"""Tests du calcul des statistiques : temps total, dernière utilisation, 7 derniers jours."""

import sqlite3
from datetime import UTC, datetime, timedelta, timezone

import pytest

from nova.core.models import GameStats
from nova.data.games_repo import GameRepository
from nova.data.sessions_repo import SessionRepository
from nova.data.stats import LAST_7_DAYS, add_running_session, load_stats

HOUR = 3600
DAY = 24 * HOUR
NOW = int(datetime(2026, 10, 15, 12, 0, tzinfo=UTC).timestamp())


@pytest.fixture
def game_id(db: sqlite3.Connection) -> int:
    return GameRepository(db).add("game.exe", "Game", added_at=0).id


def add_session(db: sqlite3.Connection, game_id: int, start: float, end: float) -> None:
    sessions = SessionRepository(db)
    sessions.close_session(sessions.open_session(game_id, start, start), end)


def test_game_never_played_has_empty_stats(db: sqlite3.Connection, game_id: int) -> None:
    assert load_stats(db, NOW) == {game_id: GameStats(game_id, 0, None, 0)}


def test_total_and_last_played_come_from_closed_sessions(db, game_id) -> None:
    add_session(db, game_id, NOW - 30 * DAY, NOW - 30 * DAY + 2 * HOUR)
    add_session(db, game_id, NOW - 3 * DAY, NOW - 3 * DAY + HOUR)
    # Session encore ouverte en base : c'est l'interface qui l'ajoute en direct.
    SessionRepository(db).open_session(game_id, NOW - 600, NOW - 60)

    stats = load_stats(db, NOW)[game_id]
    assert stats.total_seconds == 3 * HOUR
    assert stats.last_played_at == NOW - 3 * DAY + HOUR


def test_last_7_days_only_counts_recent_sessions(db, game_id) -> None:
    add_session(db, game_id, NOW - 10 * DAY, NOW - 10 * DAY + 2 * HOUR)  # trop ancienne
    add_session(db, game_id, NOW - 2 * DAY, NOW - 2 * DAY + HOUR)  # récente

    assert load_stats(db, NOW)[game_id].last_7_days_seconds == HOUR


def test_session_across_the_7_day_limit_is_cut(db, game_id) -> None:
    # Commence 1 h avant la limite des 7 jours et dure 3 h : seules 2 h comptent.
    start = NOW - LAST_7_DAYS - HOUR
    add_session(db, game_id, start, start + 3 * HOUR)

    stats = load_stats(db, NOW)[game_id]
    assert stats.total_seconds == 3 * HOUR
    assert stats.last_7_days_seconds == 2 * HOUR


def test_session_across_midnight_counts_once_in_full(db, game_id) -> None:
    paris_winter = timezone(timedelta(hours=1))
    start = datetime(2026, 12, 31, 23, 30, tzinfo=paris_winter).timestamp()
    end = datetime(2027, 1, 1, 0, 45, tzinfo=paris_winter).timestamp()
    add_session(db, game_id, start, end)

    stats = load_stats(db, now=end + HOUR)[game_id]
    assert stats.total_seconds == 75 * 60
    assert stats.last_7_days_seconds == 75 * 60


def test_session_across_daylight_saving_change_counts_real_duration(db, game_id) -> None:
    # Nuit du 25 octobre 2026 en France : à 3 h, on revient à 2 h. De 1 h 30 (heure
    # d'été) à 2 h 30 (heure d'hiver), l'horloge murale affiche 1 h d'écart, mais
    # 2 h se sont réellement écoulées. Nova stocke des instants UTC : 2 h comptent.
    start = datetime(2026, 10, 25, 1, 30, tzinfo=timezone(timedelta(hours=2))).timestamp()
    end = datetime(2026, 10, 25, 2, 30, tzinfo=timezone(timedelta(hours=1))).timestamp()
    add_session(db, game_id, start, end)

    assert load_stats(db, now=end)[game_id].total_seconds == 2 * HOUR


def test_each_game_has_its_own_stats(db: sqlite3.Connection) -> None:
    games = GameRepository(db)
    a = games.add("a.exe", "A", added_at=0).id
    b = games.add("b.exe", "B", added_at=0).id
    add_session(db, a, NOW - HOUR, NOW)
    add_session(db, b, NOW - 2 * HOUR, NOW - HOUR)

    stats = load_stats(db, NOW)
    assert stats[a].total_seconds == HOUR
    assert stats[b].total_seconds == HOUR
    assert stats[b].last_played_at == NOW - HOUR


def test_running_session_is_added_on_top_of_saved_stats() -> None:
    saved = GameStats(
        1, total_seconds=10 * HOUR, last_played_at=NOW - DAY, last_7_days_seconds=HOUR
    )

    live = add_running_session(saved, started_at=NOW - 1800, now=NOW)

    assert live == GameStats(1, 10 * HOUR + 1800, NOW, HOUR + 1800)


def test_running_session_started_long_ago_is_cut_to_7_days() -> None:
    saved = GameStats(1, 0, None, 0)

    live = add_running_session(saved, started_at=NOW - 8 * DAY, now=NOW)

    assert live.total_seconds == 8 * DAY
    assert live.last_7_days_seconds == LAST_7_DAYS
