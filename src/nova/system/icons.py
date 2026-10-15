"""Icônes des jeux : extraites une seule fois de l'exe, puis gardées sur le disque.

Chaque icône est enregistrée en PNG dans ``%APPDATA%\\Nova\\icons\\<id du jeu>.png``.
Elle n'est jamais recalculée à l'affichage. À utiliser depuis le thread principal :
l'extraction passe par ``QFileIconProvider``, un composant graphique de Qt.
"""

import logging
from pathlib import Path

from PySide6.QtCore import QFileInfo, QSize, Qt
from PySide6.QtGui import QIcon, QImage, QPainter, QPixmap
from PySide6.QtWidgets import QFileIconProvider

log = logging.getLogger(__name__)

ICON_SIZE = 256  # taille maximale extraite ; Windows fournit souvent 256 px pour les jeux


def icon_from_exe(exe_path: str) -> QIcon:
    """Icône Windows d'un exe, sans mise en cache (liste des programmes en cours)."""
    return QFileIconProvider().icon(QFileInfo(exe_path))


def trim_to_content(image: QImage) -> QImage:
    """Recadre une icône sur sa partie visible, dans un carré.

    Quand un exe n'a qu'une petite icône, Windows la renvoie parfois dans le coin
    supérieur gauche d'une grande image vide : sans recadrage, elle paraîtrait minuscule.
    """
    image = image.convertToFormat(QImage.Format.Format_ARGB32)
    width, height, stride = image.width(), image.height(), image.bytesPerLine()
    data = bytes(image.constBits())
    top = bottom = None
    left, right = width, -1
    for y in range(height):
        # En mémoire, chaque pixel fait 4 octets (bleu, vert, rouge, alpha) :
        # on ne garde que l'alpha, puis on retire les pixels transparents des deux côtés.
        alpha = data[y * stride : y * stride + width * 4][3::4]
        if not alpha.strip(b"\x00"):
            continue
        top = y if top is None else top
        bottom = y
        left = min(left, width - len(alpha.lstrip(b"\x00")))
        right = max(right, len(alpha.rstrip(b"\x00")) - 1)
    if top is None or bottom is None:
        return image  # icône entièrement transparente : rien à recadrer

    content = image.copy(left, top, right - left + 1, bottom - top + 1)
    side = max(content.width(), content.height())
    square = QImage(side, side, QImage.Format.Format_ARGB32)
    square.fill(Qt.GlobalColor.transparent)
    painter = QPainter(square)
    painter.drawImage((side - content.width()) // 2, (side - content.height()) // 2, content)
    painter.end()
    return square


class IconCache:
    def __init__(self, folder: Path) -> None:
        self._folder = folder
        self._folder.mkdir(parents=True, exist_ok=True)
        self._loaded: dict[int, QIcon] = {}

    def path_for(self, game_id: int) -> Path:
        return self._folder / f"{game_id}.png"

    def extract(self, game_id: int, exe_path: str) -> bool:
        """Extrait l'icône de l'exe et l'enregistre. Renvoie False si c'est impossible."""
        icon = icon_from_exe(exe_path)
        sizes = icon.availableSizes()
        size = max(sizes, key=lambda s: s.width()) if sizes else QSize(ICON_SIZE, ICON_SIZE)
        pixmap: QPixmap = icon.pixmap(size.boundedTo(QSize(ICON_SIZE, ICON_SIZE)))
        if pixmap.isNull():
            log.info("Icône introuvable pour %s", exe_path)
            return False
        image = trim_to_content(pixmap.toImage())
        if not image.save(str(self.path_for(game_id)), "PNG"):
            log.info("Icône introuvable pour %s", exe_path)
            return False
        self._loaded.pop(game_id, None)
        return True

    def icon(self, game_id: int) -> QIcon | None:
        """Icône du jeu, ou None s'il n'en a pas (l'interface affiche alors l'icône générique)."""
        if game_id not in self._loaded:
            path = self.path_for(game_id)
            if not path.exists():
                return None
            self._loaded[game_id] = QIcon(str(path))
        return self._loaded[game_id]

    def remove(self, game_id: int) -> None:
        self._loaded.pop(game_id, None)
        self.path_for(game_id).unlink(missing_ok=True)
