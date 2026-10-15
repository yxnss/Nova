"""Petites fonctions d'aide pour créer des widgets au style de Nova.

Le style dépend de propriétés lues par la feuille de style (``role`` pour les textes,
``variant`` pour les boutons) : voir ``theme/nova.qss``.
"""

from PySide6.QtWidgets import QLabel, QPushButton, QWidget


def set_style_property(widget: QWidget, name: str, value: str) -> None:
    """Change une propriété de style et redessine le widget avec son nouveau style."""
    widget.setProperty(name, value)
    widget.style().unpolish(widget)
    widget.style().polish(widget)


def make_label(text: str = "", role: str | None = None, wrap: bool = False) -> QLabel:
    label = QLabel(text)
    if role:
        label.setProperty("role", role)
    label.setWordWrap(wrap)
    return label


def make_button(text: str, variant: str | None = None) -> QPushButton:
    button = QPushButton(text)
    if variant:
        button.setProperty("variant", variant)
    return button
