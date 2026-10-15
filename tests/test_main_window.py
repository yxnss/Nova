"""Test d'ensemble de la fenêtre principale (jamais affichée à l'écran)."""

import sqlite3
from pathlib import Path

import pytest

from fakes import FakeClock, FakeTracking
from nova.core.events import GameStarted, GameStopped, StopReason
from nova.services.library import LibraryService
from nova.system.icons import IconCache
from nova.ui.library_model import GameListModel
from nova.ui.main_window import MainWindow


@pytest.fixture
def setup(qapp, db: sqlite3.Connection, tmp_path: Path):
    tracking = FakeTracking()
    library = LibraryService(db, tracking, IconCache(tmp_path / "icons"), FakeClock())
    window = MainWindow(library, tracking)
    yield window, library, tracking
    window.deleteLater()


def test_empty_library_shows_the_invitation(setup) -> None:
    window, _, _ = setup
    assert window._pages.currentWidget() is window._empty


def test_added_game_appears_and_is_selected(setup) -> None:
    window, library, _ = setup
    library.add_game("game.exe", "Mon jeu")

    assert window._pages.currentWidget() is window._details
    assert window._list.currentIndex().data() == "Mon jeu"
    assert window._details._title.text() == "Mon jeu"


def test_running_game_is_marked_then_unmarked(setup) -> None:
    window, library, tracking = setup
    game = library.add_game("game.exe", "Mon jeu")

    tracking.game_started.emit(GameStarted(game.id, 1000, None))
    assert window._list.currentIndex().data(GameListModel.RunningRole) is True
    assert "En cours" in window._details._status.text()

    tracking.game_stopped.emit(GameStopped(game.id, 1000, 1600, StopReason.CLOSED, True))
    assert window._list.currentIndex().data(GameListModel.RunningRole) is False
    assert window._details._status.text() == "Fermé"


def test_search_filters_the_list(setup) -> None:
    window, library, _ = setup
    library.add_game("a.exe", "Apex")
    library.add_game("z.exe", "Zelda")

    window._search.setText("zel")
    assert window._proxy.rowCount() == 1
    assert window._proxy.index(0, 0).data() == "Zelda"
