"""Événements produits par le moteur de suivi.

Le moteur ne connaît pas l'interface : il renvoie ces événements, et la couche
``services`` les transmet à l'interface sous forme de signaux Qt.
"""

from dataclasses import dataclass
from enum import StrEnum


class StopReason(StrEnum):
    """Pourquoi une session s'est arrêtée."""

    CLOSED = "closed"  # le jeu s'est fermé
    GAP = "gap"  # écart anormal entre deux scans : veille, gel ou changement d'heure
    PAUSED = "paused"  # l'utilisateur a mis le suivi en pause
    UNTRACKED = "untracked"  # le jeu a été retiré de la bibliothèque
    SHUTDOWN = "shutdown"  # Nova s'arrête


@dataclass(frozen=True)
class GameStarted:
    game_id: int
    started_at: float
    # Chemin de l'exécutable, ou None s'il est illisible (processus protégé).
    exe_path: str | None


@dataclass(frozen=True)
class GameStopped:
    game_id: int
    started_at: float
    ended_at: float
    reason: StopReason
    # False si la session a été ignorée car trop courte.
    counted: bool


type TrackerEvent = GameStarted | GameStopped
