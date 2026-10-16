"""Sauvegarde de la base et récupération si elle est abîmée.

- Une copie par jour dans ``%APPDATA%\\Nova\\backups`` (``nova-2026-10-17.db``),
  les 7 dernières sont gardées.
- Au démarrage, si la base est illisible ou abîmée, elle est mise de côté (jamais
  supprimée) et remplacée par la sauvegarde la plus récente.
"""

import logging
import shutil
import sqlite3
from datetime import date, datetime
from pathlib import Path

from nova.data.database import UnsupportedDatabaseVersion, connect

log = logging.getLogger(__name__)

KEEP_BACKUPS = 7


def backup_if_needed(
    conn: sqlite3.Connection, folder: Path, today: date | None = None, keep: int = KEEP_BACKUPS
) -> Path | None:
    """Fait la sauvegarde du jour si elle n'existe pas encore ; renvoie son chemin."""
    folder.mkdir(parents=True, exist_ok=True)
    target = folder / f"nova-{(today or date.today()).isoformat()}.db"
    if target.exists():
        return None
    # Copie dans un fichier temporaire puis renommage : jamais de sauvegarde à moitié écrite.
    temporary = target.with_suffix(".tmp")
    copy = sqlite3.connect(temporary)
    conn.backup(copy)  # copie cohérente, même pendant que le suivi écrit
    copy.close()
    temporary.replace(target)
    for old in sorted(folder.glob("nova-*.db"))[:-keep]:
        old.unlink()
    log.info("Sauvegarde du jour : %s", target.name)
    return target


def latest_backup(folder: Path) -> Path | None:
    backups = sorted(folder.glob("nova-*.db"))
    return backups[-1] if backups else None


def open_or_recover(path: Path, backups: Path) -> tuple[sqlite3.Connection, str | None]:
    """Ouvre la base ; si elle est abîmée, la remplace par la dernière sauvegarde.

    Renvoie la connexion et, en cas de récupération, un message pour l'utilisateur.
    Une base créée par une version plus récente de Nova n'est jamais touchée.
    """
    try:
        conn = connect(path)
        if conn.execute("PRAGMA quick_check").fetchone()[0] == "ok":
            return conn, None
        conn.close()
    except UnsupportedDatabaseVersion:
        raise
    except sqlite3.DatabaseError:
        log.exception("Base illisible")

    # Mise de côté (jamais supprimée) : on pourra peut-être en récupérer quelque chose.
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    for suffix in ("", "-wal", "-shm"):
        damaged = Path(f"{path}{suffix}")
        if damaged.exists():
            damaged.rename(f"{path}.abimee-{stamp}{suffix}")

    backup = latest_backup(backups)
    if backup is not None:
        shutil.copy2(backup, path)
        day = backup.stem.removeprefix("nova-")
        message = (
            "La bibliothèque de Nova était abîmée. Elle a été restaurée à partir de la "
            f"sauvegarde du {day} : le temps de jeu depuis cette date peut manquer."
        )
    else:
        message = (
            "La bibliothèque de Nova était abîmée et aucune sauvegarde n'existait encore : "
            "une nouvelle bibliothèque vide a été créée."
        )
    log.warning("%s (base abîmée gardée sous %s.abimee-%s)", message, path.name, stamp)
    return connect(path), message
