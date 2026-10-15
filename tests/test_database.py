"""Tests de la connexion SQLite, du schéma et des migrations."""

import sqlite3

import pytest

from nova.data.database import MIGRATIONS, UnsupportedDatabaseVersion, connect, transaction
from nova.data.games_repo import GameRepository


def pragma(conn: sqlite3.Connection, name: str) -> object:
    return conn.execute(f"PRAGMA {name}").fetchone()[0]


def test_connection_settings(db: sqlite3.Connection) -> None:
    assert pragma(db, "journal_mode") == "wal"
    assert pragma(db, "foreign_keys") == 1
    assert pragma(db, "synchronous") == 2  # FULL
    assert pragma(db, "user_version") == len(MIGRATIONS)


def test_reopening_keeps_data_and_does_not_migrate_again(db_path) -> None:
    first = connect(db_path)
    GameRepository(first).add("game.exe", "Game", added_at=0)
    first.close()

    second = connect(db_path)
    assert [g.process_name for g in GameRepository(second).list_all()] == ["game.exe"]
    assert pragma(second, "user_version") == len(MIGRATIONS)
    second.close()


def test_database_from_a_newer_nova_is_refused(db_path) -> None:
    conn = connect(db_path)
    conn.execute(f"PRAGMA user_version = {len(MIGRATIONS) + 1}")
    conn.close()

    with pytest.raises(UnsupportedDatabaseVersion):
        connect(db_path)


def test_transaction_is_cancelled_entirely_on_error(db: sqlite3.Connection) -> None:
    games = GameRepository(db)
    with pytest.raises(RuntimeError), transaction(db):
        games.add("game.exe", "Game", added_at=0)
        raise RuntimeError("panne au milieu de la transaction")

    assert games.list_all() == []
