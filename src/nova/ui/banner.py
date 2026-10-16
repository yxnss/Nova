"""Grande bannière en haut de la fiche d'un jeu.

Image choisie par l'utilisateur, ou bannière dessinée par Nova dans l'esprit du
logo : ciel nuit vers violet, quelques étoiles et une planète à anneau. L'icône du
jeu s'affiche à côté du titre. Le rendu est mis en cache : il n'est recalculé que
si la taille ou le contenu change, jamais à chaque affichage.
"""

from pathlib import Path

from PySide6.QtCore import QPoint, QPointF, QRect, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import (
    QColor,
    QContextMenuEvent,
    QIcon,
    QLinearGradient,
    QPainter,
    QPaintEvent,
    QPen,
    QPixmap,
    QRadialGradient,
    QResizeEvent,
)
from PySide6.QtWidgets import QHBoxLayout, QLabel, QMenu, QSizePolicy, QVBoxLayout, QWidget

from nova.ui.theme.palette import COLORS
from nova.ui.widgets import make_label

RATIO = 3.2  # largeur / hauteur, proche des bannières de bibliothèque de Steam
MIN_HEIGHT, MAX_HEIGHT = 190, 330
TITLE_ICON_SIZE = 44

# Étoiles de la bannière par défaut : position (fraction de la largeur et de la
# hauteur) et rayon en pixels. Fixes, pour que la bannière soit toujours la même.
_STARS = [
    (0.06, 0.18, 1.2), (0.14, 0.42, 0.8), (0.22, 0.12, 1.0), (0.31, 0.30, 0.7),
    (0.38, 0.08, 1.3), (0.47, 0.22, 0.8), (0.55, 0.10, 1.0), (0.61, 0.36, 0.7),
    (0.68, 0.06, 0.9), (0.93, 0.14, 1.1), (0.97, 0.52, 0.8), (0.88, 0.80, 0.7),
]  # fmt: skip


def _color(name: str, alpha: int = 255) -> QColor:
    color = QColor(COLORS[name])
    color.setAlpha(alpha)
    return color


