"""Tests de la table des jeux."""

import sqlite3

import pytest

from nova.core.models import Game, TrackedGame
from nova.data.games_repo import DuplicateGameError, GameRepository
from nova.data.sessions_repo import SessionRepository


def test_add_stores_a_lowercase_process_name(db: sqlite3.Connection) -> None:
    games = GameRepository(db)
    game = games.add("  EldenRing.EXE ", "Elden Ring", "C:/Jeux/eldenring.exe", added_at=1000.4)

    assert game == Game(1, "eldenring.exe", "Elden Ring", "C:/Jeux/eldenring.exe", 1000)
    assert games.get(game.id) == game


def test_same_process_name_cannot_be_added_twice(db: sqlite3.Connection) -> None:
    games = GameRepository(db)
    games.add("game.exe", "Game", added_at=0)

    with pytest.raises(DuplicateGameError):
        games.add("GAME.exe", "Autre nom", added_at=0)


def test_game_added_by_name_has_no_path_until_discovered(db: sqlite3.Connection) -> None:
    games = GameRepository(db)
    game = games.add("game.exe", "Game", added_at=0)
    assert game.exe_path is None

    games.update_exe_path(game.id, "D:/Jeux/game.exe")
    assert games.get(game.id).exe_path == "D:/Jeux/game.exe"


def test_list_tracked_gives_what_the_tracker_needs(db: sqlite3.Connection) -> None:
    games = GameRepository(db)
    games.add("a.exe", "A", added_at=0)
    games.add("b.exe", "B", added_at=0)

    assert games.list_tracked() == [TrackedGame(1, "a.exe"), TrackedGame(2, "b.exe")]


def test_get_unknown_game_returns_none(db: sqlite3.Connection) -> None:
    assert GameRepository(db).get(42) is None


def test_deleting_a_game_also_deletes_its_sessions(db: sqlite3.Connection) -> None:
    games, sessions = GameRepository(db), SessionRepository(db)
    kept = games.add("kept.exe", "Gardé", added_at=0)
    removed = games.add("removed.exe", "Retiré", added_at=0)
    sessions.open_session(kept.id, 0, 60)
    sessions.open_session(removed.id, 0, 60)

    games.delete(removed.id)

    assert games.get(removed.id) is None
    remaining = db.execute("SELECT game_id FROM sessions").fetchall()
    assert [row["game_id"] for row in remaining] == [kept.id]


def test_banner_and_launch_error_are_stored(db: sqlite3.Connection) -> None:
    games = GameRepository(db)
    game = games.add("game.exe", "Game", "C:/Jeux/game.exe", added_at=0)

    games.set_banner(game.id, "1-abcd.jpg")
    games.set_launch_error(game.id, "Ce jeu ne se lance pas directement.")
    stored = games.get(game.id)
    assert (stored.banner_file, stored.launch_error) == (
        "1-abcd.jpg",
        "Ce jeu ne se lance pas directement.",
    )


def test_new_exe_path_forgets_a_previous_launch_failure(db: sqlite3.Connection) -> None:
    games = GameRepository(db)
    game = games.add("game.exe", "Game", "C:/Jeux/game.exe", added_at=0)
    games.set_launch_error(game.id, "Ce jeu ne se lance pas directement.")

    games.update_exe_path(game.id, "D:/Jeux/game.exe")  # jeu déplacé ou réinstallé
    assert games.get(game.id).launch_error is None
