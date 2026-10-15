"""Fixtures partagées par les tests."""

import sqlite3
from collections.abc import Iterator
from pathlib import Path

import pytest
from PySide6.QtCore import QCoreApplication

from nova.data.database import connect


@pytest.fixture(scope="session")
def qapp() -> QCoreApplication:
    """Application Qt minimale (sans fenêtre), nécessaire aux threads et signaux Qt."""
    return QCoreApplication.instance() or QCoreApplication([])


@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    return tmp_path / "nova.db"


@pytest.fixture
def db(db_path: Path) -> Iterator[sqlite3.Connection]:
    """Base SQLite neuve, dans un dossier temporaire propre à chaque test."""
    conn = connect(db_path)
    yield conn
    conn.close()
