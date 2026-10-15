"""Accès à la table des sessions.

``SessionRepository`` implémente l'interface ``SessionStore`` du moteur de suivi.
Les instants sont arrondis à la seconde avant d'être enregistrés.
"""

import sqlite3
from dataclasses import dataclass

from nova.data.database import transaction


@dataclass(frozen=True)
class RepairReport:
    closed: int  # sessions clôturées à leur dernière sauvegarde
    deleted: int  # sessions supprimées car trop courtes


class SessionRepository:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def open_session(self, game_id: int, started_at: float, saved_at: float) -> int:
        cursor = self._conn.execute(
            "INSERT INTO sessions (game_id, started_at, last_saved_at) VALUES (?, ?, ?)",
            (game_id, round(started_at), round(saved_at)),
        )
        return cursor.lastrowid

    def save_session(self, session_id: int, saved_at: float) -> None:
        self._conn.execute(
            "UPDATE sessions SET last_saved_at = ? WHERE id = ?",
            (round(saved_at), session_id),
        )

    def close_session(self, session_id: int, ended_at: float) -> None:
        self._conn.execute(
            "UPDATE sessions SET last_saved_at = ?, ended_at = ? WHERE id = ?",
            (round(ended_at), round(ended_at), session_id),
        )

    def repair_open_sessions(self, min_session: float) -> RepairReport:
        """Répare les sessions restées ouvertes, à appeler au démarrage avant le suivi.

        Une session encore ouverte à ce moment-là a été interrompue (crash, coupure
        de courant, arrêt brutal). Elle est clôturée à sa dernière sauvegarde, ou
        supprimée si elle n'atteint pas la durée minimale.
        """
        with transaction(self._conn):
            deleted = self._conn.execute(
                "DELETE FROM sessions WHERE ended_at IS NULL AND last_saved_at - started_at < ?",
                (min_session,),
            ).rowcount
            closed = self._conn.execute(
                "UPDATE sessions SET ended_at = last_saved_at WHERE ended_at IS NULL"
            ).rowcount
        return RepairReport(closed=closed, deleted=deleted)
