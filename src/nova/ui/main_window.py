"""Fenêtre principale : liste des jeux à gauche, fiche du jeu sélectionné à droite."""

import time

from PySide6.QtCore import QModelIndex, QPoint, QSize, Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListView,
    QMainWindow,
    QMenu,
    QMessageBox,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from nova.core.events import GameStarted, GameStopped
from nova.services.library import LibraryService
from nova.services.tracking import TrackingService
from nova.system.paths import asset_path
from nova.ui.add_game_dialog import AddGameDialog
from nova.ui.formatting import format_duration
from nova.ui.game_details import EmptyLibrary, GameDetails
from nova.ui.library_model import GameFilterProxy, GameItemDelegate, GameListModel, SortMode
from nova.ui.widgets import make_button

SIDEBAR_WIDTH = 270


class MainWindow(QMainWindow):
    def __init__(self, library: LibraryService, tracking: TrackingService) -> None:
        super().__init__()
        self._library = library
        self._running: dict[int, float] = {}  # id du jeu -> début de la session en cours
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

        library.changed.connect(self.refresh)
        tracking.ready.connect(self.refresh)
        tracking.game_started.connect(self._on_game_started)
        tracking.game_stopped.connect(self._on_game_stopped)
        self._empty.add_requested.connect(self.open_add_dialog)
        self._details.remove_requested.connect(self.confirm_remove)
        self.refresh()

    def _build_sidebar(self) -> QWidget:
        sidebar = QWidget()
        sidebar.setObjectName("sidebar")
        sidebar.setAttribute(Qt.WidgetAttribute.WA_StyledBackground)
        sidebar.setFixedWidth(SIDEBAR_WIDTH)
        layout = QVBoxLayout(sidebar)
        layout.setContentsMargins(12, 14, 12, 12)
        layout.setSpacing(10)

        header = QHBoxLayout()
        logo = QLabel()
        logo.setPixmap(
            QPixmap(str(asset_path("logo.png"))).scaled(
                26,
                26,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
        )
        title = QLabel("Nova")
        title.setObjectName("appTitle")
        header.addWidget(logo)
        header.addWidget(title)
        header.addStretch()
        layout.addLayout(header)

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
        self._model.set_library(self._library.games(), self._library.stats(), self._running)
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
            self._details.show_game(row, time.time())
        self._pages.setCurrentWidget(self._details)

    def _on_game_started(self, event: GameStarted) -> None:
        self._running[event.game_id] = event.started_at
        self._model.set_running(event.game_id, event.started_at)
        self._update_details()

    def _on_game_stopped(self, event: GameStopped) -> None:
        self._running.pop(event.game_id, None)
        self.refresh()  # la session vient d'être enregistrée : les statistiques changent

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
