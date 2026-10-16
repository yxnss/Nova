"""Bannières personnalisées des jeux.

L'image choisie est **copiée** dans ``%APPDATA%\\Nova\\banners`` (jamais référencée
à son emplacement d'origine, qui peut disparaître), puis réduite si elle est trop
grande. Chaque fichier porte l'id du jeu en préfixe : ``12-3fa9c1d0.jpg``.
"""

from pathlib import Path
from uuid import uuid4

from PySide6.QtCore import Qt
from PySide6.QtGui import QImage

MAX_WIDTH, MAX_HEIGHT = 1920, 1080  # largement assez pour la zone de bannière
JPEG_QUALITY = 90
IMAGE_FILTER = "Images (*.png *.jpg *.jpeg *.webp *.bmp *.gif)"


class BannerError(Exception):
    """Erreur dont le message s'affiche tel quel à l'utilisateur."""


def has_transparency(image: QImage) -> bool:
    """Vrai si au moins un pixel est transparent.

    ``hasAlphaChannel()`` ne suffit pas : beaucoup de PNG ont un canal alpha alors
    que tous leurs pixels sont opaques. On vérifie donc les pixels eux-mêmes.
    """
    if not image.hasAlphaChannel():
        return False
    argb = image.convertToFormat(QImage.Format.Format_ARGB32)
    alpha = bytes(argb.constBits())[3::4]  # 4 octets par pixel : bleu, vert, rouge, alpha
    return alpha.count(255) != len(alpha)


class BannerStore:
    def __init__(self, folder: Path) -> None:
        self._folder = folder
        self._folder.mkdir(parents=True, exist_ok=True)

    def path(self, file_name: str) -> Path:
        return self._folder / file_name

    def import_image(self, game_id: int, source: str | Path) -> str:
        """Copie et réduit l'image ; renvoie le nom du fichier créé."""
        image = QImage(str(source))
        if image.isNull():
            raise BannerError(
                "Cette image n'a pas pu être lue. Choisissez un fichier PNG, JPG ou WebP."
            )
        if image.width() > MAX_WIDTH or image.height() > MAX_HEIGHT:
            image = image.scaled(
                MAX_WIDTH,
                MAX_HEIGHT,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
        # JPG, plus léger, sauf si l'image a de la transparence (que le JPG ne garde pas).
        keep_alpha = has_transparency(image)
        name = f"{game_id}-{uuid4().hex[:8]}.{'png' if keep_alpha else 'jpg'}"
        saved = image.save(
            str(self.path(name)), "PNG" if keep_alpha else "JPG", -1 if keep_alpha else JPEG_QUALITY
        )
        if not saved:
            raise BannerError("La bannière n'a pas pu être enregistrée.")
        return name

    def remove(self, file_name: str | None) -> None:
        if file_name:
            self.path(file_name).unlink(missing_ok=True)

    def remove_all_for(self, game_id: int) -> None:
        """Supprime toutes les bannières d'un jeu (retrait de la bibliothèque)."""
        for path in self._folder.glob(f"{game_id}-*"):
            path.unlink(missing_ok=True)
