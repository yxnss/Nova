"""Accès à la table des jeux."""

import sqlite3

from nova.core.models import Game, TrackedGame


class DuplicateGameError(Exception):
    """Un jeu avec ce nom de processus est déjà dans la bibliothèque."""


def normalize_process_name(name: str) -> str:
    """Forme enregistrée d'un nom de processus : sans espaces autour, en minuscules."""
    return name.strip().lower()


class GameRepository:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def add(
        self,
        process_name: str,
        display_name: str,
        exe_path: str | None = None,
        *,
        added_at: float,
    ) -> Game:
        name = normalize_process_name(process_name)
        try:
            cursor = self._conn.execute(
                "INSERT INTO games (process_name, display_name, exe_path, added_at)"
                " VALUES (?, ?, ?, ?)",
                (name, display_name, exe_path, round(added_at)),
            )
        except sqlite3.IntegrityError as error:
            if error.sqlite_errorname == "SQLITE_CONSTRAINT_UNIQUE":
                raise DuplicateGameError(name) from error
            raise
        return Game(cursor.lastrowid, name, display_name, exe_path, round(added_at))

    def get(self, game_id: int) -> Game | None:
        row = self._conn.execute("SELECT * FROM games WHERE id = ?", (game_id,)).fetchone()
        return _to_game(row) if row else None

    def list_all(self) -> list[Game]:
        return [_to_game(row) for row in self._conn.execute("SELECT * FROM games ORDER BY id")]

    def list_tracked(self) -> list[TrackedGame]:
        """Ce dont le moteur de suivi a besoin : l'id et le nom de processus de chaque jeu."""
        rows = self._conn.execute("SELECT id, process_name FROM games ORDER BY id")
        return [TrackedGame(row["id"], row["process_name"]) for row in rows]

    def update_exe_path(self, game_id: int, exe_path: str) -> None:
        # Nouveau chemin (jeu déplacé, mis à jour…) : un ancien échec de lancement ne
        # vaut plus, le bouton « Lancer » redevient disponible.
        self._conn.execute(
            "UPDATE games SET exe_path = ?, launch_error = NULL WHERE id = ?", (exe_path, game_id)
        )

    def set_banner(self, game_id: int, banner_file: str | None) -> None:
        self._conn.execute("UPDATE games SET banner_file = ? WHERE id = ?", (banner_file, game_id))

    def set_launch_error(self, game_id: int, reason: str | None) -> None:
        """Enregistre le code de raison d'un échec de lancement (None : lançable)."""
        self._conn.execute("UPDATE games SET launch_error = ? WHERE id = ?", (reason, game_id))

    def delete(self, game_id: int) -> None:
        """Supprime le jeu ; ses sessions sont supprimées en cascade par SQLite."""
        self._conn.execute("DELETE FROM games WHERE id = ?", (game_id,))


def _to_game(row: sqlite3.Row) -> Game:
    return Game(
        id=row["id"],
        process_name=row["process_name"],
        display_name=row["display_name"],
        exe_path=row["exe_path"],
        added_at=row["added_at"],
        banner_file=row["banner_file"],
        launch_error=row["launch_error"],
    )
