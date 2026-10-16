"""Petits appels à l'API Windows (via ctypes, module standard)."""

import ctypes
import logging
import sys

log = logging.getLogger(__name__)

APP_USER_MODEL_ID = "Nova.GameTimeTracker"


def set_app_user_model_id() -> None:
    """Donne à Nova sa propre identité dans la barre des tâches.

    Sans cela, pendant le développement, Windows regroupe la fenêtre avec Python et
    affiche l'icône de Python au lieu de celle de Nova.
    """
    if sys.platform != "win32":
        return
    try:
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(APP_USER_MODEL_ID)
    except OSError:
        log.warning("Impossible de définir l'identité de Nova dans la barre des tâches")


def allow_any_process_to_take_focus() -> None:
    """Autorise la première instance de Nova à passer au premier plan.

    Windows interdit à un programme en arrière-plan de voler le focus : sans cet
    appel, la fenêtre réveillée se contenterait de clignoter dans la barre des
    tâches. La nouvelle instance, lancée par l'utilisateur, a le droit de céder
    ce privilège juste avant de demander le réveil.
    """
    if sys.platform != "win32":
        return
    asfw_any = 0xFFFFFFFF  # ASFW_ANY : n'importe quel processus
    ctypes.windll.user32.AllowSetForegroundWindow(asfw_any)
