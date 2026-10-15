"""Horloges utilisées par le moteur de suivi.

Le moteur lit le temps à travers l'interface ``Clock`` plutôt qu'en appelant
directement le module ``time`` : les tests peuvent ainsi simuler des minutes,
une veille ou un changement d'heure sans attendre.
"""

import time
from typing import Protocol


class Clock(Protocol):
    def now(self) -> float:
        """Heure murale en secondes UTC depuis 1970 : c'est elle qu'on enregistre."""
        ...

    def monotonic(self) -> float:
        """Horloge qui ne recule jamais, insensible aux changements d'heure."""
        ...


class SystemClock:
    """Horloge réelle du système."""

    def now(self) -> float:
        return time.time()

    def monotonic(self) -> float:
        return time.monotonic()
