"""Barre de titre intégrée à la fenêtre principale, à la manière de Steam.

La barre native de Windows est retirée : la barre latérale et la bannière montent
jusqu'en haut de la fenêtre, et Nova dessine ses propres boutons (réduire, agrandir,
fermer). La bande du haut sert toujours à déplacer la fenêtre, et Windows garde ses
comportements habituels (aimantation aux bords, double-clic pour agrandir,
redimensionnement par les bords), car c'est lui qui gère ces zones (voir
``nova.system.windows``).
"""

import sys

from PySide6.QtCore import QEvent, QObject, QPoint, QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QEnterEvent, QGuiApplication, QPainter, QPaintEvent, QPen
from PySide6.QtWidgets import (
    QAbstractButton,
    QAbstractItemView,
    QApplication,
    QComboBox,
    QHBoxLayout,
    QLineEdit,
    QWidget,
)

from nova.system import windows
from nova.ui.theme.palette import COLORS

CAPTION_HEIGHT = 40  # bande du haut qui sert à déplacer la fenêtre
RESIZE_BORDER = 6  # épaisseur des bords qui servent à redimensionner
BUTTON_WIDTH = 46
GLYPH_SIZE = 10  # taille des petits dessins des boutons

# Sous ces éléments, un clic dans la bande du haut doit leur revenir au lieu de
# déplacer la fenêtre.
_INTERACTIVE = (QAbstractButton, QLineEdit, QComboBox, QAbstractItemView)


def hit_test(x: float, y: float, width: int, height: int, maximized: bool, on_control: bool) -> int:
    """Indique à Windows ce qui se trouve sous la souris : un bord, la barre de titre ou le contenu.

    ``x`` et ``y`` sont relatifs au coin haut gauche de la fenêtre. Une fenêtre agrandie
    n'a pas de bords à tirer.
    """
    if not maximized:
        left, right = x < RESIZE_BORDER, x >= width - RESIZE_BORDER
        top, bottom = y < RESIZE_BORDER, y >= height - RESIZE_BORDER
        if top and left:
            return windows.HTTOPLEFT
        if top and right:
            return windows.HTTOPRIGHT
        if bottom and left:
            return windows.HTBOTTOMLEFT
        if bottom and right:
            return windows.HTBOTTOMRIGHT
        if left:
            return windows.HTLEFT
        if right:
            return windows.HTRIGHT
        if top:
            return windows.HTTOP
        if bottom:
            return windows.HTBOTTOM
    if y < CAPTION_HEIGHT and not on_control:
        return windows.HTCAPTION
    return windows.HTCLIENT


def custom_frame_supported() -> bool:
    """Vrai sous Windows avec un vrai affichage (pas en mode ``offscreen``)."""
    return sys.platform == "win32" and QGuiApplication.platformName() == "windows"


class WindowButton(QAbstractButton):
    """Bouton plat de la barre de titre : un petit dessin fin, un fond discret au survol."""

    def __init__(self, kind: str, tooltip: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.kind = kind  # "minimize", "maximize", "restore" ou "close"
        self.hovered = False
        self.setToolTip(tooltip)
        self.setFixedSize(BUTTON_WIDTH, CAPTION_HEIGHT)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setAttribute(Qt.WidgetAttribute.WA_Hover)

    def enterEvent(self, event: QEnterEvent) -> None:
        self.hovered = True
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event: QEvent) -> None:
        self.hovered = False
        self.update()
        super().leaveEvent(event)

    def paintEvent(self, event: QPaintEvent) -> None:
        painter = QPainter(self)
        closing = self.kind == "close"
        if self.hovered or self.isDown():
            if closing:
                background = QColor(COLORS["window_close"])
                if self.isDown():
                    background = background.darker(115)
            else:
                background = QColor(COLORS["text"])
                background.setAlpha(14 if self.isDown() else 22)
            painter.fillRect(self.rect(), background)

        if closing and (self.hovered or self.isDown()):
            color = QColor("#FFFFFF")
        elif self.hovered:
            color = QColor(COLORS["text"])
        elif self.window().isActiveWindow():
            color = QColor(COLORS["text_secondary"])
        else:
            color = QColor(COLORS["text_muted"])
        pen = QPen(color, 1.0)
        pen.setCapStyle(Qt.PenCapStyle.FlatCap)
        pen.setJoinStyle(Qt.PenJoinStyle.MiterJoin)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)

        # Carré de 10 px centré, aligné sur la grille des pixels pour un trait net.
        left = (self.width() - GLYPH_SIZE) // 2 + 0.5
        top = (self.height() - GLYPH_SIZE) // 2 + 0.5
        size = GLYPH_SIZE - 1
        if self.kind == "minimize":
            middle = top + size / 2
            painter.drawLine(QPointF(left, middle), QPointF(left + size, middle))
        elif self.kind == "maximize":
            painter.drawRect(QRectF(left, top, size, size))
        elif self.kind == "restore":
            # Deux fenêtres superposées : celle de devant en bas à gauche.
            front = QRectF(left, top + 2, size - 2, size - 2)
            painter.drawRect(front)
            painter.drawPolyline(
                [
                    QPointF(left + 2, top + 2),
                    QPointF(left + 2, top),
                    QPointF(left + size, top),
                    QPointF(left + size, top + size - 2),
                    QPointF(left + size - 2, top + size - 2),
                ]
            )
        else:
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            painter.drawLine(QPointF(left, top), QPointF(left + size, top + size))
            painter.drawLine(QPointF(left + size, top), QPointF(left, top + size))
        painter.end()


