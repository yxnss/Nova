"""Assemblage de l'application : crée chaque élément et les relie entre eux.

C'est le seul endroit qui connaît toutes les couches. L'ordre compte :
1. le journal, pour noter tout problème dès le départ ;
2. la connexion SQLite de l'interface, qui crée ou met à jour la base ;
3. le thread de suivi, qui ouvre sa propre connexion sur une base déjà prête.
"""

import logging
import sys

from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication

from nova import __version__
from nova.data.database import connect
from nova.services.library import LibraryService
from nova.services.tracking import TrackingService
from nova.system.banners import BannerStore
from nova.system.icons import IconCache
from nova.system.logging_setup import setup_logging
from nova.system.paths import asset_path, banners_dir, database_path, icons_dir, logs_dir
from nova.system.windows import set_app_user_model_id
from nova.ui.main_window import MainWindow
from nova.ui.theme import apply_theme

log = logging.getLogger(__name__)


def run() -> int:
    setup_logging(logs_dir())
    log.info("Démarrage de Nova %s", __version__)
    set_app_user_model_id()

    app = QApplication(sys.argv[:1])
    app.setApplicationName("Nova")
    app.setWindowIcon(QIcon(str(asset_path("logo.png"))))
    apply_theme(app)

    db_path = database_path()
    conn = connect(db_path)
    tracking = TrackingService(db_path)
    library = LibraryService(conn, tracking, IconCache(icons_dir()), BannerStore(banners_dir()))
    window = MainWindow(library, tracking)

    # Fermer la fenêtre quitte Nova pour l'instant (le systray arrive à l'étape 5) :
    # le suivi s'arrête alors proprement en clôturant les sessions en cours.
    app.aboutToQuit.connect(tracking.stop)
    tracking.start()
    window.show()
    code = app.exec()
    conn.close()
    log.info("Nova s'est arrêtée")
    return code
