"""Statistiques de temps de jeu, toujours recalculées à partir des sessions.

La base ne contient que les sessions terminées sous leur forme définitive. La
session en cours, elle, est ajoutée par-dessus avec ``add_running_session`` :
elle n'est donc jamais comptée deux fois.
"""

import sqlite3
from dataclasses import replace

from nova.core.models import GameStats

LAST_7_DAYS = 7 * 24 * 3600  # fenêtre glissante, en secondes

# Pour les 7 derniers jours, chaque session est découpée à la fenêtre
# [since, now] : seule la partie qui chevauche la fenêtre est comptée.
# MIN et MAX à deux arguments sont des fonctions de SQLite qui renvoient
# le plus petit ou le plus grand des deux.
_STATS_QUERY = """
    SELECT
        g.id AS game_id,
        COALESCE(SUM(s.ended_at - s.started_at), 0) AS total,
        MAX(s.ended_at) AS last_played_at,
        COALESCE(SUM(MAX(0, MIN(s.ended_at, :now) - MAX(s.started_at, :since))), 0) AS last_7_days
    FROM games AS g
    LEFT JOIN sessions AS s ON s.game_id = g.id AND s.ended_at IS NOT NULL
    GROUP BY g.id
"""


def load_stats(conn: sqlite3.Connection, now: float) -> dict[int, GameStats]:
    """Statistiques de chaque jeu de la bibliothèque, calculées sur les sessions terminées."""
    now = round(now)
    rows = conn.execute(_STATS_QUERY, {"now": now, "since": now - LAST_7_DAYS})
    return {
        row["game_id"]: GameStats(
            game_id=row["game_id"],
            total_seconds=row["total"],
            last_played_at=row["last_played_at"],
            last_7_days_seconds=row["last_7_days"],
        )
        for row in rows
    }


def add_running_session(stats: GameStats, started_at: float, now: float) -> GameStats:
    """Ajoute aux statistiques la session d'un jeu en cours d'exécution."""
    since = now - LAST_7_DAYS
    return replace(
        stats,
        total_seconds=stats.total_seconds + int(max(0.0, now - started_at)),
        last_played_at=int(now),
        last_7_days_seconds=stats.last_7_days_seconds + int(max(0.0, now - max(started_at, since))),
    )
