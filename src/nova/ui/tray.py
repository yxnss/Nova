"""Icône de Nova dans la zone de notifications (systray), avec un menu à la Steam.

- Clic gauche : ouvre la fenêtre de Nova.
- Clic droit : derniers jeux joués (avec leur icône), « Ouvrir Nova », « Paramètres »,
  pause du suivi et « Quitter Nova ».
- Pendant la pause, l'icône est grisée avec un petit badge pause.
"""

from collections.abc import Callable
from dataclasses import dataclass

from PySide6.QtCore import QObject, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QIcon, QImage, QPainter, QPixmap
from PySide6.QtWidgets import QMenu, QSystemTrayIcon

from nova.system.paths import asset_path
from nova.ui.theme.palette import COLORS

TRAY_SIZES = (16, 20, 24, 32, 40, 48, 64)  # Windows choisit selon l'échelle de l'écran
RECENT_GAMES = 5


@dataclass(frozen=True)
class RecentGame:
    game_id: int
    name: str
    icon: QIcon
    running: bool


def tray_icon(logo: QPixmap, paused: bool) -> QIcon:
    """Logo décliné en plusieurs tailles, en version normale ou « en pause »."""
    icon = QIcon()
    for size in TRAY_SIZES:
        pixmap = logo.scaled(
            size,
            size,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        icon.addPixmap(paused_version(pixmap) if paused else pixmap)
    return icon


def paused_version(pixmap: QPixmap) -> QPixmap:
    """Logo grisé, avec un badge pause ambré en bas à droite."""
    image = pixmap.toImage().convertToFormat(QImage.Format.Format_ARGB32)
    for y in range(image.height()):
        for x in range(image.width()):
            color = image.pixelColor(x, y)
            gray = (color.red() * 11 + color.green() * 16 + color.blue() * 5) // 32
            image.setPixelColor(x, y, QColor(gray, gray, gray, color.alpha()))

    size = image.width()
    painter = QPainter(image)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setPen(Qt.PenStyle.NoPen)
    badge = size * 0.5
    painter.setBrush(QColor(COLORS["paused"]))
    painter.drawEllipse(QRectF(size - badge, size - badge, badge, badge))
    painter.setBrush(QColor(COLORS["night"]))  # deux barres sombres : le symbole pause
    bar_width, bar_height = badge * 0.16, badge * 0.46
    top = size - badge / 2 - bar_height / 2
    for offset in (-0.14, 0.14):
        left = size - badge / 2 + offset * badge - bar_width / 2
        painter.drawRect(QRectF(left, top, bar_width, bar_height))
    painter.end()
    return QPixmap.fromImage(image)


class TrayIcon(QObject):
    open_requested = Signal()
    game_requested = Signal(int)  # ouvrir la fiche de ce jeu
    settings_requested = Signal()
    pause_requested = Signal(bool)  # True : mettre en pause ; False : reprendre
    quit_requested = Signal()

    def __init__(
        self, recent_games: Callable[[], list[RecentGame]], parent: QObject | None = None
    ) -> None:
        super().__init__(parent)
        logo = QPixmap(str(asset_path("logo.png")))
        self._icons = {False: tray_icon(logo, paused=False), True: tray_icon(logo, paused=True)}
        self._recent_games = recent_games
        self._paused = False
        self._running_names: list[str] = []

        # Le menu est reconstruit juste avant chaque affichage : il reflète toujours
        # les derniers jeux et l'état de la pause, sans mise à jour en continu.
        self.menu = QMenu()
        self.menu.aboutToShow.connect(self.rebuild_menu)
        self._tray = QSystemTrayIcon(self._icons[False], self)
        self._tray.setContextMenu(self.menu)
        self._tray.activated.connect(self._on_activated)
        self._update_tooltip()

    def show(self) -> None:
        self._tray.show()

    def hide(self) -> None:
        self._tray.hide()

    def set_paused(self, paused: bool) -> None:
        self._paused = paused
        self._tray.setIcon(self._icons[paused])
        self._update_tooltip()

    def set_running_games(self, names: list[str]) -> None:
        self._running_names = names
        self._update_tooltip()

    def notify(self, title: str, text: str) -> None:
        self._tray.showMessage(title, text, self._icons[False], 6000)

    @property
    def tooltip(self) -> str:
        return self._tray.toolTip()

    def _on_activated(self, reason: QSystemTrayIcon.ActivationReason) -> None:
        if reason == QSystemTrayIcon.ActivationReason.Trigger:  # clic gauche
            self.open_requested.emit()

    def _update_tooltip(self) -> None:
        if self._paused:
            text = "Nova — suivi en pause"
        elif self._running_names:
            text = f"Nova — {', '.join(self._running_names)} en cours"
        else:
            text = "Nova"
        self._tray.setToolTip(text)

    def rebuild_menu(self) -> None:
        self.menu.clear()
        games = self._recent_games()[:RECENT_GAMES]
        for game in games:
            label = f"{game.name}   ●  en cours" if game.running else game.name
            action = self.menu.addAction(game.icon, label)
            action.triggered.connect(
                lambda _=False, game_id=game.game_id: self.game_requested.emit(game_id)
            )
        if games:
            self.menu.addSeparator()

        self.menu.addAction("Ouvrir Nova").triggered.connect(self.open_requested)
        self.menu.addAction("Paramètres").triggered.connect(self.settings_requested)
        self.menu.addSeparator()
        pause_text = "Reprendre le suivi" if self._paused else "Mettre en pause le suivi"
        pause = self.menu.addAction(pause_text)
        pause.triggered.connect(lambda: self.pause_requested.emit(not self._paused))
        self.menu.addSeparator()
        self.menu.addAction("Quitter Nova").triggered.connect(self.quit_requested)
