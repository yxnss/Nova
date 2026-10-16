"""Tests d'ensemble de la fenêtre principale (jamais affichée à l'écran)."""

import sqlite3
import sys
from dataclasses import dataclass, field
from pathlib import Path

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QPushButton

from fakes import FakeClock, FakeTracking
from nova.core.events import GameStarted, GameStopped, StopReason
from nova.services.launcher import UNKNOWN_PATH, GameLauncher
from nova.services.library import LibraryService
from nova.system.banners import BannerStore
from nova.system.icons import IconCache
from nova.ui.library_model import GameListModel
from nova.ui.main_window import MainWindow


@dataclass
class Setup:
    window: MainWindow
    library: LibraryService
    tracking: FakeTracking
    launched: list[str] = field(default_factory=list)  # exe « lancés » (rien n'est exécuté)


@pytest.fixture
def setup(qapp, db: sqlite3.Connection, tmp_path: Path):
    tracking = FakeTracking()
    launched: list[str] = []
    launcher = GameLauncher(tracking.game_started, tracking.game_stopped, open_file=launched.append)
    library = LibraryService(
        db,
        tracking,
        IconCache(tmp_path / "icons"),
        BannerStore(tmp_path / "banners"),
        FakeClock(),
        launcher=launcher,
    )
    window = MainWindow(library, tracking)
    yield Setup(window, library, tracking, launched)
    window.close()
    window.deleteLater()


def show_offscreen(window: MainWindow) -> None:
    """« Affiche » la fenêtre sans qu'elle apparaisse à l'écran."""
    window.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen, True)
    window.show()


def test_empty_library_shows_the_invitation(setup: Setup) -> None:
    assert setup.window._pages.currentWidget() is setup.window._empty


def test_added_game_appears_and_is_selected(setup: Setup) -> None:
    setup.library.add_game("game.exe", "Mon jeu")

    assert setup.window._pages.currentWidget() is setup.window._details
    assert setup.window._list.currentIndex().data() == "Mon jeu"
    assert setup.window._details._banner.title.text() == "Mon jeu"


def test_running_game_is_marked_then_unmarked(setup: Setup) -> None:
    game = setup.library.add_game("game.exe", "Mon jeu")
    details = setup.window._details

    setup.tracking.game_started.emit(GameStarted(game.id, 1000, None))
    assert setup.window._list.currentIndex().data(GameListModel.RunningRole) is True
    assert "En cours" in details._status.text()
    assert not details._launch.isEnabled()

    setup.tracking.game_stopped.emit(GameStopped(game.id, 1000, 1600, StopReason.CLOSED, True))
    assert setup.window._list.currentIndex().data(GameListModel.RunningRole) is False
    assert details._status.text() == "Fermé"


def test_launch_is_greyed_with_a_message_when_the_path_is_unknown(setup: Setup) -> None:
    setup.library.add_game("game.exe", "Ajouté par son nom")
    details = setup.window._details

    assert not details._launch.isEnabled()
    assert not details._launch_hint.isHidden()
    assert details._launch_hint.text() == UNKNOWN_PATH


@pytest.mark.skipif(sys.platform != "win32", reason="exe Windows")
def test_launch_button_starts_the_game_and_waits_for_it(setup: Setup) -> None:
    game = setup.library.add_game("python.exe", "Jeu", sys.executable)
    details = setup.window._details
    assert details._launch.isEnabled()

    details._launch.click()
    assert setup.launched == [sys.executable]
    assert details._launch.text() == "Lancement…"

    setup.tracking.game_started.emit(GameStarted(game.id, 1000, sys.executable))
    assert details._launch.text() == "En cours"


def test_live_counter_runs_only_while_the_window_is_visible(setup: Setup) -> None:
    game = setup.library.add_game("game.exe", "Mon jeu")
    details = setup.window._details
    show_offscreen(setup.window)
    assert not details.is_counting  # aucun jeu en cours : rien à compter

    setup.tracking.game_started.emit(GameStarted(game.id, 1000, None))
    assert details.is_counting

    setup.window.hide()  # fenêtre cachée (bientôt : réduite dans le systray)
    assert not details.is_counting

    show_offscreen(setup.window)
    assert details.is_counting
    setup.tracking.game_stopped.emit(GameStopped(game.id, 1000, 1600, StopReason.CLOSED, True))
    assert not details.is_counting


def test_search_filters_the_list(setup: Setup) -> None:
    setup.library.add_game("a.exe", "Apex")
    setup.library.add_game("z.exe", "Zelda")

    setup.window._search.setText("zel")
    assert setup.window._proxy.rowCount() == 1
    assert setup.window._proxy.index(0, 0).data() == "Zelda"


# --- Étape 5 : systray et pause ---


def test_closing_the_window_hides_it_instead_of_quitting(setup: Setup) -> None:
    notified = []
    setup.window.closed_to_tray.connect(lambda: notified.append(True))
    show_offscreen(setup.window)

    setup.window.close()
    assert not setup.window.isVisible()
    assert notified == [True]

    setup.window.prepare_quit()  # « Quitter Nova »
    show_offscreen(setup.window)
    assert setup.window.close()  # cette fois, la fermeture est acceptée
    assert notified == [True]


def test_pause_banner_follows_the_tracking_state(setup: Setup) -> None:
    resume_requests = []
    setup.window.pause_requested.connect(resume_requests.append)

    setup.window.set_paused(True)
    assert not setup.window._pause_banner.isHidden()

    setup.window._pause_banner.findChild(QPushButton).click()  # « Reprendre »
    assert resume_requests == [False]
    setup.window.set_paused(False)
    assert setup.window._pause_banner.isHidden()


def test_tray_can_open_a_game_sheet(setup: Setup) -> None:
    setup.library.add_game("a.exe", "Apex")
    zelda = setup.library.add_game("z.exe", "Zelda")
    setup.window.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen, True)

    setup.window.show_game(zelda.id)
    assert setup.window.isVisible()
    assert setup.window._details._banner.title.text() == "Zelda"
