"""Panneau de droite : fiche du jeu sélectionné, ou invitation si la bibliothèque est vide.

La fiche affiche la bannière, le bouton « Lancer », le statut et le temps de jeu.
Pour un jeu en cours, un compteur avance chaque seconde, mais seulement quand la
fenêtre est visible : réduite, Nova ne fait aucun calcul d'affichage.
"""

import time
from pathlib import Path

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QIcon, QPixmap
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QVBoxLayout, QWidget

from nova.data.stats import add_running_session
from nova.services.launcher import launch_problem
from nova.system.paths import asset_path
from nova.ui.banner import Banner
from nova.ui.formatting import format_duration, format_elapsed, format_last_played
from nova.ui.library_model import GameRow
from nova.ui.widgets import ElidedLabel, make_button, make_label, set_style_property


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
    launch_requested = Signal(int)
    remove_requested = Signal(int)
    change_banner_requested = Signal(int)
    reset_banner_requested = Signal(int)

    def __init__(self) -> None:
        super().__init__()
        self._row: GameRow | None = None
        self._live_allowed = False  # la fenêtre est visible et non réduite

        # Compteur en direct : une mise à jour par seconde, seulement si utile.
        self._timer = QTimer(self)
        self._timer.setInterval(1000)
        self._timer.timeout.connect(self._refresh_numbers)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        self._banner = Banner()
        self._banner.change_requested.connect(
            lambda: self._emit_for_game(self.change_banner_requested)
        )
        self._banner.reset_requested.connect(
            lambda: self._emit_for_game(self.reset_banner_requested)
        )
        layout.addWidget(self._banner)

        body = QVBoxLayout()
        body.setContentsMargins(32, 16, 32, 24)
        body.setSpacing(12)
        layout.addLayout(body, 1)

        actions = QHBoxLayout()
        actions.setSpacing(14)
        self._launch = make_button("▶  Lancer", variant="primary")
        self._launch.setObjectName("launchButton")
        self._launch.clicked.connect(lambda: self._emit_for_game(self.launch_requested))
        self._status = make_label(role="pill")
        change_banner = make_button("Changer la bannière…")
        change_banner.clicked.connect(lambda: self._emit_for_game(self.change_banner_requested))
        actions.addWidget(self._launch)
        actions.addWidget(self._status)
        actions.addStretch()
        actions.addWidget(change_banner)
        body.addLayout(actions)

        # Petit message sous le bouton quand le jeu ne peut pas être lancé depuis Nova.
        self._launch_hint = make_label(role="hint", wrap=True)
        self._launch_hint.hide()
        body.addWidget(self._launch_hint)
        body.addSpacing(6)

        cards = QHBoxLayout()
        cards.setSpacing(12)
        self._total = _StatCard("Temps de jeu total")
        self._last = _StatCard("Dernière utilisation")
        self._recent = _StatCard("7 derniers jours")
        for card in (self._total, self._last, self._recent):
            cards.addWidget(card)
        body.addLayout(cards)

        self._location = ElidedLabel(role="hint")
        body.addWidget(self._location)
        body.addStretch()

        footer = QHBoxLayout()
        footer.addStretch()
        remove = make_button("Retirer de la bibliothèque…", variant="danger")
        remove.clicked.connect(lambda: self._emit_for_game(self.remove_requested))
        footer.addWidget(remove)
        body.addLayout(footer)

    # --- Affichage d'un jeu ---

    def show_game(
        self, row: GameRow, launching: bool, banner: Path | None, icon: QIcon | None
    ) -> None:
        self._row = row
        self._banner.set_content(row.game.display_name, banner, icon)
        location = row.game.exe_path or "chemin inconnu pour l'instant"
        self._location.set_full_text(f"{row.game.process_name}  ·  {location}")
        self._update_launch_button(row, launching)
        self._refresh_numbers()
        self._update_timer()

    def _update_launch_button(self, row: GameRow, launching: bool) -> None:
        problem = launch_problem(row.game)
        if row.running:
            self._launch.setText("En cours")
            self._launch.setEnabled(False)
            hint = None
        elif launching:
            self._launch.setText("Lancement…")
            self._launch.setEnabled(False)
            hint = "Nova attend que le jeu démarre."
        else:
            self._launch.setText("▶  Lancer")
            self._launch.setEnabled(problem is None)
            hint = problem
        self._launch_hint.setText(hint or "")
        self._launch_hint.setVisible(bool(hint))

    def _refresh_numbers(self) -> None:
        """Statut et statistiques ; appelée chaque seconde pendant qu'un jeu tourne."""
        row = self._row
        if row is None:
            return
        now = time.time()
        stats = row.stats
        if row.running_since is not None:
            stats = add_running_session(stats, row.running_since, now)
            self._status.setText(f"●  En cours · {format_elapsed(now - row.running_since)}")
            set_style_property(self._status, "role", "pillRunning")
            last = "En cours"
        else:
            self._status.setText("Fermé")
            set_style_property(self._status, "role", "pill")
            last = format_last_played(stats.last_played_at, now)
        self._total.value.setText(format_duration(stats.total_seconds))
        self._last.value.setText(last)
        self._recent.value.setText(format_duration(stats.last_7_days_seconds))

    # --- Compteur en direct ---

    def set_live_allowed(self, allowed: bool) -> None:
        """Appelée par la fenêtre : True si elle est visible et non réduite."""
        self._live_allowed = allowed
        self._update_timer()

    @property
    def is_counting(self) -> bool:
        return self._timer.isActive()

    def _update_timer(self) -> None:
        should_count = self._live_allowed and self._row is not None and self._row.running
        if should_count and not self._timer.isActive():
            self._refresh_numbers()  # rattrape le temps écoulé pendant que la fenêtre était cachée
            self._timer.start()
        elif not should_count:
            self._timer.stop()

    def _emit_for_game(self, signal: Signal) -> None:
        if self._row is not None:
            signal.emit(self._row.game.id)


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
