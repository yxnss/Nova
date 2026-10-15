"""Tests du moteur de suivi, avec une horloge et des processus simulés.

Les instants sont en secondes depuis le démarrage simulé de Nova (t=0). Un tick
a lieu toutes les 5 s, comme dans l'application.
"""

import pytest

from fakes import TrackerHarness
from nova.core.events import GameStarted, GameStopped, StopReason
from nova.core.models import TrackedGame

GAME = TrackedGame(1, "game.exe")
OTHER = TrackedGame(2, "other.exe")


def start_game(h: TrackerHarness, pid: int = 100) -> None:
    """Lance le jeu puis fait le premier tick : le jeu est détecté à l'instant courant."""
    h.scanner.launch(pid, "game.exe")
    h.tick()


# --- Sessions normales ---


def test_normal_session_is_recorded_from_detection_to_closing() -> None:
    h = TrackerHarness(GAME)
    start_game(h)  # t=0 : jeu détecté
    h.run(120)  # t=120 : toujours en cours
    h.scanner.kill(100)
    h.run(5)  # t=125 : fermeture constatée

    assert h.store.periods() == [(1, 0, 125)]
    assert h.events == [
        GameStarted(1, 0, "C:/Jeux/game.exe"),
        GameStopped(1, 0, 125, StopReason.CLOSED, counted=True),
    ]
    assert h.tracker.running_games() == {}


def test_running_session_is_saved_every_minute() -> None:
    h = TrackerHarness(GAME)
    start_game(h)
    h.run(190)

    # Création à 10 s (durée minimale atteinte), puis une sauvegarde par minute.
    assert h.store.writes == [("open", 10), ("save", 70), ("save", 130), ("save", 190)]


def test_nothing_is_written_when_no_game_runs() -> None:
    h = TrackerHarness(GAME)
    h.tick()
    h.run(600)
    assert h.store.writes == []


def test_session_starts_when_nova_detects_the_game() -> None:
    h = TrackerHarness(GAME)
    h.scanner.launch(100, "game.exe")  # le jeu tournait déjà avant Nova
    h.clock.advance(500)
    h.tick()
    assert h.tracker.running_games() == {1: 500}


# --- Sessions trop courtes ---


def test_too_short_session_is_ignored() -> None:
    h = TrackerHarness(GAME)
    start_game(h)  # t=0
    h.scanner.kill(100)  # crash immédiat
    h.run(5)  # t=5

    assert h.store.writes == []
    assert h.stopped() == [GameStopped(1, 0, 5, StopReason.CLOSED, counted=False)]


def test_session_reaching_minimum_between_two_ticks_is_recorded() -> None:
    h = TrackerHarness(GAME)
    start_game(h)  # t=0
    h.run(5)  # t=5 : 5 s, encore provisoire
    h.scanner.kill(100)
    h.run(5)  # t=10 : fermé, mais 10 s atteintes

    assert h.store.periods() == [(1, 0, 10)]
    assert h.stopped()[0].counted


# --- Processus multiples ---


def test_several_processes_share_one_counter() -> None:
    h = TrackerHarness(GAME)
    h.scanner.launch(100, "game.exe")
    h.scanner.launch(101, "game.exe")
    h.tick()  # t=0
    h.run(30)
    h.scanner.kill(100)  # un des deux processus se ferme : le jeu continue
    h.run(30)
    h.scanner.kill(101)
    h.run(5)  # t=65

    assert h.store.periods() == [(1, 0, 65)]
    assert len(h.started()) == 1
    assert len(h.stopped()) == 1


def test_game_restarting_its_process_keeps_one_session() -> None:
    h = TrackerHarness(GAME)
    start_game(h, pid=100)  # t=0
    h.run(20)
    h.scanner.kill(100)  # le jeu se relance (mise à jour, options graphiques...)
    h.scanner.launch(200, "game.exe")
    h.run(20)  # dès t=25, le scan de confirmation trouve le nouveau PID 200
    h.scanner.kill(200)
    h.run(5)  # t=45

    assert h.store.periods() == [(1, 0, 45)]
    assert len(h.started()) == 1


def test_second_game_is_detected_by_the_regular_full_scan() -> None:
    h = TrackerHarness(GAME, OTHER)
    start_game(h)  # t=0
    h.run(10)
    h.scanner.launch(200, "other.exe", path="C:/Jeux/other.exe")  # lancé pendant la partie
    h.run(20)  # t=30 : scan complet régulier

    assert h.started()[-1] == GameStarted(2, 30, "C:/Jeux/other.exe")
    assert h.tracker.running_games() == {1: 0, 2: 30}


# --- Coût du scan ---


def test_full_scan_every_30_seconds_during_a_session() -> None:
    h = TrackerHarness(GAME)
    start_game(h)
    h.run(120)  # ticks à 0, 5, ..., 120

    # Scans complets à 0, 30, 60, 90 et 120 ; simple vérification des PID sinon.
    assert h.scanner.full_scans == 5
    assert h.scanner.pid_checks == 20


def test_full_scan_every_tick_when_no_game_runs() -> None:
    h = TrackerHarness(GAME)
    h.tick()
    h.run(60)  # 13 ticks au total
    assert h.scanner.full_scans == 13
    assert h.scanner.pid_checks == 0


