"""Fenêtre « Paramètres » : démarrage avec Windows et pause du suivi."""

import logging

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QCheckBox, QDialog, QHBoxLayout, QMessageBox, QVBoxLayout, QWidget

from nova.system.autostart import AutoStart
from nova.ui.widgets import make_button, make_label, set_style_property

log = logging.getLogger(__name__)


class SettingsDialog(QDialog):
    pause_requested = Signal(bool)  # True : mettre en pause ; False : reprendre

    def __init__(
        self, autostart: AutoStart | None, paused: bool, parent: QWidget | None = None
    ) -> None:
        super().__init__(parent)
        self._autostart = autostart
        self._paused = paused
        self.setWindowTitle("Paramètres")
        self.setMinimumWidth(480)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(8)

        layout.addWidget(make_label("Démarrage", role="sectionTitle"))
        self._autostart_box = QCheckBox("Lancer Nova au démarrage de Windows")
        self._autostart_box.setEnabled(autostart is not None)
        self._autostart_box.setChecked(autostart is not None and autostart.is_enabled())
        self._autostart_box.toggled.connect(self._on_autostart_toggled)
        layout.addWidget(self._autostart_box)
        layout.addWidget(
            make_label(
                "Nova démarre alors directement dans la zone de notifications, près de "
                "l'horloge, sans ouvrir de fenêtre.",
                role="hint",
                wrap=True,
            )
        )
        layout.addSpacing(14)

        layout.addWidget(make_label("Suivi du temps de jeu", role="sectionTitle"))
        row = QHBoxLayout()
        self._status = make_label()
        self._pause_button = make_button("")
        self._pause_button.clicked.connect(lambda: self.pause_requested.emit(not self._paused))
        row.addWidget(self._status, 1)
        row.addWidget(self._pause_button)
        layout.addLayout(row)
        layout.addWidget(
            make_label(
                "La pause arrête complètement la surveillance. Elle prend fin au prochain "
                "démarrage de Nova.",
                role="hint",
                wrap=True,
            )
        )
        layout.addSpacing(10)

        footer = QHBoxLayout()
        footer.addStretch()
        close = make_button("Fermer")
        close.clicked.connect(self.close)
        footer.addWidget(close)
        layout.addLayout(footer)
        self.set_paused(paused)

    def set_paused(self, paused: bool) -> None:
        self._paused = paused
        if paused:
            self._status.setText("En pause : aucun temps de jeu n'est compté.")
            set_style_property(self._status, "role", "paused")
            self._pause_button.setText("Reprendre le suivi")
        else:
            self._status.setText("●  Actif : vos jeux sont détectés automatiquement.")
            set_style_property(self._status, "role", "running")
            self._pause_button.setText("Mettre en pause")

    def _on_autostart_toggled(self, enabled: bool) -> None:
        try:
            if enabled:
                self._autostart.enable()
            else:
                self._autostart.disable()
        except OSError as error:
            log.warning("Démarrage automatique impossible à modifier : %s", error)
            QMessageBox.warning(
                self, "Démarrage automatique", "Windows n'a pas permis de modifier ce réglage."
            )
            self._autostart_box.blockSignals(True)
            self._autostart_box.setChecked(not enabled)  # revient à l'état réel
            self._autostart_box.blockSignals(False)
