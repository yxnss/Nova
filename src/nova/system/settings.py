"""Petits réglages de l'interface, gardés dans ``%APPDATA%\\Nova\\settings.ini``.

``QSettings`` (Qt) lit et écrit ce fichier texte. Les données de jeu, elles,
restent dans la base SQLite : ici, il n'y a que des préférences d'affichage.
"""

from pathlib import Path

from PySide6.QtCore import QSettings


class AppSettings:
    def __init__(self, path: Path) -> None:
        self._settings = QSettings(str(path), QSettings.Format.IniFormat)

    @property
    def close_notice_shown(self) -> bool:
        """Vrai si la notification « Nova continue en arrière-plan » a déjà été montrée."""
        return self._settings.value("close_notice_shown", False, type=bool)

    @close_notice_shown.setter
    def close_notice_shown(self, shown: bool) -> None:
        self._settings.setValue("close_notice_shown", shown)
        self._settings.sync()
