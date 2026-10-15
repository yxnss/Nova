"""Thème de Nova : style Fusion, palette sombre et feuille de style QSS."""

import re
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QFont, QPalette
from PySide6.QtWidgets import QApplication

from nova.ui.theme.palette import COLORS

_QSS_FILE = Path(__file__).with_name("nova.qss")
_COLOR_NAME = re.compile(r"@([a-z_]+)")


def stylesheet() -> str:
    """Feuille de style, avec chaque « @nom » remplacé par la couleur de la palette."""
    template = _QSS_FILE.read_text(encoding="utf-8")
    return _COLOR_NAME.sub(lambda match: COLORS[match.group(1)], template)


def apply_theme(app: QApplication) -> None:
    # Fusion : style de base prévisible, qui respecte bien les feuilles de style
    # (le style natif de Windows 11 en ignore une partie).
    app.setStyle("Fusion")
    # Barre de titre sombre, même si Windows est réglé en mode clair.
    app.styleHints().setColorScheme(Qt.ColorScheme.Dark)

    font = QFont()
    font.setFamilies(["Segoe UI Variable Text", "Segoe UI"])
    font.setPointSize(10)
    app.setFont(font)

    # Palette de base pour les éléments que la feuille de style ne couvre pas.
    palette = QPalette()
    roles = {
        QPalette.ColorRole.Window: "background",
        QPalette.ColorRole.Base: "card",
        QPalette.ColorRole.AlternateBase: "panel",
        QPalette.ColorRole.Button: "card",
        QPalette.ColorRole.WindowText: "text",
        QPalette.ColorRole.Text: "text",
        QPalette.ColorRole.ButtonText: "text",
        QPalette.ColorRole.PlaceholderText: "text_muted",
        QPalette.ColorRole.Highlight: "accent",
        QPalette.ColorRole.HighlightedText: "text",
        QPalette.ColorRole.ToolTipBase: "card",
        QPalette.ColorRole.ToolTipText: "text",
    }
    for role, name in roles.items():
        palette.setColor(role, QColor(COLORS[name]))
    app.setPalette(palette)
    app.setStyleSheet(stylesheet())
