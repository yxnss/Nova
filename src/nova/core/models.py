"""Objets métier partagés par les couches de Nova."""

from dataclasses import dataclass


@dataclass(frozen=True)
class TrackedGame:
    """Un jeu surveillé, identifié par son nom de processus (ex. ``eldenring.exe``)."""

    id: int
    process_name: str


@dataclass(frozen=True)
class Game:
    """Un jeu de la bibliothèque, tel qu'enregistré en base."""

    id: int
    process_name: str  # toujours en minuscules
    display_name: str
    exe_path: str | None  # None : chemin inconnu (ajout par nom) ou illisible
    added_at: int  # secondes UTC


@dataclass(frozen=True)
class GameStats:
    """Statistiques d'un jeu, en secondes. Elles sont recalculées, jamais stockées."""

    game_id: int
    total_seconds: int
    last_played_at: int | None  # fin de la session la plus récente, None si jamais joué
    last_7_days_seconds: int
