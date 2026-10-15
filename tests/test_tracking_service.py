"""Tests du thread de suivi Qt, avec des processus simulés et des intervalles très courts."""

import sqlite3
import time
from collections.abc import Callable, Iterator
from pathlib import Path

import pytest
from PySide6.QtCore import QCoreApplication, QEventLoop

from fakes import FakeScanner
from nova.core.events import GameStarted, GameStopped, StopReason
from nova.core.tracker import TrackerSettings
from nova.data.database import connect
from nova.data.games_repo import GameRepository
from nova.data.sessions_repo import RepairReport, SessionRepository
from nova.services.tracking import TrackingService

# Intervalles en dizaines de millisecondes pour que les tests soient rapides. Le
# seuil d'écart anormal est large : un minuteur un peu en retard ne doit pas être
# pris pour une veille.
FAST = TrackerSettings(
    scan_interval=0.02,
    checkpoint_interval=0.1,
    min_session=0.05,
    gap_factor=50,
    full_scan_interval=0.1,
)


def wait_until(condition: Callable[[], bool], timeout: float = 5.0) -> None:
    """Fait tourner la boucle d'événements Qt jusqu'à ce que la condition soit vraie."""
    deadline = time.monotonic() + timeout
    while not condition():
        assert time.monotonic() < deadline, "délai dépassé"
        QCoreApplication.processEvents(QEventLoop.ProcessEventsFlag.AllEvents, 20)
        time.sleep(0.005)


class Recorder:
    """Garde tout ce qu'un service émet, pour pouvoir le vérifier ensuite."""

    def __init__(self, service: TrackingService) -> None:
        self.ready: list[RepairReport] = []
        self.started: list[GameStarted] = []
        self.stopped: list[GameStopped] = []
        self.paths: list[tuple[int, str]] = []
        self.removed: list[int] = []
        self.paused: list[bool] = []
        service.ready.connect(self.ready.append)
        service.game_started.connect(self.started.append)
        service.game_stopped.connect(self.stopped.append)
        service.game_path_found.connect(lambda game_id, path: self.paths.append((game_id, path)))
        service.game_removed.connect(self.removed.append)
        service.paused_changed.connect(self.paused.append)


@pytest.fixture
def game_id(db_path: Path) -> int:
    conn = connect(db_path)
    game_id = GameRepository(conn).add("game.exe", "Game", added_at=0).id
    conn.close()
    return game_id


@pytest.fixture
def scanner() -> FakeScanner:
    return FakeScanner()


@pytest.fixture
def service(qapp, db_path: Path, scanner: FakeScanner) -> Iterator[TrackingService]:
    service = TrackingService(db_path, FAST, scanner)
    yield service
    service.stop()  # même si le test échoue, le thread est arrêté proprement


def read_sessions(db_path: Path) -> list[sqlite3.Row]:
    conn = connect(db_path)
    rows = conn.execute("SELECT * FROM sessions").fetchall()
    conn.close()
    return rows


def test_game_is_tracked_and_saved(service, scanner, game_id, db_path) -> None:
    events = Recorder(service)
    scanner.launch(100, "game.exe")
    service.start()
    wait_until(lambda: events.started)
    time.sleep(0.15)  # le jeu tourne au-delà de la durée minimale
    scanner.kill(100)
    wait_until(lambda: events.stopped)

    assert events.ready == [RepairReport(closed=0, deleted=0)]
    assert events.started[0].game_id == game_id
    assert events.stopped[0].reason == StopReason.CLOSED
    assert events.stopped[0].counted
    rows = read_sessions(db_path)
    assert len(rows) == 1
    assert rows[0]["ended_at"] is not None


def test_interrupted_session_is_repaired_on_start(service, game_id, db_path) -> None:
    conn = connect(db_path)
    SessionRepository(conn).open_session(game_id, 1000, 1130)  # laissée ouverte par un crash
    conn.close()
    events = Recorder(service)

    service.start()
    wait_until(lambda: events.ready)

    assert events.ready == [RepairReport(closed=1, deleted=0)]


def test_path_is_remembered_for_a_game_added_by_name(service, scanner, game_id, db_path) -> None:
    events = Recorder(service)
    scanner.launch(100, "game.exe", path="D:/Jeux/game.exe")
    service.start()
    wait_until(lambda: events.paths)

    assert events.paths == [(game_id, "D:/Jeux/game.exe")]
    conn = connect(db_path)
    assert GameRepository(conn).get(game_id).exe_path == "D:/Jeux/game.exe"
    conn.close()


def test_pause_stops_scanning_and_resume_restarts_it(service, scanner, game_id) -> None:
    events = Recorder(service)
    scanner.launch(100, "game.exe")
    service.start()
    wait_until(lambda: events.started)

    service.set_paused(True)
    wait_until(lambda: events.paused == [True])
    assert events.stopped[-1].reason == StopReason.PAUSED
    scans = (scanner.full_scans, scanner.pid_checks)
    time.sleep(0.15)
    assert (scanner.full_scans, scanner.pid_checks) == scans  # aucune activité en pause

    service.set_paused(False)
    wait_until(lambda: len(events.started) == 2)
    assert events.paused == [True, False]


def test_removing_a_running_game_deletes_it_with_its_history(
    service, scanner, game_id, db_path
) -> None:
    events = Recorder(service)
    scanner.launch(100, "game.exe")
    service.start()
    wait_until(lambda: events.started)
    time.sleep(0.15)  # une session est enregistrée en base

    service.remove_game(game_id)
    wait_until(lambda: events.removed)

    assert events.stopped[-1].reason == StopReason.UNTRACKED
    conn = connect(db_path)
    assert GameRepository(conn).get(game_id) is None
    conn.close()
    assert read_sessions(db_path) == []


def test_stop_closes_the_running_session(service, scanner, game_id, db_path) -> None:
    events = Recorder(service)
    scanner.launch(100, "game.exe")
    service.start()
    wait_until(lambda: events.started)
    time.sleep(0.15)

    service.stop()
    QCoreApplication.processEvents()  # délivre les derniers signaux du thread de suivi

    assert events.stopped[-1].reason == StopReason.SHUTDOWN
    assert all(row["ended_at"] is not None for row in read_sessions(db_path))
