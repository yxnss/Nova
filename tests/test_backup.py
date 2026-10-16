"""Tests de la sauvegarde quotidienne et de la récupération d'une base abîmée."""

import sqlite3
from datetime import date, timedelta
from pathlib import Path

import pytest

from nova.data.backup import backup_if_needed, latest_backup, open_or_recover
from nova.data.database import MIGRATIONS, UnsupportedDatabaseVersion, connect
from nova.data.games_repo import GameRepository

DAY = date(2026, 10, 17)


def test_one_backup_per_day(db: sqlite3.Connection, tmp_path: Path) -> None:
    folder = tmp_path / "backups"
    GameRepository(db).add("game.exe", "Mon jeu", added_at=0)

    first = backup_if_needed(db, folder, today=DAY)
    assert first == folder / "nova-2026-10-17.db"
    assert backup_if_needed(db, folder, today=DAY) is None  # déjà faite aujourd'hui

    copy = sqlite3.connect(first)
    assert copy.execute("SELECT display_name FROM games").fetchone()[0] == "Mon jeu"
    copy.close()


def test_only_the_last_seven_backups_are_kept(db: sqlite3.Connection, tmp_path: Path) -> None:
    folder = tmp_path / "backups"
    for offset in range(10):
        backup_if_needed(db, folder, today=DAY + timedelta(days=offset))

    kept = sorted(path.name for path in folder.glob("nova-*.db"))
    assert len(kept) == 7
    assert kept[0] == "nova-2026-10-20.db"
    assert latest_backup(folder).name == "nova-2026-10-26.db"


def test_healthy_database_opens_normally(db_path: Path, tmp_path: Path) -> None:
    conn, message = open_or_recover(db_path, tmp_path / "backups")
    assert message is None
    conn.close()


def damage(path: Path) -> None:
    path.write_bytes(b"ceci n'est plus une base SQLite" * 100)


def test_damaged_database_is_restored_from_the_latest_backup(db_path: Path, tmp_path: Path) -> None:
    folder = tmp_path / "backups"
    conn = connect(db_path)
    GameRepository(conn).add("game.exe", "Mon jeu", added_at=0)
    backup_if_needed(conn, folder, today=DAY)
    conn.close()
    damage(db_path)

    conn, message = open_or_recover(db_path, folder)
    assert "restaurée" in message and "2026-10-17" in message
    assert [game.display_name for game in GameRepository(conn).list_all()] == ["Mon jeu"]
    conn.close()
    # La base abîmée est gardée à côté, jamais supprimée.
    assert list(tmp_path.glob("nova.db.abimee-*"))


def test_damaged_database_without_backup_starts_empty(db_path: Path, tmp_path: Path) -> None:
    damage(db_path)
    conn, message = open_or_recover(db_path, tmp_path / "backups")
    assert "vide" in message
    assert GameRepository(conn).list_all() == []
    conn.close()


def test_database_from_a_newer_nova_is_never_touched(db_path: Path, tmp_path: Path) -> None:
    conn = connect(db_path)
    conn.execute(f"PRAGMA user_version = {len(MIGRATIONS) + 1}")
    conn.close()

    with pytest.raises(UnsupportedDatabaseVersion):
        open_or_recover(db_path, tmp_path / "backups")
    assert not list(tmp_path.glob("nova.db.abimee-*"))
