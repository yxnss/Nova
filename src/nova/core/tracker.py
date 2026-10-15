"""Moteur de suivi : transforme des observations de processus en sessions de jeu.

Le thread de suivi appelle ``Tracker.tick()`` toutes les ``scan_interval`` secondes.
À chaque tick, le moteur :

1. détecte un écart anormal depuis le tick précédent (veille, gel, changement
   d'heure) et clôture alors les sessions au dernier instant fiable ;
2. observe les processus, par un scan complet ou une simple vérification des PID ;
3. ouvre, prolonge, sauvegarde ou clôture la session de chaque jeu.

Une session reste provisoire en mémoire jusqu'à atteindre ``min_session`` : un
lancement raté ne provoque donc aucune écriture. Ensuite, elle est sauvegardée
toutes les ``checkpoint_interval`` secondes pour limiter la perte en cas de crash.
"""

from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Protocol

from nova.core.clock import Clock
from nova.core.events import GameStarted, GameStopped, StopReason, TrackerEvent
from nova.core.models import TrackedGame
from nova.core.scanner import ProcessScanner


class SessionStore(Protocol):
    """Enregistrement des sessions (implémenté par la couche ``data``)."""

    def open_session(self, game_id: int, started_at: float, saved_at: float) -> int:
        """Crée la session en base et renvoie son identifiant."""
        ...

    def save_session(self, session_id: int, saved_at: float) -> None:
        """Note que la session était encore en cours à ``saved_at``."""
        ...

    def close_session(self, session_id: int, ended_at: float) -> None:
        """Clôture la session."""
        ...


@dataclass(frozen=True)
class TrackerSettings:
    """Réglages du moteur, en secondes."""

    scan_interval: float = 5.0  # cadence des ticks
    checkpoint_interval: float = 60.0  # sauvegarde d'une session en cours
    min_session: float = 10.0  # en dessous, la session est ignorée
    gap_factor: float = 3.0  # un écart > gap_factor × scan_interval est anormal
    full_scan_interval: float = 30.0  # scan complet régulier pendant une partie

    @property
    def max_gap(self) -> float:
        return self.gap_factor * self.scan_interval


@dataclass
class _ActiveSession:
    """Session d'un jeu en cours d'exécution, telle que le moteur la suit en mémoire."""

    game_id: int
    started_at: float
    last_seen_at: float  # dernier tick où le jeu tournait : dernier instant fiable
    pids: set[int] = field(default_factory=set)
    session_id: int | None = None  # None tant que la session n'est pas en base
    last_saved_at: float | None = None


