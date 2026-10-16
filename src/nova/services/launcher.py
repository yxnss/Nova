"""Bouton « Lancer » : lancement d'un jeu et détection des jeux non lançables.

Certains jeux ne se lancent pas directement : Valorant exige le Riot Client, un jeu
Epic passe par son lanceur… Un jeu est marqué « non lançable » si Windows refuse de
le lancer (Vanguard répond « Accès refusé »), s'il n'est pas détecté dans le délai
prévu ou s'il se ferme presque aussitôt. Le bouton reste alors grisé avec un
message, et ce choix est mémorisé.

En base, on enregistre un **code** de raison (« access_denied »…) et non la phrase
affichée : le texte peut ainsi évoluer sans toucher aux données.
"""

import logging
import os
from collections.abc import Callable
from pathlib import Path

from PySide6.QtCore import QObject, QTimer, Signal, SignalInstance

from nova.core.events import GameStarted, GameStopped, StopReason
from nova.core.models import Game

log = logging.getLogger(__name__)

# Délai pour que le jeu soit détecté après un clic. Assez long pour les lanceurs
# qui démarrent le vrai jeu après une vérification ou une mise à jour.
LAUNCH_TIMEOUT = 45.0

# Codes de raison enregistrés en base (colonne games.launch_error).
ACCESS_DENIED = "access_denied"  # Windows a refusé (anti-triche qui bloque le lancement direct)
WINDOWS_ERROR = "windows_error"  # autre refus de Windows
NOT_DETECTED = "not_detected"  # le jeu n'est jamais apparu après le clic
CLOSED_IMMEDIATELY = "closed_immediately"  # le jeu s'est fermé en moins de 10 s

# Codes d'erreur Windows utiles ici.
_ERROR_ACCESS_DENIED = 5
_ERROR_CANCELLED = 1223  # l'utilisateur a répondu « Non » à la fenêtre UAC

NOT_LAUNCHABLE = (
    "Ce jeu ne se lance pas directement. Lancez-le depuis son lanceur habituel "
    "(Riot Client, Epic Games…) : Nova mesurera son temps de jeu quand même."
)
UNKNOWN_PATH = (
    "Chemin inconnu : lancez le jeu une première fois depuis son lanceur habituel, "
    "Nova retiendra son emplacement."
)
MISSING_FILE = "Fichier introuvable : le jeu a peut-être été déplacé ou désinstallé."


class LaunchError(Exception):
    """Le jeu ne peut pas être lancé ; le message s'affiche tel quel."""


def launch_problem(game: Game) -> str | None:
    """Message expliquant pourquoi le jeu ne peut pas être lancé depuis Nova, ou None."""
    if game.launch_error:
        # Quel que soit le code enregistré, le conseil utile est le même.
        return NOT_LAUNCHABLE
    if not game.exe_path:
        return UNKNOWN_PATH
    if not Path(game.exe_path).is_file():
        return MISSING_FILE
    return None


def open_with_windows(exe_path: str) -> None:
    """Lance l'exe comme un double-clic, depuis son dossier.

    Passer par Windows (et non par un simple sous-processus) affiche la fenêtre de
    confirmation (UAC) si le jeu demande les droits administrateur. Le dossier de
    travail est celui du jeu : beaucoup de jeux ne trouvent pas leurs fichiers sinon.
    """
    os.startfile(exe_path, cwd=str(Path(exe_path).parent))


class GameLauncher(QObject):
    launch_failed = Signal(int, str)  # id du jeu, code de raison (à enregistrer)
    pending_changed = Signal()  # un lancement commence ou se termine

    def __init__(
        self,
        game_started: SignalInstance,
        game_stopped: SignalInstance,
        timeout: float = LAUNCH_TIMEOUT,
        open_file: Callable[[str], None] = open_with_windows,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._timeout = timeout
        self._open_file = open_file
        self._pending: dict[int, QTimer] = {}  # lancé depuis Nova, pas encore détecté
        self._watched: set[int] = set()  # détecté : on guette une fermeture immédiate
        game_started.connect(self._on_started)
        game_stopped.connect(self._on_stopped)

    def is_pending(self, game_id: int) -> bool:
        return game_id in self._pending

    def launch(self, game: Game) -> None:
        problem = launch_problem(game)
        if problem:
            raise LaunchError(problem)
        try:
            self._open_file(game.exe_path)
        except OSError as error:
            code = getattr(error, "winerror", None)
            if code == _ERROR_CANCELLED:
                # Refus de l'utilisateur dans la fenêtre UAC : le jeu n'est pas en cause.
                raise LaunchError("Lancement annulé.") from error
            log.warning("Windows refuse de lancer %s : %s", game.exe_path, error)
            reason = ACCESS_DENIED if code == _ERROR_ACCESS_DENIED else WINDOWS_ERROR
            self.launch_failed.emit(game.id, reason)
            raise LaunchError(NOT_LAUNCHABLE) from error

        timer = QTimer(self)
        timer.setSingleShot(True)
        timer.timeout.connect(lambda: self._fail(game.id, NOT_DETECTED))
        timer.start(round(self._timeout * 1000))
        self._pending[game.id] = timer
        self.pending_changed.emit()

    def _on_started(self, event: GameStarted) -> None:
        if self._stop_waiting(event.game_id):
            self._watched.add(event.game_id)
            self.pending_changed.emit()

    def _on_stopped(self, event: GameStopped) -> None:
        if event.game_id not in self._watched:
            return
        self._watched.discard(event.game_id)
        # Fermé avant la durée minimale d'une session : le jeu a refusé de démarrer
        # (lanceur exigé, anti-triche…).
        if event.reason == StopReason.CLOSED and not event.counted:
            self._fail(event.game_id, CLOSED_IMMEDIATELY)

    def _fail(self, game_id: int, reason: str) -> None:
        self._stop_waiting(game_id)
        self.launch_failed.emit(game_id, reason)
        self.pending_changed.emit()

    def _stop_waiting(self, game_id: int) -> bool:
        timer = self._pending.pop(game_id, None)
        if timer is None:
            return False
        timer.stop()
        timer.deleteLater()
        return True
