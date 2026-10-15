"""Icônes dessinées par Nova (aucun fichier image nécessaire)."""

from functools import cache

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QIcon, QPainter, QPen, QPixmap

from nova.ui.theme.palette import COLORS


@cache
def generic_game_icon() -> QIcon:
    """Icône des jeux dont l'icône est inconnue : une petite planète, clin d'œil au logo."""
    size = 64
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QColor(COLORS["border"]))
    painter.drawRoundedRect(QRectF(0, 0, size, size), 12, 12)
    painter.setBrush(QColor(COLORS["accent"]))
    painter.drawEllipse(QRectF(20, 20, 24, 24))
    ring = QPen(QColor(COLORS["lilac"]), 4)
    painter.setPen(ring)
    painter.setBrush(Qt.BrushStyle.NoBrush)
    painter.drawEllipse(QRectF(8, 25, 48, 14))
    painter.end()
    return QIcon(pixmap)
