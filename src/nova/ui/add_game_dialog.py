"""Fenêtre « Ajouter un jeu » : trois façons de désigner le jeu à suivre.

1. **Jeu en cours** (par défaut) : on lance le jeu, puis on le choisit dans la
   liste. Le jeu, gros consommateur de mémoire, arrive en tête et il est
   présélectionné. Les petits programmes (lanceurs, anti-triche) sont masqués :
   c'est le moyen le plus sûr de désigner le bon exécutable.
2. **Fichier .exe** : on choisit l'exécutable dans ses dossiers.
3. **Nom du processus** : on tape le nom ; chemin et icône viendront au premier lancement.
"""

import os
from pathlib import Path

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QFileDialog,
    QHBoxLayout,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from nova.core.models import Game
from nova.services.library import LibraryError, LibraryService
from nova.system.exe_info import pick_display_name, suggest_display_name
from nova.system.icons import icon_from_exe
from nova.system.processes import RunningProgram, list_running_programs
from nova.ui.formatting import sort_key
from nova.ui.widgets import make_button, make_label

# En dessous, un programme est masqué par défaut : les lanceurs et les outils
# d'anti-triche pèsent quelques Mo, un jeu en pèse des centaines, voire des milliers.
SMALL_PROGRAM_MEMORY = 50 * 1024 * 1024

# Position des onglets.
RUNNING_TAB, FILE_TAB, NAME_TAB = range(3)


