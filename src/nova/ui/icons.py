"""Icônes dessinées par Nova (aucun fichier image nécessaire)."""

from functools import cache

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QIcon, QPainter, QPainterPath, QPen, QPixmap, QTransform

from nova.ui.theme.palette import COLORS


@cache
def gear_icon() -> QIcon:
    """Engrenage plat, dans le même style que la flèche de tri : gris, plus clair au survol."""
    icon = QIcon()
    icon.addPixmap(_gear(COLORS["text_secondary"]), QIcon.Mode.Normal)
    icon.addPixmap(_gear(COLORS["text"]), QIcon.Mode.Active)  # survol
    return icon


def _gear(color: str, size: int = 64) -> QPixmap:
    center = QPointF(size / 2, size / 2)
    body, tooth_length, tooth_width, hole = size * 0.30, size * 0.14, size * 0.17, size * 0.13

    shape = QPainterPath()
    shape.addEllipse(center, body, body)
    for step in range(8):  # huit dents réparties autour du disque
        tooth = QPainterPath()
        tooth.addRoundedRect(
            QRectF(-tooth_width / 2, -(body + tooth_length), tooth_width, tooth_length + 2), 2, 2
        )
        turn = QTransform().translate(center.x(), center.y()).rotate(step * 45)
        shape = shape.united(turn.map(tooth))
    center_hole = QPainterPath()
    center_hole.addEllipse(center, hole, hole)
    shape = shape.subtracted(center_hole)

    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.fillPath(shape, QColor(color))
    painter.end()
    return pixmap


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
