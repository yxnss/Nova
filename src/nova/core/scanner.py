"""Détection des processus en cours d'exécution.

Le moteur de suivi passe par l'interface ``ProcessScanner`` ; ``PsutilScanner`` en
est l'implémentation réelle, et les tests utilisent une version simulée.
"""

from collections.abc import Collection, Iterable
from typing import Protocol

import psutil


class ProcessScanner(Protocol):
    def find(self, names: Collection[str]) -> dict[str, set[int]]:
        """Scan complet : renvoie les PID de chaque nom cherché qui tourne.

        Les noms sont comparés sans tenir compte de la casse et les clés du
        résultat sont en minuscules. Un nom absent du résultat ne tourne pas.
        """
        ...

    def still_running(self, pids: Iterable[int]) -> set[int]:
        """Vérification légère : renvoie ceux des PID donnés qui existent encore."""
        ...

    def exe_path(self, pid: int) -> str | None:
        """Chemin de l'exécutable, ou None s'il est illisible ou si le processus a disparu."""
        ...


class PsutilScanner:
    """Implémentation réelle, basée sur psutil."""

    def __init__(self) -> None:
        # Processus trouvés au dernier scan complet, gardés pour les vérifications
        # légères : psutil y mémorise l'heure de création, ce qui permet de
        # repérer un PID réutilisé par un autre programme.
        self._known: dict[int, psutil.Process] = {}

    def find(self, names: Collection[str]) -> dict[str, set[int]]:
        wanted = {name.lower() for name in names}
        if not wanted:
            return {}
        # Sous Windows, psutil garde le nom de chaque processus en cache. Si un PID
        # est réutilisé entre deux scans, le cache donnerait le nom de l'ancien
        # processus : on le vide pour toujours lire des noms à jour.
        psutil.process_iter.cache_clear()
        found: dict[str, set[int]] = {}
        known: dict[int, psutil.Process] = {}
        for process in psutil.process_iter(["name"]):
            name = (process.info["name"] or "").lower()
            if name in wanted:
                found.setdefault(name, set()).add(process.pid)
                known[process.pid] = process
        self._known = known
        return found

    def still_running(self, pids: Iterable[int]) -> set[int]:
        alive = set()
        for pid in pids:
            process = self._known.get(pid)
            # is_running() vérifie aussi l'heure de création : un PID réutilisé
            # par un autre programme est considéré comme terminé.
            if process is not None and process.is_running():
                alive.add(pid)
        return alive

    def exe_path(self, pid: int) -> str | None:
        try:
            process = self._known.get(pid) or psutil.Process(pid)
            return process.exe() or None
        except psutil.Error:  # accès refusé (processus protégé) ou processus disparu
            return None