class WindowButtons(QWidget):
    """Les trois boutons du coin haut droit : réduire, agrandir ou restaurer, fermer."""

    def __init__(self, window: QWidget) -> None:
        super().__init__(window)
        self.setObjectName("windowButtons")
        self._window = window
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        self.minimize = WindowButton("minimize", "Réduire")
        self.maximize = WindowButton("maximize", "Agrandir")
        self.close = WindowButton("close", "Fermer")
        self.minimize.clicked.connect(window.showMinimized)
        self.maximize.clicked.connect(self._toggle_maximized)
        self.close.clicked.connect(window.close)
        for button in (self.minimize, self.maximize, self.close):
            layout.addWidget(button)
        self.adjustSize()

    def _toggle_maximized(self) -> None:
        if self._window.isMaximized():
            self._window.showNormal()
        else:
            self._window.showMaximized()

    def update_state(self) -> None:
        maximized = self._window.isMaximized()
        self.maximize.kind = "restore" if maximized else "maximize"
        self.maximize.setToolTip("Restaurer" if maximized else "Agrandir")
        for button in (self.minimize, self.maximize, self.close):
            button.hovered = button.underMouse()
            button.update()


class WindowFrame(QObject):
    """Retire la barre de titre native d'une fenêtre et place les boutons de Nova."""

    def __init__(self, window: QWidget) -> None:
        super().__init__(window)
        self._window = window
        self._native_ready = False
        self.enabled = custom_frame_supported()
        self.buttons = WindowButtons(window)
        if self.enabled:
            window.setWindowFlag(Qt.WindowType.FramelessWindowHint)
        else:
            self.buttons.hide()  # tests en mode offscreen : la barre native reste
        window.installEventFilter(self)

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:
        kind = event.type()
        if kind == QEvent.Type.Show and self.enabled and not self._native_ready:
            windows.prepare_custom_title_bar(int(self._window.winId()), COLORS["border"])
            self._native_ready = True
        if kind in (QEvent.Type.Show, QEvent.Type.Resize):
            self.buttons.move(self._window.width() - self.buttons.width(), 0)
            self.buttons.raise_()  # toujours au-dessus de la bannière
        elif kind in (QEvent.Type.WindowStateChange, QEvent.Type.ActivationChange):
            self.buttons.update_state()
        return False

    def native_event(self, message: int) -> tuple[bool, int] | None:
        """Réponses aux messages qui décrivent le cadre ; ``None`` pour laisser faire Qt."""
        if not self._native_ready:
            return None
        msg = windows.read_message(message)
        if msg.message == windows.WM_NCCALCSIZE:
            windows.fill_client_area(msg)
            return True, 0
        if msg.message == windows.WM_NCHITTEST:
            x, y = windows.cursor_offset(msg)
            ratio = self._window.devicePixelRatioF()  # pixels physiques → pixels Qt
            x, y = x / ratio, y / ratio
            child = self._window.childAt(QPoint(int(x), int(y)))
            area = hit_test(
                x,
                y,
                self._window.width(),
                self._window.height(),
                windows.is_maximized(msg.hWnd),
                _is_interactive(child),
            )
            return True, area
        return None


def _is_interactive(widget: QWidget | None) -> bool:
    while widget is not None:
        if isinstance(widget, _INTERACTIVE):
            return True
        widget = widget.parentWidget()
    return False


def blend_native_title_bars(app: QApplication) -> None:
    """Colore la barre de titre native des autres fenêtres (paramètres, messages) comme leur fond.

    Elles gardent leur barre Windows, mais sans démarcation avec leur contenu (Windows 11).
    La couleur est posée quand la fenêtre prend le focus, sans surveiller chaque événement.
    """
    if not custom_frame_supported():
        return

    def on_focus_window_changed(window) -> None:
        if window is None or window.flags() & Qt.WindowType.FramelessWindowHint:
            return
        if window.type() in (Qt.WindowType.Dialog, Qt.WindowType.Window):
            windows.set_caption_color(int(window.winId()), COLORS["background"])

    app.focusWindowChanged.connect(on_focus_window_changed)
