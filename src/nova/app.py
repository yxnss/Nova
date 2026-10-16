"""Assemblage de l'application : crée chaque élément et les relie entre eux.

C'est le seul endroit qui connaît toutes les couches. L'ordre compte :
1. le journal, pour noter tout problème dès le départ ;
2. l'instance unique : si Nova tourne déjà, on la réveille et on s'arrête là ;
3. la connexion SQLite de l'interface, qui crée ou met à jour la base ;
4. le thread de suivi, qui ouvre sa propre connexion sur une base déjà prête ;
5. la fenêtre et l'icône du systray, reliées par des signaux.
"""

from __future__ import annotations

import logging
import sys
from collections.abc import Callable
from typing import TYPE_CHECKING

from PySide6.QtCore import QLibraryInfo, QTimer, QTranslator
from PySide6.QtGui import QIcon, QSessionManager
from PySide6.QtWidgets import QApplication, QMessageBox

from nova import __version__
from nova.data.backup import backup_if_needed, open_or_recover
from nova.data.database import UnsupportedDatabaseVersion
from nova.services.library import LibraryService
from nova.services.tracking import TrackingService
from nova.system.autostart import AutoStart
from nova.system.banners import BannerStore
from nova.system.icons import IconCache
from nova.system.logging_setup import setup_logging
from nova.system.paths import (
    asset_path,
    backups_dir,
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
from nova.ui.icons import generic_game_icon
from nova.ui.theme import apply_theme
from nova.ui.tray import RecentGame, TrayIcon

if TYPE_CHECKING:  # seulement pour les annotations : la fenêtre est importée à la demande
    from nova.ui.main_window import MainWindow

log = logging.getLogger(__name__)

CLOSE_NOTICE = (
    "Nova continue de mesurer votre temps de jeu en arrière-plan. "
    "Cliquez sur son icône pour la rouvrir, ou faites un clic droit pour la quitter."
)


class LazyWindow:
    """Fenêtre principale créée seulement à sa première ouverture.

    Nova lancée avec Windows reste dans le systray : tant qu'on ne l'ouvre pas, la
    fenêtre n'existe pas, ce qui divise presque par deux la mémoire utilisée.
    """

    def __init__(self, factory: Callable[[], MainWindow]) -> None:
        self._factory = factory
        self._window: MainWindow | None = None

    def get(self) -> MainWindow:
        if self._window is None:
            self._window = self._factory()
        return self._window

    def prepare_quit(self) -> None:
        if self._window is not None:
            self._window.prepare_quit()


def run(minimized: bool = False) -> int:
    setup_logging(logs_dir())
    set_app_user_model_id()

    app = QApplication(sys.argv[:1])
    app.setApplicationName("Nova")
    app.setWindowIcon(QIcon(str(asset_path("logo_small.png"))))
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
    # Textes standard de Qt en français (menu du clic droit dans les champs de saisie…).
    translator = QTranslator(app)
    if translator.load("qtbase_fr", QLibraryInfo.path(QLibraryInfo.LibraryPath.TranslationsPath)):
        app.installTranslator(translator)
    db_path = database_path()
    try:
        conn, recovery_message = open_or_recover(db_path, backups_dir())
    except UnsupportedDatabaseVersion:
        QMessageBox.critical(
            None,
            "Nova",
            "Votre bibliothèque a été créée par une version plus récente de Nova. "
            "Installez la dernière version de Nova pour l'ouvrir.",
        )
        instance.release()
        return 1
    if recovery_message:
        QMessageBox.warning(None, "Nova", recovery_message)
    backup_if_needed(conn, backups_dir())
    # Nova peut tourner des jours sans redémarrer : on vérifie chaque heure s'il faut
    # faire la sauvegarde du jour (une seule écriture par jour).
    backup_timer = QTimer()
    backup_timer.timeout.connect(lambda: backup_if_needed(conn, backups_dir()))
    backup_timer.start(60 * 60 * 1000)
    tracking = TrackingService(db_path)
    library = LibraryService(conn, tracking, IconCache(icons_dir()), BannerStore(banners_dir()))
    settings = AppSettings(settings_path())
    autostart = AutoStart()
    try:
        autostart.repair()
    except OSError:
        log.warning("Impossible de vérifier le démarrage automatique", exc_info=True)

    def recent_games() -> list[RecentGame]:
        return [
            RecentGame(
                game.id, game.display_name, library.icon(game.id) or generic_game_icon(), running
            )
            for game, running in library.recent_games()
        ]

    tray = TrayIcon(recent_games)
    paused = False

    def on_closed_to_tray() -> None:
        # Une seule fois : expliquer que Nova n'est pas arrêtée.
        if not settings.close_notice_shown:
            tray.notify("Nova est toujours active", CLOSE_NOTICE)
            settings.close_notice_shown = True

    def create_window() -> MainWindow:
        # Import ici : les modules de la fenêtre ne sont chargés qu'à sa première ouverture.
        from nova.ui.main_window import MainWindow

        main_window = MainWindow(library, tracking, autostart)
        main_window.set_paused(paused)
        main_window.pause_requested.connect(tracking.set_paused)
        main_window.closed_to_tray.connect(on_closed_to_tray)
        tracking.paused_changed.connect(main_window.set_paused)
        return main_window

    window = LazyWindow(create_window)

    def quit_nova() -> None:
        window.prepare_quit()
        app.quit()

    def on_windows_session_end(manager: QSessionManager) -> None:
        # Arrêt ou déconnexion de Windows : on clôture les sessions tout de suite, à la
        # seconde près, sans attendre la réparation au prochain démarrage.
        log.info("Fin de session Windows : arrêt du suivi")
        window.prepare_quit()
        tracking.stop()

    def on_paused_changed(is_paused: bool) -> None:
        nonlocal paused
        paused = is_paused

    tray.open_requested.connect(lambda: window.get().show_and_raise())
    tray.game_requested.connect(lambda game_id: window.get().show_game(game_id))
    tray.settings_requested.connect(lambda: window.get().open_settings())
    tray.pause_requested.connect(tracking.set_paused)
    tray.quit_requested.connect(quit_nova)
    tracking.paused_changed.connect(on_paused_changed)
    tracking.paused_changed.connect(tray.set_paused)
    tracking.game_started.connect(lambda _: tray.set_running_games(library.running_names()))
    tracking.game_stopped.connect(lambda _: tray.set_running_games(library.running_names()))
    instance.activation_requested.connect(lambda: window.get().show_and_raise())
    app.commitDataRequest.connect(on_windows_session_end)
    app.aboutToQuit.connect(tracking.stop)
    app.aboutToQuit.connect(tray.hide)

    tracking.start()
    tray.show()
    if not minimized:
        window.get().show()
    code = app.exec()
    conn.close()
    instance.release()
    log.info("Nova s'est arrêtée")
    return code
