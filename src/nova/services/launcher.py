"""Bouton « Lancer » : lancement d'un jeu et détection des jeux non lançables.

Certains jeux ne se lancent pas directement : Valorant exige le Riot Client, un jeu
Epic passe par son lanceur… Après un lancement, Nova surveille donc le jeu grâce au
moteur de suivi. S'il n'est pas détecté dans le délai prévu, ou s'il se ferme
presque aussitôt, il est marqué « non lançable » : le bouton reste alors grisé avec
un message, et ce choix est mémorisé.
"""

import os
from collections.abc import Callable
from pathlib import Path

from PySide6.QtCore import QObject, QTimer, Signal, SignalInstance

from nova.core.events import GameStarted, GameStopped, StopReason
from nova.core.models import Game

# Délai pour que le jeu soit détecté après un clic. Assez long pour les lanceurs
# qui démarrent le vrai jeu après une vérification ou une mise à jour.
LAUNCH_TIMEOUT = 45.0

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
    """Raison pour laquelle le jeu ne peut pas être lancé depuis Nova, ou None."""
    if game.launch_error:
        return game.launch_error
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
    launch_failed = Signal(int, str)  # id du jeu, message à afficher
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
            message = f"Windows n'a pas pu lancer ce jeu ({error.strerror or error})."
            self.launch_failed.emit(game.id, message)
            raise LaunchError(message) from error

        timer = QTimer(self)
        timer.setSingleShot(True)
        timer.timeout.connect(lambda: self._fail(game.id))
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
            self._fail(event.game_id)

    def _fail(self, game_id: int) -> None:
        self._stop_waiting(game_id)
        self.launch_failed.emit(game_id, NOT_LAUNCHABLE)
        self.pending_changed.emit()

    def _stop_waiting(self, game_id: int) -> bool:
        timer = self._pending.pop(game_id, None)
        if timer is None:
            return False
        timer.stop()
        timer.deleteLater()
        return True
