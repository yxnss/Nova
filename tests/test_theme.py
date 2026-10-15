"""Tests du thème : chaque couleur utilisée par la feuille de style existe dans la palette."""

import re

from PySide6.QtCore import Qt
from PySide6.QtGui import QPalette

from nova.ui.theme import _QSS_FILE, apply_theme, stylesheet
from nova.ui.theme.palette import COLORS


def test_every_color_used_by_the_stylesheet_is_defined() -> None:
    used = set(re.findall(r"@([a-z_]+)", _QSS_FILE.read_text(encoding="utf-8")))
    assert used, "la feuille de style devrait utiliser la palette"
    assert used <= COLORS.keys(), f"couleurs inconnues : {sorted(used - COLORS.keys())}"


def test_stylesheet_contains_real_colors_only() -> None:
    css = stylesheet()
    assert "@" not in css
    assert COLORS["accent"] in css


def test_palette_colors_are_hex_codes() -> None:
    assert all(re.fullmatch(r"#[0-9A-F]{6}", value) for value in COLORS.values())


def test_theme_applies_to_the_application(qapp) -> None:
    apply_theme(qapp)
    background = qapp.palette().color(QPalette.ColorRole.Window).name().upper()
    assert background == COLORS["background"]
    assert qapp.styleHints().colorScheme() == Qt.ColorScheme.Dark
    assert COLORS["accent"] in qapp.styleSheet()
