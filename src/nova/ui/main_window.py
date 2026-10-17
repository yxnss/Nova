"""Fenêtre principale : liste des jeux à gauche, fiche du jeu sélectionné à droite."""

from pathlib import Path

from PySide6.QtCore import QEvent, QModelIndex, QPoint, QSize, Qt, Signal
from PySide6.QtGui import QCloseEvent, QHideEvent, QPixmap, QShowEvent
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListView,
    QMainWindow,
    QMenu,
    QMessageBox,
    QStackedWidget,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from nova.core.events import GameStarted, GameStopped
from nova.services.library import LibraryError, LibraryService
from nova.services.tracking import TrackingService
from nova.system.autostart import AutoStart
from nova.system.banners import IMAGE_FILTER
from nova.system.paths import asset_path
from nova.ui.add_game_dialog import AddGameDialog
from nova.ui.formatting import format_duration
from nova.ui.game_details import EmptyLibrary, GameDetails
from nova.ui.icons import gear_icon
from nova.ui.library_model import GameFilterProxy, GameItemDelegate, GameListModel, SortMode
from nova.ui.settings_dialog import SettingsDialog
from nova.ui.title_bar import CAPTION_HEIGHT, WindowFrame
from nova.ui.widgets import make_button, make_label

SIDEBAR_WIDTH = 270


