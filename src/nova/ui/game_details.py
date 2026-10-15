"""Panneau de droite : fiche du jeu sélectionné, ou invitation si la bibliothèque est vide.

Version de l'étape 3 : nom, statut, statistiques et retrait. La bannière, le
compteur en direct et le bouton « Lancer » arrivent à l'étape 4.
"""

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QVBoxLayout, QWidget

from nova.data.stats import add_running_session
from nova.system.paths import asset_path
from nova.ui.formatting import format_clock, format_duration, format_last_played
from nova.ui.library_model import GameRow
from nova.ui.widgets import make_button, make_label, set_style_property


class _StatCard(QFrame):
    def __init__(self, title: str) -> None:
        super().__init__()
        self.setProperty("role", "card")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 12, 16, 14)
        layout.setSpacing(4)
        layout.addWidget(make_label(title, role="statLabel"))
        self.value = make_label(role="statValue")
        layout.addWidget(self.value)


class GameDetails(QWidget):
    remove_requested = Signal(int)

    def __init__(self) -> None:
        super().__init__()
        self._game_id: int | None = None
        layout = QVBoxLayout(self)
        layout.setContentsMargins(40, 36, 40, 32)
        layout.setSpacing(10)

        self._title = make_label(role="title", wrap=True)
        self._status = make_label()
        self._location = make_label(role="hint", wrap=True)
        self._location.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        layout.addWidget(self._title)
        layout.addWidget(self._status)
        layout.addWidget(self._location)
        layout.addSpacing(18)

        cards = QHBoxLayout()
        cards.setSpacing(12)
        self._total = _StatCard("Temps de jeu total")
        self._last = _StatCard("Dernière utilisation")
        self._recent = _StatCard("7 derniers jours")
        for card in (self._total, self._last, self._recent):
            cards.addWidget(card)
        layout.addLayout(cards)
        layout.addStretch()

        footer = QHBoxLayout()
        footer.addStretch()
        self._remove = make_button("Retirer de la bibliothèque…", variant="danger")
        self._remove.clicked.connect(self._on_remove_clicked)
        footer.addWidget(self._remove)
        layout.addLayout(footer)

    def show_game(self, row: GameRow, now: float) -> None:
        self._game_id = row.game.id
        self._title.setText(row.game.display_name)
        stats = row.stats
        if row.running_since is not None:
            stats = add_running_session(stats, row.running_since, now)
            self._status.setText(f"●  En cours depuis {format_clock(row.running_since)}")
            set_style_property(self._status, "role", "running")
        else:
            self._status.setText("Fermé")
            set_style_property(self._status, "role", "secondary")

        location = row.game.exe_path or (
            "Chemin inconnu : il sera récupéré automatiquement au premier lancement du jeu."
        )
        self._location.setText(f"{row.game.process_name}  ·  {location}")
        self._total.value.setText(format_duration(stats.total_seconds))
        self._last.value.setText(
            "En cours" if row.running else format_last_played(stats.last_played_at, now)
        )
        self._recent.value.setText(format_duration(stats.last_7_days_seconds))

    def _on_remove_clicked(self) -> None:
        if self._game_id is not None:
            self.remove_requested.emit(self._game_id)


class EmptyLibrary(QWidget):
    """Affiché tant que la bibliothèque est vide."""

    add_requested = Signal()

    def __init__(self) -> None:
        super().__init__()
        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.setSpacing(12)

        logo = QLabel()
        pixmap = QPixmap(str(asset_path("logo.png")))
        if not pixmap.isNull():
            logo.setPixmap(
                pixmap.scaled(
                    96,
                    96,
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                )
            )
        logo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title = make_label("Votre bibliothèque est vide", role="title")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        text = make_label(
            "Ajoutez un jeu : Nova mesurera ensuite son temps de jeu automatiquement,\n"
            "même si vous ne le lancez pas depuis Nova.",
            role="secondary",
        )
        text.setAlignment(Qt.AlignmentFlag.AlignCenter)
        button = make_button("Ajouter un jeu", variant="primary")
        button.clicked.connect(self.add_requested)

        layout.addWidget(logo)
        layout.addWidget(title)
        layout.addWidget(text)
        layout.addSpacing(8)
        layout.addWidget(button, alignment=Qt.AlignmentFlag.AlignCenter)