class AddGameDialog(QDialog):
    def __init__(self, library: LibraryService, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._library = library
        self.added_game: Game | None = None
        self._programs: list[RunningProgram] = []
        self._names: dict[str, str] = {}  # chemin de l'exe -> nom proposé (lu une seule fois)
        self._icons: dict[str, QIcon] = {}
        self._name_edited = False  # l'utilisateur a modifié le nom affiché lui-même

        self.setWindowTitle("Ajouter un jeu")
        self.resize(580, 620)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 16, 20, 18)
        layout.setSpacing(10)

        self._tabs = QTabWidget()
        self._tabs.addTab(self._build_running_tab(), "Jeu en cours")
        self._tabs.addTab(self._build_file_tab(), "Fichier .exe")
        self._tabs.addTab(self._build_name_tab(), "Nom du processus")
        self._tabs.currentChanged.connect(self._on_tab_changed)
        layout.addWidget(self._tabs, 1)

        layout.addWidget(make_label("Nom affiché dans Nova", role="secondary"))
        self._display_name = QLineEdit()
        self._display_name.setPlaceholderText("Nom du jeu")
        self._display_name.textEdited.connect(self._on_name_edited)
        layout.addWidget(self._display_name)

        self._error = make_label(role="error", wrap=True)
        self._error.hide()
        layout.addWidget(self._error)

        buttons = QHBoxLayout()
        buttons.addStretch()
        cancel = make_button("Annuler")
        cancel.clicked.connect(self.reject)
        self._add = make_button("Ajouter", variant="primary")
        self._add.setDefault(True)
        self._add.clicked.connect(self._on_add_clicked)
        buttons.addWidget(cancel)
        buttons.addWidget(self._add)
        layout.addLayout(buttons)

        self._reload_programs()

    # --- Onglet « Jeu en cours » ---

    def _build_running_tab(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 12, 0, 0)
        layout.addWidget(
            make_label(
                "Lancez d'abord votre jeu, puis choisissez-le ci-dessous. Les programmes "
                "qui utilisent le plus de mémoire, comme les jeux, apparaissent en premier.",
                role="hint",
                wrap=True,
            )
        )
        row = QHBoxLayout()
        self._program_search = QLineEdit()
        self._program_search.setPlaceholderText("Rechercher un programme")
        self._program_search.setClearButtonEnabled(True)
        self._program_search.textChanged.connect(self._fill_program_list)
        refresh = make_button("Actualiser")
        refresh.clicked.connect(self._reload_programs)
        row.addWidget(self._program_search, 1)
        row.addWidget(refresh)
        layout.addLayout(row)

        self._program_list = QListWidget()
        self._program_list.setObjectName("programList")
        self._program_list.setIconSize(QSize(28, 28))
        self._program_list.currentItemChanged.connect(self._on_program_selected)
        self._program_list.itemDoubleClicked.connect(self._on_add_clicked)
        layout.addWidget(self._program_list, 1)

        self._show_small = QCheckBox("Afficher aussi les petits programmes (lanceurs, outils)")
        self._show_small.toggled.connect(self._fill_program_list)
        layout.addWidget(self._show_small)
        self._program_info = make_label(role="hint", wrap=True)
        layout.addWidget(self._program_info)
        return page

    def _reload_programs(self) -> None:
        # Nova elle-même (et, en développement, le lanceur de Python) n'est pas proposée.
        self._programs = list_running_programs(exclude_pids={os.getpid(), os.getppid()})
        self._fill_program_list()

    def _fill_program_list(self) -> None:
        tracked = self._library.tracked_process_names()
        query = sort_key(self._program_search.text().strip())
        self._program_list.clear()
        for program in self._programs:
            if program.memory < SMALL_PROGRAM_MEMORY and not self._show_small.isChecked():
                continue
            name = self._suggested_name(program.exe_path)
            if query and query not in sort_key(name) and query not in program.process_name:
                continue
            item = QListWidgetItem(self._icon(program.exe_path), name)
            item.setData(Qt.ItemDataRole.UserRole, program)
            item.setToolTip(program.exe_path)
            if program.process_name in tracked:
                item.setText(f"{name}  (déjà dans la bibliothèque)")
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEnabled)
            self._program_list.addItem(item)

        first = next(
            (
                self._program_list.item(i)
                for i in range(self._program_list.count())
                if self._program_list.item(i).flags() & Qt.ItemFlag.ItemIsEnabled
            ),
            None,
        )
        self._program_list.setCurrentItem(first)
        if first is None:
            self._program_info.setText(
                "Aucun programme trouvé. Lancez votre jeu, puis cliquez sur « Actualiser »."
            )
        self._update_state()

    def _on_program_selected(self, item: QListWidgetItem | None) -> None:
        if item is None:
            return
        program: RunningProgram = item.data(Qt.ItemDataRole.UserRole)
        self._program_info.setText(f"Exécutable suivi : {Path(program.exe_path).name}")
        self._suggest_name(self._suggested_name(program.exe_path))
        self._update_state()

    # --- Onglet « Fichier .exe » ---

    def _build_file_tab(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 12, 0, 0)
        layout.addWidget(
            make_label(
                "Choisissez l'exécutable du jeu lui-même. Pour un jeu lancé par Steam, Epic "
                "ou Riot, l'onglet « Jeu en cours » est plus sûr : le bon fichier n'est pas "
                "toujours celui du raccourci.",
                role="hint",
                wrap=True,
            )
        )
        row = QHBoxLayout()
        self._file_path = QLineEdit()
        self._file_path.setReadOnly(True)
        self._file_path.setPlaceholderText("Aucun fichier choisi")
        browse = make_button("Parcourir…")
        browse.clicked.connect(self._browse)
        row.addWidget(self._file_path, 1)
        row.addWidget(browse)
        layout.addLayout(row)
        layout.addStretch()
        return page

    def _browse(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Choisir l'exécutable du jeu", "", "Programmes (*.exe)"
        )
        if path:
            path = str(Path(path))  # séparateurs Windows (« \ »)
            self._file_path.setText(path)
            self._suggest_name(self._suggested_name(path))
            self._update_state()

    # --- Onglet « Nom du processus » ---

    def _build_name_tab(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 12, 0, 0)
        layout.addWidget(
            make_label(
                "Tapez le nom exact du processus, tel qu'il apparaît dans le Gestionnaire "
                "des tâches (onglet « Détails »). Le chemin et l'icône seront récupérés "
                "automatiquement au premier lancement du jeu.",
                role="hint",
                wrap=True,
            )
        )
        self._process_name = QLineEdit()
        self._process_name.setPlaceholderText("jeu.exe")
        self._process_name.textChanged.connect(self._on_process_name_changed)
        layout.addWidget(self._process_name)
        layout.addStretch()
        return page

    def _on_process_name_changed(self, text: str) -> None:
        stem = Path(text.strip()).stem if text.strip() else ""
        self._suggest_name(pick_display_name({}, stem) if stem else "")
        self._update_state()

    # --- Commun aux trois onglets ---

    def _request(self) -> tuple[str, str | None] | None:
        """(nom du processus, chemin de l'exe) désignés par l'onglet courant, ou None."""
        tab = self._tabs.currentIndex()
        if tab == RUNNING_TAB:
            item = self._program_list.currentItem()
            if item is None or not item.flags() & Qt.ItemFlag.ItemIsEnabled:
                return None
            program: RunningProgram = item.data(Qt.ItemDataRole.UserRole)
            return program.process_name, program.exe_path
        if tab == FILE_TAB:
            path = self._file_path.text()
            return (Path(path).name, path) if path else None
        name = self._process_name.text().strip()
        return (name, None) if name else None

    def _on_add_clicked(self) -> None:
        request = self._request()
        if request is None:
            return
        process_name, exe_path = request
        try:
            self.added_game = self._library.add_game(
                process_name, self._display_name.text(), exe_path
            )
        except LibraryError as error:
            self._show_error(str(error))
            return
        self.accept()

    def _on_tab_changed(self) -> None:
        # Chaque onglet propose son propre nom, tant que l'utilisateur n'en a pas tapé un.
        self._name_edited = False
        tab = self._tabs.currentIndex()
        if tab == RUNNING_TAB:
            self._on_program_selected(self._program_list.currentItem())
        elif tab == FILE_TAB:
            path = self._file_path.text()
            self._suggest_name(self._suggested_name(path) if path else "")
        else:
            self._on_process_name_changed(self._process_name.text())
        self._update_state()

    def _on_name_edited(self) -> None:
        self._name_edited = True

    def _suggest_name(self, name: str) -> None:
        if not self._name_edited:
            self._display_name.setText(name)

    def _update_state(self) -> None:
        self._add.setEnabled(self._request() is not None)
        self._show_error("")

    def _show_error(self, message: str) -> None:
        self._error.setText(message)
        self._error.setVisible(bool(message))

    def _suggested_name(self, exe_path: str) -> str:
        if exe_path not in self._names:
            self._names[exe_path] = suggest_display_name(exe_path)
        return self._names[exe_path]

    def _icon(self, exe_path: str) -> QIcon:
        if exe_path not in self._icons:
            self._icons[exe_path] = icon_from_exe(exe_path)
        return self._icons[exe_path]
