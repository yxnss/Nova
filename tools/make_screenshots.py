"""Génère les captures du README dans ``docs/screenshots``, sans rien afficher à l'écran.

Les jeux sont fictifs et leurs icônes dessinées ici : aucune image protégée ni aucune
donnée personnelle dans le dépôt. Les données vont dans un dossier temporaire.

    .venv\\Scripts\\python tools\\make_screenshots.py
"""

import os
import tempfile
import time
from pathlib import Path

os.environ["NOVA_DATA_DIR"] = tempfile.mkdtemp(prefix="nova-captures-")

from PySide6.QtCore import QObject, QPointF, QRectF, Qt, Signal  # noqa: E402
from PySide6.QtGui import QColor, QFont, QImage, QLinearGradient, QPainter  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from nova.core.events import GameStarted  # noqa: E402
from nova.data.database import connect  # noqa: E402
from nova.data.sessions_repo import SessionRepository  # noqa: E402
from nova.services.library import LibraryService  # noqa: E402
from nova.system.banners import BannerStore  # noqa: E402
from nova.system.icons import IconCache  # noqa: E402
from nova.system.paths import banners_dir, database_path, icons_dir  # noqa: E402
from nova.ui import game_details  # noqa: E402
from nova.ui.icons import generic_game_icon  # noqa: E402
from nova.ui.main_window import MainWindow  # noqa: E402
from nova.ui.theme import apply_theme  # noqa: E402
from nova.ui.tray import RecentGame, TrayIcon  # noqa: E402

OUT = Path(__file__).resolve().parents[1] / "docs" / "screenshots"
HOUR = 3600

# (nom, exe, initiale, deux couleurs de l'icône, sessions : (il y a combien d'heures, durée en h))
GAMES = [
    ("Odyssée stellaire", "Odyssey", "O", "#2E6BFF", "#7FD3FF", [(30, 3.5), (80, 2), (200, 6)]),
    ("Les Ruines d'Aldaria", "Aldaria", "A", "#8A4B12", "#F2B33D", [(5, 1.5), (60, 4), (300, 12)]),
    ("Néon Drift", "NeonDrift", "N", "#D12E8A", "#FF8AD8", [(26, 0.8), (130, 1.2)]),
    ("Cartographe", "Cartographe", "C", "#1E7A5A", "#7CE0B5", [(400, 2)]),
    ("Forge et Givre", "ForgeEtGivre", "F", "#3B4A6B", "#B9C7E6", []),
]


class DemoTracking(QObject):
    """Remplace le thread de suivi : les captures n'ont pas besoin de scanner le PC."""

    ready = Signal(object)
    game_started = Signal(object)
    game_stopped = Signal(object)
    game_path_found = Signal(int, str)
    game_removed = Signal(int)
    paused_changed = Signal(bool)

    def reload_games(self) -> None: ...

    def remove_game(self, game_id: int) -> None: ...


def draw_icon(path: Path, letter: str, dark: str, light: str) -> None:
    image = QImage(128, 128, QImage.Format.Format_ARGB32)
    image.fill(Qt.GlobalColor.transparent)
    painter = QPainter(image)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    gradient = QLinearGradient(QPointF(0, 0), QPointF(128, 128))
    gradient.setColorAt(0, QColor(light))
    gradient.setColorAt(1, QColor(dark))
    painter.setBrush(gradient)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.drawRoundedRect(QRectF(0, 0, 128, 128), 24, 24)
    painter.setPen(QColor("#FFFFFF"))
    painter.setFont(QFont("Segoe UI", 64, QFont.Weight.Bold))
    painter.drawText(QRectF(0, 0, 128, 128), Qt.AlignmentFlag.AlignCenter, letter)
    painter.end()
    image.save(str(path))


def draw_landscape(path: Path) -> Path:
    """Bannière personnalisée de démonstration : un paysage au crépuscule."""
    image = QImage(2400, 760, QImage.Format.Format_RGB32)
    painter = QPainter(image)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    sky = QLinearGradient(QPointF(0, 0), QPointF(0, 760))
    sky.setColorAt(0, QColor("#1B2A5C"))
    sky.setColorAt(0.55, QColor("#C2477A"))
    sky.setColorAt(1, QColor("#F2A65A"))
    painter.fillRect(image.rect(), sky)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QColor("#FFE2A8"))
    painter.drawEllipse(QPointF(1750, 470), 120, 120)
    for color, points in [
        (
            "#3A1F4D",
            [(0, 760), (0, 520), (500, 360), (900, 560), (1400, 330), (2400, 600), (2400, 760)],
        ),
        (
            "#1E1030",
            [(0, 760), (0, 640), (700, 520), (1300, 680), (1900, 540), (2400, 700), (2400, 760)],
        ),
    ]:
        painter.setBrush(QColor(color))
        painter.drawPolygon([QPointF(x, y) for x, y in points])
    painter.end()
    image.save(str(path))
    return path


def capture(widget, name: str) -> None:
    widget.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen, True)
    widget.show()
    for _ in range(4):
        QApplication.processEvents()
    widget.grab().save(str(OUT / name))
    print("capture :", OUT / name)


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    app = QApplication([])
    apply_theme(app)
    conn = connect(database_path())
    tracking = DemoTracking()
    library = LibraryService(conn, tracking, IconCache(icons_dir()), BannerStore(banners_dir()))
    sessions = SessionRepository(conn)
    now = time.time()
    games = []
    for name, exe, letter, dark, light, played in GAMES:
        game = library.add_game(f"{exe}.exe", name, rf"D:\Jeux\{name}\{exe}.exe")
        draw_icon(icons_dir() / f"{game.id}.png", letter, dark, light)
        for hours_ago, length in played:
            start = now - hours_ago * HOUR
            sessions.close_session(
                sessions.open_session(game.id, start, start), start + length * HOUR
            )
        games.append(game)
    library.set_banner(games[1].id, str(draw_landscape(Path(tempfile.mkdtemp()) / "paysage.png")))

    # Les exe des jeux fictifs n'existent pas : pour ces captures seulement, on considère
    # qu'ils peuvent être lancés (sinon « Lancer » serait grisé avec « Fichier introuvable »).
    game_details.launch_problem = lambda game: None
    window = MainWindow(library, tracking)
    window.resize(1100, 680)
    tracking.game_started.emit(GameStarted(games[0].id, now - 47 * 60 - 12, None))
    window.show_game(games[0].id)
    capture(window, "fiche-banniere-par-defaut.png")
    window.show_game(games[1].id)
    capture(window, "fiche-banniere-personnalisee.png")

    tray = TrayIcon(
        lambda: [
            RecentGame(g.id, g.display_name, library.icon(g.id) or generic_game_icon(), running)
            for g, running in library.recent_games()
        ]
    )
    tray.rebuild_menu()
    tray.menu.adjustSize()
    capture(tray.menu, "menu-systray.png")
    conn.close()


if __name__ == "__main__":
    main()
