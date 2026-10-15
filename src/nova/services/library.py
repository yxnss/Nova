"""Bibliothèque de jeux, côté interface : lecture, ajout et retrait.

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
from nova.system.icons import IconCache

log = logging.getLogger(__name__)

_FORBIDDEN_CHARACTERS = set('<>:"/\\|?*')


class LibraryError(Exception):
    """Erreur dont le message s'affiche tel quel à l'utilisateur."""


class Tracking(Protocol):
    """Ce que la bibliothèque utilise du service de suivi."""

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
    changed = Signal()  # la liste des jeux ou leurs icônes ont changé

    def __init__(
        self,
        conn: sqlite3.Connection,
        tracking: Tracking,
        icons: IconCache,
        clock: Clock | None = None,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._conn = conn
        self._games = GameRepository(conn)
        self._tracking = tracking
        self._icons = icons
        self._clock = clock or SystemClock()
        tracking.game_path_found.connect(self._on_path_found)
        tracking.game_removed.connect(self._on_game_removed)

    def games(self) -> list[Game]:
        return self._games.list_all()

    def stats(self) -> dict[int, GameStats]:
        return load_stats(self._conn, self._clock.now())

    def icon(self, game_id: int) -> QIcon | None:
        return self._icons.icon(game_id)

    def tracked_process_names(self) -> set[str]:
        return {game.process_name for game in self.games()}

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

    def _on_game_removed(self, game_id: int) -> None:
        self._icons.remove(game_id)
        self.changed.emit()

    def _on_path_found(self, game_id: int, exe_path: str) -> None:
        # Jeu ajouté par son nom : l'icône devient disponible avec le chemin.
        if self._icons.icon(game_id) is None and self._icons.extract(game_id, exe_path):
            self.changed.emit()
