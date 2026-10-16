"""Connexion à la base SQLite et migrations du schéma.

Chaque thread ouvre sa propre connexion : une pour l'interface, une pour le thread
de suivi. Le mode WAL permet à l'interface de lire pendant que le suivi écrit.
"""

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

# Chaque migration fait passer le schéma à la version suivante. On ne modifie
# jamais une migration déjà utilisée : on en ajoute une nouvelle à la fin.
MIGRATIONS: list[tuple[str, ...]] = [
    # Version 1 : jeux et sessions.
    (
        """
        CREATE TABLE games (
            id INTEGER PRIMARY KEY,
            process_name TEXT NOT NULL UNIQUE,  -- toujours en minuscules
            display_name TEXT NOT NULL,
            exe_path TEXT,                      -- NULL : chemin inconnu ou illisible
            added_at INTEGER NOT NULL           -- secondes UTC
        )
        """,
        """
        CREATE TABLE sessions (
            id INTEGER PRIMARY KEY,
            game_id INTEGER NOT NULL REFERENCES games (id) ON DELETE CASCADE,
            started_at INTEGER NOT NULL,        -- secondes UTC
            last_saved_at INTEGER NOT NULL,     -- dernier instant où le jeu tournait à coup sûr
            ended_at INTEGER                    -- NULL : en cours, ou interrompue par un crash
        )
        """,
        "CREATE INDEX sessions_game_id ON sessions (game_id)",
    ),
    # Version 2 : bannière personnalisée et jeux impossibles à lancer directement.
    (
        "ALTER TABLE games ADD COLUMN banner_file TEXT",  # NULL : bannière par défaut
        # NULL : lançable (à notre connaissance) ; sinon code de raison (« access_denied »…).
        "ALTER TABLE games ADD COLUMN launch_error TEXT",
    ),
]


class UnsupportedDatabaseVersion(Exception):
    """La base a été créée par une version plus récente de Nova."""


def connect(path: str | Path) -> sqlite3.Connection:
    """Ouvre la base (en la créant si besoin) et met son schéma à jour."""
    conn = sqlite3.connect(path, autocommit=True)
    try:
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")  # active la suppression en cascade
        conn.execute("PRAGMA busy_timeout = 5000")  # attend jusqu'à 5 s si l'autre écrit
        conn.execute("PRAGMA journal_mode = WAL")
        # FULL : chaque validation est écrite physiquement sur le disque. En mode WAL,
        # NORMAL ne garantit pas qu'une sauvegarde survive à une coupure de courant,
        # et FULL ne coûte qu'une écriture disque par minute de jeu.
        conn.execute("PRAGMA synchronous = FULL")
        migrate(conn)
    except BaseException:
        # Base inutilisable : on referme tout de suite, sinon Windows garde le fichier
        # verrouillé et il devient impossible de le mettre de côté.
        conn.close()
        raise
    return conn


def migrate(conn: sqlite3.Connection) -> None:
    """Applique les migrations manquantes. La version du schéma est stockée dans la base."""
    version = conn.execute("PRAGMA user_version").fetchone()[0]
    if version > len(MIGRATIONS):
        raise UnsupportedDatabaseVersion(
            f"schéma en version {version}, cette version de Nova connaît jusqu'à {len(MIGRATIONS)}"
        )
    for number in range(version + 1, len(MIGRATIONS) + 1):
        with transaction(conn):
            for statement in MIGRATIONS[number - 1]:
                conn.execute(statement)
            conn.execute(f"PRAGMA user_version = {number}")


@contextmanager
def transaction(conn: sqlite3.Connection) -> Iterator[None]:
    """Regroupe plusieurs écritures : soit elles réussissent toutes, soit aucune.

    Hors de ce bloc, chaque requête est validée immédiatement (mode autocommit).
    """
    conn.execute("BEGIN IMMEDIATE")
    try:
        yield
    except BaseException:
        conn.execute("ROLLBACK")
        raise
    conn.execute("COMMIT")