def test_no_scan_at_all_when_no_game_is_tracked() -> None:
    h = TrackerHarness()
    h.tick()
    h.run(60)
    assert h.scanner.full_scans == 0
    assert h.scanner.pid_checks == 0


def test_newly_added_game_is_searched_at_the_next_tick() -> None:
    h = TrackerHarness(GAME)
    start_game(h)  # t=0
    h.run(10)
    h.scanner.launch(200, "other.exe")
    h.events += h.tracker.set_games([GAME, OTHER])  # ajouté pendant la partie
    h.run(5)  # t=15 : scan complet immédiat, sans attendre t=30

    assert h.tracker.running_games() == {1: 0, 2: 15}


# --- Veille et changements d'heure ---


@pytest.mark.parametrize("monotonic_counts", [True, False])
def test_sleep_closes_session_at_last_reliable_instant(monotonic_counts: bool) -> None:
    h = TrackerHarness(GAME)
    start_game(h)  # t=0
    h.run(60)  # t=60 : dernier tick avant la veille
    h.clock.suspend(3600, monotonic_counts)  # une heure de veille
    h.run(5)  # t=3665 : réveil, le jeu tourne toujours
    h.run(60)
    h.scanner.kill(100)
    h.run(5)  # t=3730

    assert h.store.periods() == [(1, 0, 60), (1, 3665, 3730)]
    assert h.stopped()[0] == GameStopped(1, 0, 60, StopReason.GAP, counted=True)


def test_game_closed_during_sleep_is_not_reopened() -> None:
    h = TrackerHarness(GAME)
    start_game(h)
    h.run(60)
    h.scanner.kill(100)
    h.clock.suspend(3600, monotonic_counts=False)
    h.run(5)

    assert h.store.periods() == [(1, 0, 60)]
    assert h.tracker.running_games() == {}


def test_clock_set_back_never_produces_a_negative_duration() -> None:
    h = TrackerHarness(GAME)
    start_game(h)  # t=0
    h.run(60)
    h.clock.change_time(-7200)  # l'utilisateur recule l'heure de 2 h
    h.run(60)
    h.scanner.kill(100)
    h.run(5)

    periods = h.store.periods()
    assert periods[0] == (1, 0, 60)
    assert all(end is not None and end >= start for _, start, end in periods)


# --- Pause, retrait, arrêt ---


def test_pause_closes_session_and_stops_all_scanning() -> None:
    h = TrackerHarness(GAME)
    start_game(h)
    h.run(40)
    h.events += h.tracker.pause()  # t=40
    scans = (h.scanner.full_scans, h.scanner.pid_checks)
    h.run(60)  # en pause : les ticks ne font rien

    assert h.store.periods() == [(1, 0, 40)]
    assert h.stopped()[-1].reason == StopReason.PAUSED
    assert (h.scanner.full_scans, h.scanner.pid_checks) == scans
    assert h.tracker.paused


def test_resume_reopens_a_session_if_the_game_still_runs() -> None:
    h = TrackerHarness(GAME)
    start_game(h)
    h.run(40)
    h.tracker.pause()  # t=40
    h.run(60)
    h.tracker.resume()  # t=100
    h.run(5)  # t=105

    assert h.tracker.running_games() == {1: 105}
    assert not h.tracker.paused


def test_pause_right_after_waking_up_ends_session_before_sleep() -> None:
    h = TrackerHarness(GAME)
    start_game(h)
    h.run(60)  # t=60 : dernier tick avant la veille
    h.clock.suspend(3600, monotonic_counts=False)
    h.events += h.tracker.pause()  # demandée au réveil, avant tout nouveau tick

    assert h.store.periods() == [(1, 0, 60)]


def test_removing_a_running_game_closes_its_session() -> None:
    h = TrackerHarness(GAME)
    start_game(h)
    h.run(30)
    h.events += h.tracker.set_games([])  # t=30
    scans = h.scanner.full_scans
    h.run(60)

    assert h.store.periods() == [(1, 0, 30)]
    assert h.stopped()[-1].reason == StopReason.UNTRACKED
    assert h.scanner.full_scans == scans


def test_shutdown_closes_running_sessions() -> None:
    h = TrackerHarness(GAME)
    start_game(h)
    h.run(95)
    h.events += h.tracker.shutdown()

    assert h.store.periods() == [(1, 0, 95)]
    assert h.stopped()[-1].reason == StopReason.SHUTDOWN


# --- Identification des jeux ---


def test_unreadable_path_does_not_prevent_tracking() -> None:
    h = TrackerHarness(GAME)
    h.scanner.launch(100, "game.exe", path=None)  # processus protégé (anti-triche)
    h.tick()
    h.run(30)

    assert h.started() == [GameStarted(1, 0, None)]
    assert h.store.writes[0] == ("open", 10)


def test_process_name_is_case_insensitive() -> None:
    h = TrackerHarness(TrackedGame(1, "EldenRing.EXE"))
    h.scanner.launch(100, "eldenring.exe")
    h.tick()
    assert h.tracker.running_games() == {1: 0}
