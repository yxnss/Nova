"""Tests de la table des sessions et de la réparation après un crash."""

import sqlite3

from fakes import TrackerHarness
from nova.data.database import connect
from nova.data.games_repo import GameRepository
from nova.data.sessions_repo import RepairReport, SessionRepository
from nova.data.stats import load_stats


def session_rows(conn: sqlite3.Connection) -> list[tuple[int, int, int, int | None]]:
    rows = conn.execute(
        "SELECT game_id, started_at, last_saved_at, ended_at FROM sessions ORDER BY id"
    )
    return [tuple(row) for row in rows]


def test_session_lifecycle(db: sqlite3.Connection) -> None:
    game = GameRepository(db).add("game.exe", "Game", added_at=0)
    sessions = SessionRepository(db)

    session_id = sessions.open_session(game.id, started_at=100.4, saved_at=110.6)
    assert session_rows(db) == [(game.id, 100, 111, None)]

    sessions.save_session(session_id, saved_at=170)
    assert session_rows(db) == [(game.id, 100, 170, None)]

    sessions.close_session(session_id, ended_at=195)
    assert session_rows(db) == [(game.id, 100, 195, 195)]


def test_repair_closes_open_sessions_at_their_last_save(db: sqlite3.Connection) -> None:
    game = GameRepository(db).add("game.exe", "Game", added_at=0)
    sessions = SessionRepository(db)
    finished = sessions.open_session(game.id, 0, 10)
    sessions.close_session(finished, 50)
    sessions.open_session(game.id, 1000, 1130)  # interrompue par un crash

    report = sessions.repair_open_sessions(min_session=10)

    assert report == RepairReport(closed=1, deleted=0)
    assert session_rows(db) == [(game.id, 0, 50, 50), (game.id, 1000, 1130, 1130)]


def test_repair_deletes_open_sessions_that_are_too_short(db: sqlite3.Connection) -> None:
    game = GameRepository(db).add("game.exe", "Game", added_at=0)
    sessions = SessionRepository(db)
    sessions.open_session(game.id, 1000, 1004)

    report = sessions.repair_open_sessions(min_session=10)

    assert report == RepairReport(closed=0, deleted=1)
    assert session_rows(db) == []


def test_repair_on_a_clean_database_does_nothing(db: sqlite3.Connection) -> None:
    assert SessionRepository(db).repair_open_sessions(10) == RepairReport(closed=0, deleted=0)


def test_crash_loses_at_most_the_time_since_last_save(db_path) -> None:
    """Scénario complet : le moteur écrit dans SQLite, Nova plante, puis redémarre."""
    conn = connect(db_path)
    game = GameRepository(conn).add("game.exe", "Game", added_at=0)
    h = TrackerHarness(store=SessionRepository(conn))
    h.tracker.set_games(GameRepository(conn).list_tracked())
    h.scanner.launch(100, "game.exe")
    h.tick()  # t=0 : jeu détecté
    h.run(185)  # sauvegardes à t=10, 70 et 130 ; plantage à t=185
    conn.close()  # pas d'arrêt propre : la session reste ouverte en base

    restarted = connect(db_path)
    report = SessionRepository(restarted).repair_open_sessions(min_session=10)

    assert report == RepairReport(closed=1, deleted=0)
    assert session_rows(restarted) == [(game.id, 0, 130, 130)]
    assert load_stats(restarted, now=200)[game.id].total_seconds == 130
    restarted.close()
