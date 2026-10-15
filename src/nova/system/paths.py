"""Emplacement des données de Nova : ``%APPDATA%\\Nova``.

Rien de personnel n'est stocké dans le dossier du projet. La variable
d'environnement ``NOVA_DATA_DIR`` permet d'utiliser un autre dossier
(tests, essais en développement).
"""

import os
from pathlib import Path

APP_NAME = "Nova"


def data_dir() -> Path:
    """Dossier des données de Nova, créé s'il n'existe pas encore."""
    override = os.environ.get("NOVA_DATA_DIR")
    if override:
        path = Path(override)
    else:
        appdata = os.environ.get("APPDATA")
        base = Path(appdata) if appdata else Path.home() / "AppData" / "Roaming"
        path = base / APP_NAME
    path.mkdir(parents=True, exist_ok=True)
    return path


def database_path() -> Path:
    return data_dir() / "nova.db"


def logs_dir() -> Path:
    path = data_dir() / "logs"
    path.mkdir(exist_ok=True)
    return path
