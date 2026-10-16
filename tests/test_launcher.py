"""Tests du lancement des jeux et de la détection des jeux non lançables."""

import sys
import time
from pathlib import Path

import pytest
from PySide6.QtCore import QCoreApplication

from fakes import FakeTracking
from nova.core.events import GameStarted, GameStopped, StopReason
from nova.core.models import Game
from nova.services.launcher import (
    MISSING_FILE,
    NOT_LAUNCHABLE,
    UNKNOWN_PATH,
    GameLauncher,
    LaunchError,
    launch_problem,
)

EXE = sys.executable  # un vrai fichier .exe, jamais exécuté par ces tests


def game(exe_path: str | None = EXE, launch_error: str | None = None) -> Game:
    return Game(1, "game.exe", "Jeu", exe_path, 0, launch_error=launch_error)


def test_launch_problems() -> None:
    assert launch_problem(game()) is None
    assert launch_problem(game(exe_path=None)) == UNKNOWN_PATH
    assert launch_problem(game(exe_path=r"C:\n-existe-pas\jeu.exe")) == MISSING_FILE
    assert launch_problem(game(launch_error="Raison mémorisée")) == "Raison mémorisée"


class Harness:
    def __init__(self, timeout: float = 5.0, open_file=None) -> None:
        self.tracking = FakeTracking()
        self.opened: list[str] = []
        self.failures: list[tuple[int, str]] = []
        self.launcher = GameLauncher(
            self.tracking.game_started,
            self.tracking.game_stopped,
            timeout=timeout,
            open_file=open_file or self.opened.append,
        )
        self.launcher.launch_failed.connect(lambda gid, msg: self.failures.append((gid, msg)))


@pytest.fixture
def h(qapp) -> Harness:
    return Harness()


def test_successful_launch(h: Harness) -> None:
    h.launcher.launch(game())
    assert h.opened == [EXE]
    assert h.launcher.is_pending(1)

    h.tracking.game_started.emit(GameStarted(1, 100, EXE))
    assert not h.launcher.is_pending(1)
    h.tracking.game_stopped.emit(GameStopped(1, 100, 3700, StopReason.CLOSED, counted=True))
    assert h.failures == []


def test_game_closing_immediately_is_not_launchable(h: Harness) -> None:
    h.launcher.launch(game())
    h.tracking.game_started.emit(GameStarted(1, 100, EXE))
    h.tracking.game_stopped.emit(GameStopped(1, 100, 104, StopReason.CLOSED, counted=False))

    assert h.failures == [(1, NOT_LAUNCHABLE)]


def test_game_never_detected_is_not_launchable(qapp) -> None:
    h = Harness(timeout=0.05)
    h.launcher.launch(game())
    deadline = time.monotonic() + 3
    while not h.failures and time.monotonic() < deadline:
        QCoreApplication.processEvents()
        time.sleep(0.01)

    assert h.failures == [(1, NOT_LAUNCHABLE)]
    assert not h.launcher.is_pending(1)


def test_short_session_of_a_game_not_launched_from_nova_is_ignored(h: Harness) -> None:
    h.tracking.game_started.emit(GameStarted(1, 100, EXE))
    h.tracking.game_stopped.emit(GameStopped(1, 100, 104, StopReason.CLOSED, counted=False))
    assert h.failures == []


def test_windows_refusal_is_reported(qapp) -> None:
    def refuse(path: str) -> None:
        raise OSError(1223, "Opération annulée par l'utilisateur")

    h = Harness(open_file=refuse)
    with pytest.raises(LaunchError):
        h.launcher.launch(game())
    assert h.failures and "Windows n'a pas pu lancer ce jeu" in h.failures[0][1]


def test_problem_prevents_launch(h: Harness) -> None:
    with pytest.raises(LaunchError, match="Chemin inconnu"):
        h.launcher.launch(game(exe_path=None))
    assert h.opened == []


def test_missing_file_message_points_to_a_real_check(tmp_path: Path) -> None:
    assert launch_problem(game(exe_path=str(tmp_path / "absent.exe"))) == MISSING_FILE
