"""Journal de Nova : fichier ``logs\\nova.log`` dans le dossier des données.

Nova tourne sans console : sans journal, une erreur passerait inaperçue. Le
fichier tourne à 1 Mo (3 anciens fichiers gardés) pour ne jamais grossir sans fin.
On n'y écrit que des événements (jeu démarré, arrêté, erreur), jamais à chaque scan.
"""

import logging
import sys
import threading
from logging.handlers import RotatingFileHandler
from pathlib import Path

_FORMAT = "%(asctime)s %(levelname)-7s [%(threadName)s] %(name)s : %(message)s"


def setup_logging(logs_dir: Path, *, console_level: int | None = None) -> None:
    """Configure le journal de toute l'application.

    ``console_level`` affiche aussi à l'écran les messages de ce niveau ou plus graves
    (utile pour les scripts de développement) ; None : fichier seulement.
    """
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    for handler in list(root.handlers):
        root.removeHandler(handler)
        handler.close()

    file_handler = RotatingFileHandler(
        logs_dir / "nova.log", maxBytes=1_000_000, backupCount=3, encoding="utf-8"
    )
    file_handler.setFormatter(logging.Formatter(_FORMAT))
    root.addHandler(file_handler)

    # Dans l'exe sans console, sys.stderr vaut None : on n'affiche alors rien.
    if console_level is not None and sys.stderr is not None:
        stream_handler = logging.StreamHandler()
        stream_handler.setLevel(console_level)
        stream_handler.setFormatter(logging.Formatter("%(asctime)s %(message)s", "%H:%M:%S"))
        root.addHandler(stream_handler)

    _log_uncaught_exceptions()


def _log_uncaught_exceptions() -> None:
    """Envoie au journal les erreurs qui ne sont rattrapées nulle part."""
    log = logging.getLogger("nova")

    def on_main_thread_error(exc_type, exc, tb):
        if issubclass(exc_type, KeyboardInterrupt):
            sys.__excepthook__(exc_type, exc, tb)  # Ctrl+C : arrêt normal, pas une erreur
            return
        log.critical("Erreur non rattrapée", exc_info=(exc_type, exc, tb))

    def on_thread_error(args: threading.ExceptHookArgs) -> None:
        log.critical(
            "Erreur non rattrapée dans le thread %s",
            args.thread.name if args.thread else "?",
            exc_info=(args.exc_type, args.exc_value, args.exc_traceback),
        )

    sys.excepthook = on_main_thread_error
    threading.excepthook = on_thread_error
