"""Doublures de test du moteur de suivi : horloge, scanner et stockage simulés."""

from collections.abc import Collection, Iterable
from dataclasses import dataclass

from nova.core.events import GameStarted, GameStopped, TrackerEvent
from nova.core.models import TrackedGame
from nova.core.tracker import SessionStore, Tracker, TrackerSettings


class FakeClock:
    """Horloge simulée : le temps n'avance que lorsque le test le décide."""

    def __init__(self) -> None:
        self.wall = 0.0
        self.mono = 0.0

    def now(self) -> float:
        return self.wall

    def monotonic(self) -> float:
        return self.mono

    def advance(self, seconds: float) -> None:
        self.wall += seconds
        self.mono += seconds

    def suspend(self, seconds: float, monotonic_counts: bool) -> None:
        """Simule une veille du PC.

        L'heure murale avance toujours. Selon le matériel, l'horloge monotone de
        Windows peut avancer ou non pendant la veille : les tests couvrent les deux.
        """
        self.wall += seconds
        if monotonic_counts:
            self.mono += seconds

    def change_time(self, seconds: float) -> None:
        """Simule un changement manuel de l'heure du PC : seule l'heure murale bouge."""
        self.wall += seconds


class FakeScanner:
    """Liste de processus simulée, que le test remplit et vide à volonté."""

    def __init__(self) -> None:
        self.processes: dict[int, str] = {}  # PID -> nom de processus
        self.paths: dict[int, str | None] = {}
        self.full_scans = 0
        self.pid_checks = 0

    def launch(self, pid: int, name: str, path: str | None = "C:/Jeux/game.exe") -> None:
        self.processes[pid] = name
        self.paths[pid] = path

    def kill(self, pid: int) -> None:
        del self.processes[pid]

    def find(self, names: Collection[str]) -> dict[str, set[int]]:
        self.full_scans += 1
        wanted = {name.lower() for name in names}
        found: dict[str, set[int]] = {}
        # Copie de la liste : le test peut la modifier depuis un autre thread.
        for pid, name in list(self.processes.items()):
            if name.lower() in wanted:
                found.setdefault(name.lower(), set()).add(pid)
        return found

    def still_running(self, pids: Iterable[int]) -> set[int]:
        self.pid_checks += 1
        return {pid for pid in pids if pid in self.processes}

    def exe_path(self, pid: int) -> str | None:
        return self.paths.get(pid) if pid in self.processes else None


@dataclass
class StoredSession:
    game_id: int
    started_at: float
    saved_at: float
    ended_at: float | None = None


class FakeStore:
    """Stockage en mémoire qui garde aussi le journal de toutes les écritures."""

    def __init__(self) -> None:
        self.sessions: dict[int, StoredSession] = {}
        self.writes: list[tuple[str, float]] = []  # (action, instant)

    def open_session(self, game_id: int, started_at: float, saved_at: float) -> int:
        session_id = len(self.sessions) + 1
        self.sessions[session_id] = StoredSession(game_id, started_at, saved_at)
        self.writes.append(("open", saved_at))
        return session_id

    def save_session(self, session_id: int, saved_at: float) -> None:
        self.sessions[session_id].saved_at = saved_at
        self.writes.append(("save", saved_at))

    def close_session(self, session_id: int, ended_at: float) -> None:
        self.sessions[session_id].ended_at = ended_at
        self.writes.append(("close", ended_at))

    def periods(self) -> list[tuple[int, float, float | None]]:
        """Sessions enregistrées, sous la forme (id du jeu, début, fin)."""
        return [(s.game_id, s.started_at, s.ended_at) for s in self.sessions.values()]


class TrackerHarness:
    """Assemble le moteur et ses doublures, et le fait tourner comme le ferait Nova."""

    def __init__(
        self,
        *games: TrackedGame,
        settings: TrackerSettings | None = None,
        store: SessionStore | None = None,
    ) -> None:
        self.clock = FakeClock()
        self.scanner = FakeScanner()
        # Stockage simulé par défaut ; un test peut fournir la vraie base SQLite.
        self.store = store if store is not None else FakeStore()
        self.tracker = Tracker(self.scanner, self.store, self.clock, settings)
        self.step = (settings or TrackerSettings()).scan_interval
        self.events: list[TrackerEvent] = list(self.tracker.set_games(games))

    def tick(self) -> None:
        self.events += self.tracker.tick()

    def run(self, seconds: float) -> None:
        """Fait avancer le temps de ``seconds`` secondes, avec un tick à chaque intervalle."""
        for _ in range(round(seconds / self.step)):
            self.clock.advance(self.step)
            self.tick()

    def started(self) -> list[GameStarted]:
        return [e for e in self.events if isinstance(e, GameStarted)]

    def stopped(self) -> list[GameStopped]:
        return [e for e in self.events if isinstance(e, GameStopped)]