class Banner(QWidget):
    change_requested = Signal()
    reset_requested = Signal()

    def __init__(self) -> None:
        super().__init__()
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setFixedHeight(MIN_HEIGHT)
        self._image_path: Path | None = None
        self._image: QPixmap | None = None  # image personnalisée, lue une seule fois
        self._rendered: QPixmap | None = None  # bannière complète à la taille actuelle

        layout = QVBoxLayout(self)
        layout.setContentsMargins(32, 0, 32, 14)
        layout.addStretch()
        title_row = QHBoxLayout()
        title_row.setSpacing(14)
        self.icon = QLabel()
        self.icon.setFixedSize(TITLE_ICON_SIZE, TITLE_ICON_SIZE)
        self.title = make_label(role="bannerTitle")
        title_row.addWidget(self.icon)
        title_row.addWidget(self.title, 1)
        layout.addLayout(title_row)

    @property
    def has_custom_image(self) -> bool:
        return self._image is not None

    def set_content(self, title: str, image_path: Path | None, icon: QIcon | None) -> None:
        self.title.setText(title)
        self._set_icon(icon)
        if image_path != self._image_path:
            self._image_path = image_path
            image = QPixmap(str(image_path)) if image_path else None
            self._image = image if image is not None and not image.isNull() else None
            self._rendered = None
            self.update()

    def _set_icon(self, icon: QIcon | None) -> None:
        if icon is None:
            self.icon.hide()
            return
        # On part de la plus grande taille disponible : certaines icônes ne font que
        # 32 px et QIcon ne les agrandit pas tout seul.
        pixmap = icon.pixmap(256, 256).scaled(
            TITLE_ICON_SIZE,
            TITLE_ICON_SIZE,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        self.icon.setPixmap(pixmap)
        self.icon.show()

    # --- Taille : la hauteur suit la largeur, dans des limites raisonnables ---

    def resizeEvent(self, event: QResizeEvent) -> None:
        super().resizeEvent(event)
        self._rendered = None
        # Changer sa propre hauteur pendant un redimensionnement perturbe la mise en
        # page de Qt (le titre resterait mal placé) : on reporte donc l'ajustement
        # juste après l'événement en cours.
        QTimer.singleShot(0, self._fit_height)

    def _fit_height(self) -> None:
        height = max(MIN_HEIGHT, min(MAX_HEIGHT, round(self.width() / RATIO)))
        if height != self.height():
            self.setFixedHeight(height)

    # --- Dessin ---

    def paintEvent(self, event: QPaintEvent) -> None:
        if self._rendered is None or self._rendered.size() != self.size():
            self._rendered = self._render()
        QPainter(self).drawPixmap(0, 0, self._rendered)

    def _render(self) -> QPixmap:
        pixmap = QPixmap(self.size())
        pixmap.fill(_color("background"))
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        rect = QRectF(pixmap.rect())
        if self._image is not None:
            self._paint_cover(painter, pixmap.rect())
        else:
            self._paint_default(painter, rect)

        # Fondu vers la couleur de fond : le titre reste lisible et la bannière se
        # fond dans la fiche, quelle que soit l'image.
        fade = QLinearGradient(0, rect.height() * 0.35, 0, rect.height())
        fade.setColorAt(0, _color("background", 0))
        fade.setColorAt(1, _color("background", 235))
        painter.fillRect(rect, fade)
        painter.end()
        return pixmap

    def _paint_cover(self, painter: QPainter, rect: QRect) -> None:
        """Image qui remplit toute la zone sans être déformée (le surplus est rogné)."""
        scaled = self._image.scaled(
            rect.size(),
            Qt.AspectRatioMode.KeepAspectRatioByExpanding,
            Qt.TransformationMode.SmoothTransformation,
        )
        offset = QPoint(
            (scaled.width() - rect.width()) // 2, (scaled.height() - rect.height()) // 2
        )
        painter.drawPixmap(rect, scaled, QRect(offset, rect.size()))

    def _paint_default(self, painter: QPainter, rect: QRectF) -> None:
        width, height = rect.width(), rect.height()

        # Ciel : nuit en haut à gauche, violet électrique en bas à droite, comme le logo.
        sky = QLinearGradient(rect.topLeft(), rect.bottomRight())
        sky.setColorAt(0.0, _color("night"))
        sky.setColorAt(0.6, _color("deep_violet"))
        sky.setColorAt(1.0, _color("accent"))
        painter.fillRect(rect, sky)

        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(_color("text", 150))
        for x, y, radius in _STARS:
            painter.drawEllipse(QPointF(x * width, y * height), radius, radius)

        center = QPointF(width * 0.8, height * 0.42)
        planet_radius = height * 0.27

        glow = QRadialGradient(center, planet_radius * 3)
        glow.setColorAt(0, _color("lilac", 80))
        glow.setColorAt(1, _color("lilac", 0))
        painter.fillRect(rect, glow)

        # Anneau en deux moitiés : celle de derrière, puis la planète, puis celle de
        # devant. Ça donne l'impression que l'anneau entoure vraiment la planète.
        ring = QRectF(
            -planet_radius * 1.9, -planet_radius * 0.42, planet_radius * 3.8, planet_radius * 0.84
        )
        ring_pen = QPen(_color("lilac", 210), max(2.0, planet_radius * 0.11))
        ring_pen.setCapStyle(Qt.PenCapStyle.RoundCap)

        def draw_ring_half(start_degrees: int) -> None:
            painter.save()
            painter.translate(center)
            painter.rotate(-14)
            painter.setPen(ring_pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawArc(ring, start_degrees * 16, 180 * 16)  # Qt compte en 1/16 de degré
            painter.restore()

        draw_ring_half(0)  # moitié haute, derrière la planète
        body = QRadialGradient(
            center, planet_radius, center - QPointF(planet_radius * 0.4, planet_radius * 0.4)
        )
        body.setColorAt(0.0, _color("lilac"))
        body.setColorAt(0.5, _color("accent"))
        body.setColorAt(1.0, _color("deep_violet"))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(body)
        painter.drawEllipse(center, planet_radius, planet_radius)
        draw_ring_half(180)  # moitié basse, devant la planète

    # --- Menu du clic droit ---

    def contextMenuEvent(self, event: QContextMenuEvent) -> None:
        menu = QMenu(self)
        change = menu.addAction("Changer la bannière…")
        reset = menu.addAction("Rétablir la bannière par défaut")
        reset.setEnabled(self.has_custom_image)
        chosen = menu.exec(event.globalPos())
        if chosen is change:
            self.change_requested.emit()
        elif chosen is reset:
            self.reset_requested.emit()
