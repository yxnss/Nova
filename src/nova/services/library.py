"""Bibliothèque de jeux, côté interface : lecture, ajout, retrait, bannières, lancement.

Tourne dans le thread principal avec sa propre connexion SQLite. Le retrait d'un
jeu passe par le thread de suivi, seul à écrire dans les sessions : il arrête
d'abord de suivre le jeu, puis le supprime avec son historique.
"""

import logging
import sqlite3
from pathlib import Path, PureWindowsPath
from typing import Protocol

from PySide6.QtCore import QObject, Signal, SignalInstance
from PySide6.QtGui import QIcon

from nova.core.clock import Clock, SystemClock
from nova.core.models import Game, GameStats
from nova.data.games_repo import DuplicateGameError, GameRepository, normalize_process_name
from nova.data.stats import load_stats
from nova.services.launcher import GameLauncher, LaunchError
from nova.system.banners import BannerError, BannerStore
from nova.system.icons import IconCache

log = logging.getLogger(__name__)

_FORBIDDEN_CHARACTERS = set('<>:"/\\|?*')


class LibraryError(Exception):
    """Erreur dont le message s'affiche tel quel à l'utilisateur."""


class Tracking(Protocol):
    """Ce que la bibliothèque utilise du service de suivi."""

    game_started: SignalInstance
    game_stopped: SignalInstance
    game_path_found: SignalInstance
    game_removed: SignalInstance

    def reload_games(self) -> None: ...

    def remove_game(self, game_id: int) -> None: ...


def normalize_new_process_name(text: str) -> str:
    """Nom de processus saisi par l'utilisateur, mis sous la forme enregistrée.

    « Jeu » devient « jeu.exe » ; un chemin complet collé par erreur est ramené au
    nom du fichier. Lève LibraryError si le nom est vide ou invalide.
    """
    name = text.strip().strip('"').strip()
    if "\\" in name or "/" in name:
        name = PureWindowsPath(name).name
    if not name:
        raise LibraryError("Indiquez le nom du processus, par exemple « jeu.exe ».")
    if any(character in _FORBIDDEN_CHARACTERS for character in name):
        raise LibraryError("Ce nom contient des caractères interdits dans un nom de fichier.")
    if not name.lower().endswith(".exe"):
        name += ".exe"
    return normalize_process_name(name)


class LibraryService(QObject):
    changed = Signal()  # la liste des jeux, leurs icônes ou leurs bannières ont changé
    launch_state_changed = Signal()  # un lancement depuis Nova commence ou se termine

    def __init__(
        self,
        conn: sqlite3.Connection,
        tracking: Tracking,
        icons: IconCache,
        banners: BannerStore,
        clock: Clock | None = None,
        launcher: GameLauncher | None = None,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._conn = conn
        self._games = GameRepository(conn)
        self._tracking = tracking
        self._icons = icons
        self._banners = banners
        self._clock = clock or SystemClock()
        self._launcher = launcher or GameLauncher(tracking.game_started, tracking.game_stopped)
        self._launcher.setParent(self)
        self._launcher.launch_failed.connect(self._on_launch_failed)
        self._launcher.pending_changed.connect(self.launch_state_changed)
        tracking.game_path_found.connect(self._on_path_found)
        tracking.game_removed.connect(self._on_game_removed)

    # --- Lecture ---

    def games(self) -> list[Game]:
        return self._games.list_all()

    def stats(self) -> dict[int, GameStats]:
        return load_stats(self._conn, self._clock.now())

    def icon(self, game_id: int) -> QIcon | None:
        return self._icons.icon(game_id)

    def banner_path(self, game: Game) -> Path | None:
        return self._banners.path(game.banner_file) if game.banner_file else None

    def tracked_process_names(self) -> set[str]:
        return {game.process_name for game in self.games()}

    def is_launching(self, game_id: int) -> bool:
        return self._launcher.is_pending(game_id)

    # --- Ajout et retrait ---

    def add_game(self, process_name: str, display_name: str, exe_path: str | None = None) -> Game:
        """Ajoute un jeu et lance son suivi. Lève LibraryError avec un message lisible."""
        name = normalize_new_process_name(process_name)
        display = " ".join(display_name.split()) or Path(name).stem
        try:
            game = self._games.add(name, display, exe_path, added_at=self._clock.now())
        except DuplicateGameError:
            raise LibraryError(f"« {name} » est déjà dans votre bibliothèque.") from None
        if exe_path:
            self._icons.extract(game.id, exe_path)
        log.info("Jeu ajouté : %s (%s)", display, name)
        self._tracking.reload_games()
        self.changed.emit()
        return game

    def remove_game(self, game_id: int) -> None:
        """Demande le retrait du jeu ; ``changed`` sera émis une fois la suppression faite."""
        self._tracking.remove_game(game_id)

    # --- Bannières ---

    def set_banner(self, game_id: int, image_path: str) -> None:
        """Copie l'image choisie dans les données de Nova et en fait la bannière du jeu."""
        game = self._games.get(game_id)
        if game is None:
            return
        try:
            new_file = self._banners.import_image(game_id, image_path)
        except BannerError as error:
            raise LibraryError(str(error)) from None
        self._games.set_banner(game_id, new_file)
        self._banners.remove(game.banner_file)  # l'ancienne bannière ne sert plus
        self.changed.emit()

    def reset_banner(self, game_id: int) -> None:
        game = self._games.get(game_id)
        if game is None or game.banner_file is None:
            return
        self._games.set_banner(game_id, None)
        self._banners.remove(game.banner_file)
        self.changed.emit()

    # --- Lancement ---

    def launch_game(self, game_id: int) -> None:
        game = self._games.get(game_id)
        if game is None:
            return
        try:
            self._launcher.launch(game)
        except LaunchError as error:
            raise LibraryError(str(error)) from None
        log.info("Lancement de %s depuis Nova", game.display_name)

    def _on_launch_failed(self, game_id: int, message: str) -> None:
        log.warning("Jeu %d marqué comme non lançable : %s", game_id, message)
        self._games.set_launch_error(game_id, message)
        self.changed.emit()

    # --- Réactions au thread de suivi ---

    def _on_game_removed(self, game_id: int) -> None:
        self._icons.remove(game_id)
        self._banners.remove_all_for(game_id)
        self.changed.emit()

    def _on_path_found(self, game_id: int, exe_path: str) -> None:
        # Le chemin vient d'être enregistré : l'icône devient disponible (jeu ajouté
        # par son nom) et un ancien échec de lancement est oublié (jeu déplacé).
        if self._icons.icon(game_id) is None:
            self._icons.extract(game_id, exe_path)
        self.changed.emit()