class MainWindow(QMainWindow):
    pause_requested = Signal(bool)  # True : mettre en pause ; False : reprendre
    closed_to_tray = Signal()  # la fenêtre vient d'être rangée dans le systray

    def __init__(
        self,
        library: LibraryService,
        tracking: TrackingService,
        autostart: AutoStart | None = None,
    ) -> None:
        super().__init__()
        self._library = library
        self._autostart = autostart
        self._paused = False
        self._quitting = False  # vrai seulement quand Nova quitte pour de bon
        self._settings_dialog: SettingsDialog | None = None
        self._model = GameListModel(library.icon)
        self._proxy = GameFilterProxy(self._model)

        self.setWindowTitle("Nova")
        self.resize(1100, 680)
        self.setMinimumSize(860, 540)

        central = QWidget()
        layout = QHBoxLayout(central)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self._build_sidebar())
        self._pages = QStackedWidget()
        self._empty = EmptyLibrary()
        self._details = GameDetails()
        self._pages.addWidget(self._empty)
        self._pages.addWidget(self._details)
        layout.addWidget(self._pages, 1)
        self.setCentralWidget(central)
        # Barre de titre intégrée : la barre latérale et la bannière montent jusqu'en haut.
        self._frame = WindowFrame(self)

        library.changed.connect(self.refresh)
        library.launch_state_changed.connect(self._update_details)
        tracking.ready.connect(self.refresh)
        tracking.game_started.connect(self._on_game_started)
        tracking.game_stopped.connect(self._on_game_stopped)
        self._empty.add_requested.connect(self.open_add_dialog)
        self._details.remove_requested.connect(self.confirm_remove)
        self._details.launch_requested.connect(self._launch)
        self._details.change_banner_requested.connect(self._choose_banner)
        self._details.reset_banner_requested.connect(library.reset_banner)
        self.refresh()

    def _build_sidebar(self) -> QWidget:
        sidebar = QWidget()
        sidebar.setObjectName("sidebar")
        sidebar.setAttribute(Qt.WidgetAttribute.WA_StyledBackground)
        sidebar.setFixedWidth(SIDEBAR_WIDTH)
        layout = QVBoxLayout(sidebar)
        layout.setContentsMargins(12, 0, 12, 12)
        layout.setSpacing(10)

        # En-tête de la hauteur de la barre de titre : le logo s'aligne sur les boutons
        # de la fenêtre, et cette zone sert aussi à déplacer la fenêtre.
        header_area = QWidget()
        header_area.setObjectName("sidebarHeader")
        header_area.setFixedHeight(CAPTION_HEIGHT)
        header = QHBoxLayout(header_area)
        header.setContentsMargins(0, 0, 0, 0)
        logo = QLabel()
        logo.setPixmap(
            QPixmap(str(asset_path("logo_small.png"))).scaled(
                26,
                26,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
        )
        title = QLabel("Nova")
        title.setObjectName("appTitle")
        settings = QToolButton()
        settings.setObjectName("settingsButton")
        settings.setIcon(gear_icon())
        settings.setIconSize(QSize(18, 18))
        settings.setAutoRaise(True)  # icône plus claire au survol
        settings.setToolTip("Paramètres")
        settings.setCursor(Qt.CursorShape.PointingHandCursor)
        settings.clicked.connect(self.open_settings)
        header.addWidget(logo)
        header.addWidget(title)
        header.addStretch()
        header.addWidget(settings)
        layout.addWidget(header_area)

        # Bandeau visible seulement pendant la pause du suivi.
        self._pause_banner = QFrame()
        self._pause_banner.setObjectName("pauseBanner")
        banner_layout = QHBoxLayout(self._pause_banner)
        banner_layout.setContentsMargins(10, 6, 6, 6)
        banner_layout.addWidget(make_label("Suivi en pause"), 1)
        resume = make_button("Reprendre", variant="link")
        resume.clicked.connect(lambda: self.pause_requested.emit(False))
        banner_layout.addWidget(resume)
        self._pause_banner.hide()
        layout.addWidget(self._pause_banner)

        self._search = QLineEdit()
        self._search.setPlaceholderText("Rechercher un jeu")
        self._search.setClearButtonEnabled(True)
        self._search.textChanged.connect(self._proxy.set_search)
        layout.addWidget(self._search)

        self._sort = QComboBox()
        for mode in SortMode:
            self._sort.addItem(mode.value, mode)
        self._sort.currentIndexChanged.connect(
            lambda: self._proxy.set_sort_mode(self._sort.currentData())
        )
        layout.addWidget(self._sort)

        self._list = QListView()
        self._list.setObjectName("gameList")
        self._list.setModel(self._proxy)
        self._list.setItemDelegate(GameItemDelegate(self._list))
        self._list.setIconSize(QSize(24, 24))
        self._list.setUniformItemSizes(True)
        self._list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._list.customContextMenuRequested.connect(self._show_context_menu)
        self._list.selectionModel().currentChanged.connect(lambda *_: self._update_details())
        layout.addWidget(self._list, 1)

        add_button = make_button("+  Ajouter un jeu", variant="add")
        add_button.clicked.connect(self.open_add_dialog)
        layout.addWidget(add_button)
        return sidebar

    # --- Mise à jour de l'affichage ---

    def refresh(self) -> None:
        """Relit la bibliothèque et les statistiques, en gardant le jeu sélectionné."""
        selected = self._selected_game_id()
        self._model.set_library(
            self._library.games(), self._library.stats(), self._library.running()
        )
        self._select(selected)
        self._update_details()

    def _selected_game_id(self) -> int | None:
        index = self._list.currentIndex()
        return index.data(GameListModel.GameIdRole) if index.isValid() else None

    def _select(self, game_id: int | None) -> None:
        """Sélectionne le jeu demandé, ou le premier de la liste s'il n'est plus visible."""
        target = QModelIndex()
        for row in range(self._proxy.rowCount()):
            index = self._proxy.index(row, 0)
            if index.data(GameListModel.GameIdRole) == game_id:
                target = index
                break
        if not target.isValid() and self._proxy.rowCount():
            target = self._proxy.index(0, 0)
        self._list.setCurrentIndex(target)

    def _update_details(self) -> None:
        if self._model.rowCount() == 0:
            self._pages.setCurrentWidget(self._empty)
            return
        game_id = self._selected_game_id()
        row = self._model.find(game_id) if game_id is not None else None
        if row is not None:
            self._details.show_game(
                row,
                launching=self._library.is_launching(row.game.id),
                banner=self._library.banner_path(row.game),
                icon=self._library.icon(row.game.id),
            )
        self._pages.setCurrentWidget(self._details)

    def nativeEvent(self, event_type, message) -> tuple[bool, int]:
        answer = self._frame.native_event(int(message))
        return answer if answer is not None else super().nativeEvent(event_type, message)

    # --- Compteur en direct : seulement si la fenêtre est visible et non réduite ---

    def showEvent(self, event: QShowEvent) -> None:
        super().showEvent(event)
        self._update_live_display()

    def hideEvent(self, event: QHideEvent) -> None:
        super().hideEvent(event)
        self._update_live_display()

    def changeEvent(self, event: QEvent) -> None:
        super().changeEvent(event)
        if event.type() == QEvent.Type.WindowStateChange:
            self._update_live_display()

    def _update_live_display(self) -> None:
        self._details.set_live_allowed(self.isVisible() and not self.isMinimized())

    # --- Cycle de vie : fermer la fenêtre range Nova dans le systray ---

    def closeEvent(self, event: QCloseEvent) -> None:
        if self._quitting:
            event.accept()
            return
        # Le suivi continue : la fenêtre est seulement cachée.
        event.ignore()
        self.hide()
        self.closed_to_tray.emit()

    def prepare_quit(self) -> None:
        """À appeler avant de quitter Nova : la fermeture de la fenêtre est alors acceptée."""
        self._quitting = True

    def show_and_raise(self) -> None:
        """Affiche la fenêtre au premier plan (depuis le systray ou une autre instance)."""
        if self.isMinimized():
            self.showNormal()
        self.show()
        self.raise_()
        self.activateWindow()

    def show_game(self, game_id: int) -> None:
        """Affiche la fenêtre sur la fiche d'un jeu (menu du systray)."""
        self._search.clear()
        self._select(game_id)
        self._update_details()
        self.show_and_raise()

    # --- Pause et paramètres ---

    def set_paused(self, paused: bool) -> None:
        self._paused = paused
        self._pause_banner.setVisible(paused)
        if self._settings_dialog is not None:
            self._settings_dialog.set_paused(paused)

    def open_settings(self) -> None:
        if self._settings_dialog is None:
            self._settings_dialog = SettingsDialog(self._autostart, self._paused, self)
            self._settings_dialog.pause_requested.connect(self.pause_requested)
        self._settings_dialog.set_paused(self._paused)
        self._settings_dialog.show()
        self._settings_dialog.raise_()
        self._settings_dialog.activateWindow()

    def _on_game_started(self, event: GameStarted) -> None:
        self._model.set_running(event.game_id, event.started_at)
        self._update_details()

    def _on_game_stopped(self, event: GameStopped) -> None:
        self.refresh()  # la session vient d'être enregistrée : les statistiques changent

    # --- Lancement et bannière ---

    def _launch(self, game_id: int) -> None:
        try:
            self._library.launch_game(game_id)
        except LibraryError:
            pass  # la raison est enregistrée et s'affiche sous le bouton « Lancer »
        self._update_details()

    def _choose_banner(self, game_id: int) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Choisir une bannière", str(Path.home() / "Pictures"), IMAGE_FILTER
        )
        if not path:
            return
        try:
            self._library.set_banner(game_id, path)
        except LibraryError as error:
            QMessageBox.warning(self, "Bannière", str(error))

    # --- Ajout et retrait ---

    def open_add_dialog(self) -> None:
        dialog = AddGameDialog(self._library, self)
        if dialog.exec() == QDialog.DialogCode.Accepted and dialog.added_game is not None:
            self._search.clear()
            self._select(dialog.added_game.id)
            self._update_details()

    def confirm_remove(self, game_id: int) -> None:
        row = self._model.find(game_id)
        if row is None:
            return
        details = (
            f"Son historique ({format_duration(row.stats.total_seconds)} de jeu) "
            "sera supprimé définitivement."
        )
        if row.running:
            details += "\nLe jeu est en cours : son suivi s'arrêtera immédiatement."
        box = QMessageBox(self)
        box.setIcon(QMessageBox.Icon.Warning)
        box.setWindowTitle("Retirer de la bibliothèque")
        box.setText(f"Retirer « {row.game.display_name} » de votre bibliothèque ?")
        box.setInformativeText(details)
        remove = box.addButton("Retirer", QMessageBox.ButtonRole.DestructiveRole)
        cancel = box.addButton("Annuler", QMessageBox.ButtonRole.RejectRole)
        box.setDefaultButton(cancel)
        box.exec()
        if box.clickedButton() is remove:
            self._library.remove_game(game_id)

    def _show_context_menu(self, position: QPoint) -> None:
        index = self._list.indexAt(position)
        if not index.isValid():
            return
        menu = QMenu(self)
        remove = menu.addAction("Retirer de la bibliothèque…")
        if menu.exec(self._list.viewport().mapToGlobal(position)) is remove:
            self.confirm_remove(index.data(GameListModel.GameIdRole))
