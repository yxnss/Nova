"""Petites fonctions et classes d'aide pour créer des widgets au style de Nova.

Le style dépend de propriétés lues par la feuille de style (``role`` pour les textes,
``variant`` pour les boutons) : voir ``theme/nova.qss``.
"""

from PySide6.QtCore import Qt
from PySide6.QtGui import QResizeEvent
from PySide6.QtWidgets import QLabel, QPushButton, QSizePolicy, QWidget


def set_style_property(widget: QWidget, name: str, value: str) -> None:
    """Change une propriété de style et redessine le widget avec son nouveau style."""
    if widget.property(name) == value:
        return  # rien à faire : évite de recalculer le style à chaque seconde
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


class ElidedLabel(QLabel):
    """Texte sur une seule ligne, raccourci au milieu (« C:\\Jeux\\…\\jeu.exe ») s'il est
    trop long. Le texte complet reste visible en infobulle."""

    def __init__(self, role: str | None = None) -> None:
        super().__init__()
        self._full_text = ""
        if role:
            self.setProperty("role", role)
        # Largeur « ignorée » : le libellé prend la place disponible sans l'imposer.
        self.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)

    def set_full_text(self, text: str) -> None:
        self._full_text = text
        self.setToolTip(text)
        self._elide()

    def resizeEvent(self, event: QResizeEvent) -> None:
        super().resizeEvent(event)
        self._elide()

    def _elide(self) -> None:
        metrics = self.fontMetrics()
        self.setText(
            metrics.elidedText(self._full_text, Qt.TextElideMode.ElideMiddle, self.width())
        )
