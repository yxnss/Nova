"""Assemblage de l'application : crée chaque élément et les relie entre eux.

C'est le seul endroit qui connaît toutes les couches. L'ordre compte :
1. le journal, pour noter tout problème dès le départ ;
2. l'instance unique : si Nova tourne déjà, on la réveille et on s'arrête là ;
3. la connexion SQLite de l'interface, qui crée ou met à jour la base ;
4. le thread de suivi, qui ouvre sa propre connexion sur une base déjà prête ;
5. la fenêtre et l'icône du systray, reliées par des signaux.
"""

import logging
import sys

from PySide6.QtGui import QIcon, QSessionManager
from PySide6.QtWidgets import QApplication

from nova import __version__
from nova.data.database import connect
from nova.services.library import LibraryService
from nova.services.tracking import TrackingService
from nova.system.autostart import AutoStart
from nova.system.banners import BannerStore
from nova.system.icons import IconCache
from nova.system.logging_setup import setup_logging
from nova.system.paths import (
    asset_path,
    banners_dir,
    data_dir,
    database_path,
    icons_dir,
    logs_dir,
    settings_path,
)
from nova.system.settings import AppSettings
from nova.system.single_instance import SingleInstance
from nova.system.windows import allow_any_process_to_take_focus, set_app_user_model_id
from nova.ui.main_window import MainWindow
from nova.ui.theme import apply_theme
from nova.ui.tray import TrayIcon

log = logging.getLogger(__name__)

CLOSE_NOTICE = (
    "Nova continue de mesurer votre temps de jeu en arrière-plan. "
    "Cliquez sur son icône pour la rouvrir, ou faites un clic droit pour la quitter."
)


def run(minimized: bool = False) -> int:
    setup_logging(logs_dir())
    set_app_user_model_id()

    app = QApplication(sys.argv[:1])
    app.setApplicationName("Nova")
    app.setWindowIcon(QIcon(str(asset_path("logo.png"))))
    # Fermer la fenêtre ne quitte pas Nova : seul « Quitter Nova » le fait.
    app.setQuitOnLastWindowClosed(False)

    instance = SingleInstance(data_dir())
    if not instance.acquire():
        # Nova tourne déjà. Lancée par l'utilisateur, cette instance réveille la première ;
        # lancée par le démarrage automatique, elle se ferme sans rien afficher.
        if not minimized:
            allow_any_process_to_take_focus()
            instance.wake_up_running_instance()
        log.info("Nova tourne déjà : cette nouvelle instance se ferme")
        return 0

    log.info("Démarrage de Nova %s%s", __version__, " (réduite)" if minimized else "")
    apply_theme(app)
    db_path = database_path()
    conn = connect(db_path)
    tracking = TrackingService(db_path)
    library = LibraryService(conn, tracking, IconCache(icons_dir()), BannerStore(banners_dir()))
    settings = AppSettings(settings_path())
    autostart = AutoStart()
    try:
        autostart.repair()
    except OSError:
        log.warning("Impossible de vérifier le démarrage automatique", exc_info=True)

    window = MainWindow(library, tracking, autostart)
    tray = TrayIcon(window.recent_games)

    def quit_nova() -> None:
        window.prepare_quit()
        app.quit()

    def on_closed_to_tray() -> None:
        # Une seule fois : expliquer que Nova n'est pas arrêtée.
        if not settings.close_notice_shown:
            tray.notify("Nova est toujours active", CLOSE_NOTICE)
            settings.close_notice_shown = True

    def on_windows_session_end(manager: QSessionManager) -> None:
        # Arrêt ou déconnexion de Windows : on clôture les sessions tout de suite, à la
        # seconde près, sans attendre la réparation au prochain démarrage.
        log.info("Fin de session Windows : arrêt du suivi")
        window.prepare_quit()
        tracking.stop()

    def update_running_games() -> None:
        tray.set_running_games(window.running_game_names())

    tray.open_requested.connect(window.show_and_raise)
    tray.game_requested.connect(window.show_game)
    tray.settings_requested.connect(window.open_settings)
    tray.pause_requested.connect(tracking.set_paused)
    tray.quit_requested.connect(quit_nova)
    window.pause_requested.connect(tracking.set_paused)
    window.closed_to_tray.connect(on_closed_to_tray)
    tracking.paused_changed.connect(tray.set_paused)
    tracking.paused_changed.connect(window.set_paused)
    tracking.game_started.connect(update_running_games)
    tracking.game_stopped.connect(update_running_games)
    instance.activation_requested.connect(window.show_and_raise)
    app.commitDataRequest.connect(on_windows_session_end)
    app.aboutToQuit.connect(tracking.stop)
    app.aboutToQuit.connect(tray.hide)

    tracking.start()
    tray.show()
    if not minimized:
        window.show()
    code = app.exec()
    conn.close()
    instance.release()
    log.info("Nova s'est arrêtée")
    return code