class Tracker:
    def __init__(
        self,
        scanner: ProcessScanner,
        store: SessionStore,
        clock: Clock,
        settings: TrackerSettings | None = None,
    ) -> None:
        self._scanner = scanner
        self._store = store
        self._clock = clock
        self._settings = settings or TrackerSettings()
        self._games: dict[str, int] = {}  # nom de processus (minuscules) -> id du jeu
        self._active: dict[int, _ActiveSession] = {}  # id du jeu -> session en cours
        self._last_tick: tuple[float, float] | None = None  # (heure murale, monotone)
        self._last_full_scan: float | None = None  # horloge monotone
        self._paused = False

    @property
    def paused(self) -> bool:
        return self._paused

    def running_games(self) -> dict[int, float]:
        """Jeux en cours : id du jeu -> début de la session."""
        return {game_id: s.started_at for game_id, s in self._active.items()}

    def set_games(self, games: Iterable[TrackedGame]) -> list[TrackerEvent]:
        """Remplace la liste des jeux suivis.

        Un jeu qui disparaît de la liste voit sa session en cours clôturée.
        """
        self._games = {game.process_name.lower(): game.id for game in games}
        kept = set(self._games.values())
        removed = [s for game_id, s in self._active.items() if game_id not in kept]
        # Le prochain tick fera un scan complet pour repérer les jeux ajoutés.
        self._last_full_scan = None
        return self._close_now(removed, StopReason.UNTRACKED)

    def tick(self) -> list[TrackerEvent]:
        if self._paused:
            return []
        now, mono = self._clock.now(), self._clock.monotonic()
        events: list[TrackerEvent] = []

        if self._is_gap(now, mono):
            # Le temps écoulé depuis le dernier tick n'est pas fiable (PC en veille,
            # par exemple) : chaque session s'arrête au dernier instant où on a vu
            # le jeu tourner. Si le jeu tourne encore, une nouvelle session
            # commencera juste après.
            for session in list(self._active.values()):
                events.append(self._close(session, session.last_seen_at, StopReason.GAP))

        running = self._observe(mono)
        for name, game_id in self._games.items():
            pids = running.get(name, set())
            session = self._active.get(game_id)
            if pids and session is None:
                events.append(self._start(game_id, pids, now))
            elif pids and session is not None:
                self._continue(session, pids, now)
            elif session is not None:
                events.append(self._close(session, now, StopReason.CLOSED))

        self._last_tick = (now, mono)
        return events

    def pause(self) -> list[TrackerEvent]:
        """Met le suivi en pause : les sessions en cours sont clôturées."""
        if self._paused:
            return []
        events = self._close_now(list(self._active.values()), StopReason.PAUSED)
        self._paused = True
        self._last_tick = None
        return events

    def resume(self) -> None:
        """Reprend le suivi : le prochain tick fera un scan complet."""
        self._paused = False
        self._last_full_scan = None

    def shutdown(self) -> list[TrackerEvent]:
        """Arrêt de Nova : les sessions en cours sont clôturées."""
        return self._close_now(list(self._active.values()), StopReason.SHUTDOWN)

    # --- Fonctionnement interne ---

    def _is_gap(self, now: float, mono: float) -> bool:
        """Vrai si le temps écoulé depuis le dernier tick est anormal.

        On surveille les deux horloges : l'horloge murale révèle toujours une veille
        (elle est resynchronisée au réveil) et un changement d'heure ; l'horloge
        monotone révèle un gel du programme même si l'heure a été corrigée entre-temps.
        """
        if self._last_tick is None:
            return False
        last_now, last_mono = self._last_tick
        max_gap = self._settings.max_gap
        wall_delta = now - last_now
        return wall_delta < 0 or wall_delta > max_gap or mono - last_mono > max_gap

    def _observe(self, mono: float) -> dict[str, set[int]]:
        """Renvoie les PID en cours de chaque jeu, par nom de processus."""
        if not self._games:
            return {}
        last = self._last_full_scan
        full_scan_due = last is None or mono - last >= self._settings.full_scan_interval
        if not self._active or full_scan_due:
            return self._full_scan(mono)

        # Partie en cours : on vérifie seulement les PID déjà connus, ce qui coûte
        # beaucoup moins cher qu'un scan complet.
        names = {game_id: name for name, game_id in self._games.items()}
        running: dict[str, set[int]] = {}
        for game_id, session in self._active.items():
            alive = self._scanner.still_running(session.pids)
            if not alive:
                # Tous les PID connus ont disparu, mais le jeu a peut-être relancé
                # son processus : on confirme par un scan complet avant de conclure.
                return self._full_scan(mono)
            running[names[game_id]] = alive
        return running

    def _full_scan(self, mono: float) -> dict[str, set[int]]:
        self._last_full_scan = mono
        return self._scanner.find(self._games.keys())

    def _start(self, game_id: int, pids: set[int], now: float) -> GameStarted:
        self._active[game_id] = _ActiveSession(game_id, now, now, set(pids))
        return GameStarted(game_id, now, self._scanner.exe_path(min(pids)))

    def _continue(self, session: _ActiveSession, pids: set[int], now: float) -> None:
        session.pids = set(pids)
        session.last_seen_at = now
        settings = self._settings
        if session.session_id is None:
            if now - session.started_at >= settings.min_session:
                session.session_id = self._store.open_session(
                    session.game_id, session.started_at, now
                )
                session.last_saved_at = now
        elif session.last_saved_at is not None:
            if now - session.last_saved_at >= settings.checkpoint_interval:
                self._store.save_session(session.session_id, now)
                session.last_saved_at = now

    def _close(self, session: _ActiveSession, ended_at: float, reason: StopReason) -> GameStopped:
        del self._active[session.game_id]
        counted = session.session_id is not None
        if session.session_id is not None:
            self._store.close_session(session.session_id, ended_at)
        elif ended_at - session.started_at >= self._settings.min_session:
            # Le jeu a atteint la durée minimale entre deux ticks : on enregistre
            # directement la session complète.
            session_id = self._store.open_session(session.game_id, session.started_at, ended_at)
            self._store.close_session(session_id, ended_at)
            counted = True
        return GameStopped(session.game_id, session.started_at, ended_at, reason, counted)

    def _close_now(self, sessions: list[_ActiveSession], reason: StopReason) -> list[TrackerEvent]:
        """Clôture des sessions en dehors d'un tick (pause, arrêt, retrait d'un jeu).

        Si un écart anormal s'est produit depuis le dernier tick (par exemple, une
        pause demandée juste après le réveil du PC), la session s'arrête au dernier
        instant fiable plutôt que maintenant.
        """
        now, mono = self._clock.now(), self._clock.monotonic()
        gap = self._is_gap(now, mono)
        return [self._close(s, s.last_seen_at if gap else now, reason) for s in sessions]
