"""Thread de suivi : fait tourner le moteur en arrière-plan et prévient l'interface.

``TrackingService`` vit dans le thread principal et sert d'interface au reste de
l'application. Il pilote un ``_TrackingWorker`` qui vit dans un thread dédié : le
scan, les calculs et les écritures en base ne figent donc jamais la fenêtre.

Les deux objets ne communiquent que par signaux Qt. Quand un signal traverse les
threads, Qt le met en file d'attente et l'exécute dans le thread du destinataire.
"""

import logging
from pathlib import Path

from PySide6.QtCore import QObject, Qt, QThread, QTimer, Signal, Slot

from nova.core.clock import Clock, SystemClock
from nova.core.events import GameStarted, GameStopped, TrackerEvent
from nova.core.scanner import ProcessScanner, PsutilScanner
from nova.core.tracker import Tracker, TrackerSettings
from nova.data.database import connect
from nova.data.games_repo import GameRepository
from nova.data.sessions_repo import SessionRepository

log = logging.getLogger(__name__)


class TrackingService(QObject):
    """Point d'entrée du suivi pour le reste de l'application (thread principal)."""

    ready = Signal(object)  # RepairReport : suivi démarré, sessions interrompues réparées
    game_started = Signal(object)  # GameStarted
    game_stopped = Signal(object)  # GameStopped
    game_path_found = Signal(int, str)  # id du jeu, chemin de l'exe nouvellement connu
    game_removed = Signal(int)  # id du jeu supprimé avec ses sessions
    paused_changed = Signal(bool)

    # Demandes transmises au thread de suivi.
    _reload_requested = Signal()
    _remove_requested = Signal(int)
    _pause_requested = Signal(bool)
    _stop_requested = Signal()

    def __init__(
        self,
        db_path: str | Path,
        settings: TrackerSettings | None = None,
        scanner: ProcessScanner | None = None,
        clock: Clock | None = None,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._thread = QThread()
        self._thread.setObjectName("suivi")
        self._worker = _TrackingWorker(
            db_path,
            settings or TrackerSettings(),
            scanner or PsutilScanner(),
            clock or SystemClock(),
        )
        self._worker.moveToThread(self._thread)
        self._thread.started.connect(self._worker.start)
        self._thread.finished.connect(self._worker.deleteLater)

        # Les signaux du worker sont relayés tels quels.
        self._worker.ready.connect(self.ready)
        self._worker.game_started.connect(self.game_started)
        self._worker.game_stopped.connect(self.game_stopped)
        self._worker.game_path_found.connect(self.game_path_found)
        self._worker.game_removed.connect(self.game_removed)
        self._worker.paused_changed.connect(self.paused_changed)

        self._reload_requested.connect(self._worker.reload_games)
        self._remove_requested.connect(self._worker.remove_game)
        self._pause_requested.connect(self._worker.set_paused)
        # Bloquant : stop() attend que le worker ait clôturé les sessions en cours.
        self._stop_requested.connect(self._worker.stop, Qt.ConnectionType.BlockingQueuedConnection)

    def start(self) -> None:
        self._thread.start()

    def reload_games(self) -> None:
        """À appeler après l'ajout d'un jeu : le moteur relit la liste des jeux."""
        self._reload_requested.emit()

    def remove_game(self, game_id: int) -> None:
        """Arrête le suivi du jeu puis le supprime avec tout son historique."""
        self._remove_requested.emit(game_id)

    def set_paused(self, paused: bool) -> None:
        self._pause_requested.emit(paused)

    def stop(self) -> None:
        """Arrêt propre : clôture les sessions en cours puis termine le thread."""
        if self._thread.isRunning():
            self._stop_requested.emit()
            self._thread.quit()
            self._thread.wait()


class _TrackingWorker(QObject):
    """Fait tourner le moteur dans le thread de suivi. Utilisé seulement par TrackingService."""

    ready = Signal(object)
    game_started = Signal(object)
    game_stopped = Signal(object)
    game_path_found = Signal(int, str)
    game_removed = Signal(int)
    paused_changed = Signal(bool)

    def __init__(
        self,
        db_path: str | Path,
        settings: TrackerSettings,
        scanner: ProcessScanner,
        clock: Clock,
    ) -> None:
        super().__init__()
        self._db_path = db_path
        self._settings = settings
        self._scanner = scanner
        self._clock = clock
        # Créés dans start(), donc dans le thread de suivi : une connexion SQLite et
        # un minuteur Qt doivent être utilisés par le thread qui les a créés.
        self._conn = None
        self._games: GameRepository | None = None
        self._tracker: Tracker | None = None
        self._timer: QTimer | None = None

    @Slot()
    def start(self) -> None:
        self._conn = connect(self._db_path)
        sessions = SessionRepository(self._conn)
        report = sessions.repair_open_sessions(self._settings.min_session)
        if report.closed or report.deleted:
            log.warning(
                "Sessions interrompues réparées : %d clôturées, %d supprimées (trop courtes)",
                report.closed,
                report.deleted,
            )
        self._games = GameRepository(self._conn)
        self._tracker = Tracker(self._scanner, sessions, self._clock, self._settings)
        games = self._games.list_tracked()
        self._tracker.set_games(games)

        self._timer = QTimer(self)
        self._timer.setInterval(round(self._settings.scan_interval * 1000))
        self._timer.timeout.connect(self._tick)
        self._timer.start()
        log.info("Suivi démarré : %d jeu(x) surveillé(s)", len(games))
        self.ready.emit(report)
        self._tick()

    @Slot()
    def reload_games(self) -> None:
        self._dispatch(self._tracker.set_games(self._games.list_tracked()))

    @Slot(int)
    def remove_game(self, game_id: int) -> None:
        remaining = [game for game in self._games.list_tracked() if game.id != game_id]
        self._dispatch(self._tracker.set_games(remaining))
        self._games.delete(game_id)
        log.info("Jeu %d retiré de la bibliothèque avec son historique", game_id)
        self.game_removed.emit(game_id)

    @Slot(bool)
    def set_paused(self, paused: bool) -> None:
        if paused == self._tracker.paused:
            return
        if paused:
            self._timer.stop()  # aucune activité en fond pendant la pause
            self._dispatch(self._tracker.pause())
        else:
            self._tracker.resume()
            self._timer.start()
            self._tick()
        log.info("Suivi %s", "mis en pause" if paused else "repris")
        self.paused_changed.emit(paused)

    @Slot()
    def stop(self) -> None:
        if self._timer is not None:
            self._timer.stop()
        if self._tracker is not None:
            self._dispatch(self._tracker.shutdown())
        if self._conn is not None:
            self._conn.close()
            self._conn = None
        log.info("Suivi arrêté")

    @Slot()
    def _tick(self) -> None:
        try:
            self._dispatch(self._tracker.tick())
        except Exception:
            # Une erreur ponctuelle (base momentanément occupée, processus étrange…)
            # ne doit pas arrêter le suivi : on la note et on réessaie au tick suivant.
            log.exception("Erreur pendant le suivi")

    def _dispatch(self, events: list[TrackerEvent]) -> None:
        for event in events:
            match event:
                case GameStarted():
                    log.info("Jeu %d démarré", event.game_id)
                    self._remember_path(event)
                    self.game_started.emit(event)
                case GameStopped():
                    log.info(
                        "Jeu %d arrêté (%s) après %.0f s%s",
                        event.game_id,
                        event.reason,
                        event.ended_at - event.started_at,
                        "" if event.counted else ", session ignorée car trop courte",
                    )
                    self.game_stopped.emit(event)

    def _remember_path(self, event: GameStarted) -> None:
        """Enregistre le chemin de l'exe s'il est nouveau (ajout par nom, jeu déplacé)."""
        if event.exe_path is None:
            log.info("Jeu %d : chemin de l'exe illisible (processus protégé ?)", event.game_id)
            return
        game = self._games.get(event.game_id)
        if game is not None and game.exe_path != event.exe_path:
            self._games.update_exe_path(game.id, event.exe_path)
            self.game_path_found.emit(game.id, event.exe_path)
