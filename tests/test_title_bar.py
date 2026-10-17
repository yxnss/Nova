"""Tests de la barre de titre intégrée : zones de la fenêtre et boutons."""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QWidget

from nova.system import windows
from nova.ui.title_bar import CAPTION_HEIGHT, RESIZE_BORDER, WindowButtons, hit_test

WIDTH, HEIGHT = 1100, 680


def zone(x: float, y: float, maximized: bool = False, on_control: bool = False) -> int:
    return hit_test(x, y, WIDTH, HEIGHT, maximized, on_control)


def test_edges_and_corners_resize_the_window() -> None:
    assert zone(1, 1) == windows.HTTOPLEFT
    assert zone(WIDTH - 1, HEIGHT - 1) == windows.HTBOTTOMRIGHT
    assert zone(500, 1) == windows.HTTOP
    assert zone(1, 300) == windows.HTLEFT
    assert zone(WIDTH - 1, 300) == windows.HTRIGHT
    assert zone(500, HEIGHT - 1) == windows.HTBOTTOM


def test_top_band_moves_the_window_except_over_a_control() -> None:
    assert zone(500, RESIZE_BORDER + 5) == windows.HTCAPTION
    assert zone(500, RESIZE_BORDER + 5, on_control=True) == windows.HTCLIENT
    assert zone(500, CAPTION_HEIGHT + 1) == windows.HTCLIENT


def test_maximized_window_has_no_edges_to_drag() -> None:
    assert zone(1, 1, maximized=True) == windows.HTCAPTION
    assert zone(1, 300, maximized=True) == windows.HTCLIENT


def test_maximize_button_becomes_restore(qapp) -> None:
    window = QWidget()
    buttons = WindowButtons(window)
    assert buttons.maximize.kind == "maximize"
    window.setWindowState(Qt.WindowState.WindowMaximized)
    buttons.update_state()
    assert buttons.maximize.kind == "restore"
    assert buttons.maximize.toolTip() == "Restaurer"
    window.deleteLater()
