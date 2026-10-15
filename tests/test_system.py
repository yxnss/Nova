"""Tests des intégrations système : dossier des données et journal."""

import logging
import sys
import threading
from pathlib import Path

import pytest
from PySide6.QtCore import QThread

from nova.system import paths
from nova.system.logging_setup import setup_logging


def test_data_dir_is_nova_folder_in_appdata(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.delenv("NOVA_DATA_DIR", raising=False)
    monkeypatch.setenv("APPDATA", str(tmp_path))

    assert paths.data_dir() == tmp_path / "Nova"
    assert paths.data_dir().is_dir()
    assert paths.database_path() == tmp_path / "Nova" / "nova.db"


def test_data_dir_can_be_overridden(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("NOVA_DATA_DIR", str(tmp_path / "essai"))

    assert paths.data_dir() == tmp_path / "essai"
    assert paths.logs_dir() == tmp_path / "essai" / "logs"
    assert paths.logs_dir().is_dir()


@pytest.fixture
def restore_logging():
    """Remet le journal et les gestionnaires d'erreurs dans leur état d'origine après le test."""
    root = logging.getLogger()
    handlers, level = list(root.handlers), root.level
    hooks = (sys.excepthook, threading.excepthook)
    yield
    for handler in list(root.handlers):
        root.removeHandler(handler)
        handler.close()
    for handler in handlers:
        root.addHandler(handler)
    root.setLevel(level)
    sys.excepthook, threading.excepthook = hooks


def read_log(logs_dir: Path) -> str:
    for handler in logging.getLogger().handlers:
        handler.flush()
    return (logs_dir / "nova.log").read_text(encoding="utf-8")


def test_log_lines_from_a_qt_thread_carry_its_name(qapp, tmp_path: Path, restore_logging) -> None:
    class LoggingThread(QThread):
        def run(self) -> None:
            logging.getLogger("nova.test").info("message du thread de suivi")

    setup_logging(tmp_path)
    thread = LoggingThread()
    thread.setObjectName("suivi")
    thread.start()
    thread.wait()

    assert "[suivi] nova.test : message du thread de suivi" in read_log(tmp_path)


def test_log_file_receives_messages(tmp_path: Path, restore_logging) -> None:
    setup_logging(tmp_path)
    logging.getLogger("nova.test").info("Jeu 1 démarré")

    assert "[MainThread] nova.test : Jeu 1 démarré" in read_log(tmp_path)
