"""Objets métier partagés par les couches de Nova."""

from dataclasses import dataclass


@dataclass(frozen=True)
class TrackedGame:
    """Un jeu surveillé, identifié par son nom de processus (ex. ``eldenring.exe``)."""

    id: int
    process_name: str
