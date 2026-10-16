"""Démarrage automatique avec Windows, via la clé « Run » de l'utilisateur.

``HKEY_CURRENT_USER\\Software\\Microsoft\\Windows\\CurrentVersion\\Run`` : Windows
lance chaque programme listé à l'ouverture de session. Cette clé appartient à
l'utilisateur, donc aucun droit administrateur n'est nécessaire.
"""

import logging
import sys
import winreg
from pathlib import Path

log = logging.getLogger(__name__)

RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
VALUE_NAME = "Nova"


def launch_command() -> str:
    """Commande enregistrée : Nova démarre directement réduite dans le systray.

    Une fois empaquetée (étape 7), c'est ``Nova.exe`` lui-même. En développement, c'est
    ``pythonw.exe`` du ``.venv`` (la version sans console de Python) avec ``-m nova``.
    """
    if getattr(sys, "frozen", False):
        return f'"{sys.executable}" --minimized'
    pythonw = Path(sys.executable).with_name("pythonw.exe")
    return f'"{pythonw}" -m nova --minimized'


class AutoStart:
    def __init__(
        self,
        key_path: str = RUN_KEY,
        value_name: str = VALUE_NAME,
        command: str | None = None,
    ) -> None:
        self._key_path = key_path
        self._value_name = value_name
        self._command = command or launch_command()

    def registered_command(self) -> str | None:
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, self._key_path) as key:
                value, _ = winreg.QueryValueEx(key, self._value_name)
                return value
        except FileNotFoundError:
            return None

    def is_enabled(self) -> bool:
        return self.registered_command() is not None

    def enable(self) -> None:
        with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, self._key_path) as key:
            winreg.SetValueEx(key, self._value_name, 0, winreg.REG_SZ, self._command)
        log.info("Démarrage automatique activé : %s", self._command)

    def disable(self) -> None:
        try:
            with winreg.OpenKey(
                winreg.HKEY_CURRENT_USER, self._key_path, 0, winreg.KEY_SET_VALUE
            ) as key:
                winreg.DeleteValue(key, self._value_name)
        except FileNotFoundError:
            return  # déjà désactivé
        log.info("Démarrage automatique désactivé")

    def repair(self) -> None:
        """Si Nova a été déplacée, met à jour la commande enregistrée (au démarrage)."""
        registered = self.registered_command()
        if registered is not None and registered != self._command:
            log.info("Démarrage automatique : chemin mis à jour (ancien : %s)", registered)
            self.enable()
