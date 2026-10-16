"""Tests de l'étape 5 : instance unique, démarrage automatique, réglages, systray."""

import subprocess
import sys
import time
import uuid
import winreg
from pathlib import Path

import pytest
from PySide6.QtCore import QCoreApplication
from PySide6.QtGui import QColor, QIcon, QPixmap
from PySide6.QtWidgets import QMessageBox

from nova.app import LazyWindow
from nova.system.autostart import AutoStart, launch_command
from nova.system.settings import AppSettings
from nova.system.single_instance import SingleInstance, channel_name
from nova.ui.settings_dialog import SettingsDialog
from nova.ui.theme.palette import COLORS
from nova.ui.tray import RecentGame, TrayIcon, paused_version

pytestmark = pytest.mark.skipif(sys.platform != "win32", reason="Nova cible Windows")


def wait_until(condition, timeout: float = 3.0) -> None:
    deadline = time.monotonic() + timeout
    while not condition():
        assert time.monotonic() < deadline, "délai dépassé"
        QCoreApplication.processEvents()
        time.sleep(0.01)


# --- Instance unique ---


# Seconde instance lancée dans un vrai processus séparé, comme quand on relance Nova.
# (Dans un seul processus, elle bloquerait la première pendant qu'elle attend.)
SECOND_INSTANCE = (
    "import sys\n"
    "from pathlib import Path\n"
    "from PySide6.QtCore import QCoreApplication\n"
    "from nova.system.single_instance import SingleInstance\n"
    "app = QCoreApplication([])\n"
    "instance = SingleInstance(Path(sys.argv[1]))\n"
    "print(instance.acquire(), instance.wake_up_running_instance())\n"
)


def test_second_instance_wakes_up_the_first(qapp, tmp_path: Path) -> None:
    first = SingleInstance(tmp_path)
    woken = []
    first.activation_requested.connect(lambda: woken.append(True))
    assert first.acquire()

    second = subprocess.Popen(
        [sys.executable, "-c", SECOND_INSTANCE, str(tmp_path)], stdout=subprocess.PIPE, text=True
    )
    wait_until(lambda: woken, timeout=10)
    # La seconde n'obtient pas le verrou (Nova tourne déjà), mais réveille la première.
    assert second.communicate(timeout=10)[0].split() == ["False", "True"]

    first.release()
    third = SingleInstance(tmp_path)
    assert third.acquire()  # la place est libre une fois la première arrêtée
    third.release()


def test_each_data_folder_has_its_own_channel(tmp_path: Path) -> None:
    assert channel_name(tmp_path / "a") != channel_name(tmp_path / "b")
    assert channel_name(tmp_path / "A") == channel_name(tmp_path / "a")  # Windows ignore la casse


# --- Démarrage automatique (dans une clé de test, supprimée ensuite) ---


@pytest.fixture
def test_key():
    key_path = rf"Software\NovaTests\{uuid.uuid4().hex}"
    yield key_path
    for path in (key_path, r"Software\NovaTests"):
        try:
            winreg.DeleteKey(winreg.HKEY_CURRENT_USER, path)
        except OSError:
            pass  # déjà supprimée, ou d'autres clés de test y restent


def test_autostart_can_be_enabled_and_disabled(test_key: str) -> None:
    autostart = AutoStart(key_path=test_key, command='"C:\\Nova\\Nova.exe" --minimized')
    assert not autostart.is_enabled()

    autostart.enable()
    assert autostart.registered_command() == '"C:\\Nova\\Nova.exe" --minimized'

    autostart.disable()
    assert not autostart.is_enabled()
    autostart.disable()  # déjà désactivé : aucune erreur


def test_autostart_repairs_an_outdated_path(test_key: str) -> None:
    AutoStart(key_path=test_key, command='"D:\\Ancien\\Nova.exe" --minimized').enable()

    current = AutoStart(key_path=test_key, command='"C:\\Nova\\Nova.exe" --minimized')
    current.repair()
    assert current.registered_command() == '"C:\\Nova\\Nova.exe" --minimized'


def test_repair_does_not_enable_a_disabled_autostart(test_key: str) -> None:
    autostart = AutoStart(key_path=test_key, command="nova")
    autostart.repair()
    assert not autostart.is_enabled()


def test_development_command_starts_nova_minimized_without_console() -> None:
    command = launch_command()
    assert "pythonw.exe" in command
    assert command.endswith("-m nova --minimized")


# --- Réglages ---


def test_close_notice_is_remembered(qapp, tmp_path: Path) -> None:
    path = tmp_path / "settings.ini"
    assert not AppSettings(path).close_notice_shown

    AppSettings(path).close_notice_shown = True
    assert AppSettings(path).close_notice_shown  # relu depuis le fichier


# --- Systray ---


def recent(game_id: int, name: str, running: bool = False) -> RecentGame:
    return RecentGame(game_id, name, QIcon(), running)


@pytest.fixture
def tray(qapp):
    games = [recent(1, "Fortnite", running=True), recent(2, "Hades")]
    return TrayIcon(lambda: games)


def menu_texts(tray: TrayIcon) -> list[str]:
    tray.rebuild_menu()
    return [action.text() or "—" for action in tray.menu.actions()]


def test_tray_menu_looks_like_steam(tray: TrayIcon) -> None:
    assert menu_texts(tray) == [
        "Fortnite   ●  en cours",
        "Hades",
        "—",
        "Ouvrir Nova",
        "Paramètres",
        "—",
        "Mettre en pause le suivi",
        "—",
        "Quitter Nova",
    ]


def test_tray_menu_actions_emit_their_signals(tray: TrayIcon) -> None:
    received = []
    tray.game_requested.connect(lambda game_id: received.append(("jeu", game_id)))
    tray.open_requested.connect(lambda: received.append("ouvrir"))
    tray.pause_requested.connect(lambda paused: received.append(("pause", paused)))
    tray.quit_requested.connect(lambda: received.append("quitter"))
    tray.rebuild_menu()
    actions = {action.text(): action for action in tray.menu.actions()}

    actions["Hades"].trigger()
    actions["Ouvrir Nova"].trigger()
    actions["Mettre en pause le suivi"].trigger()
    actions["Quitter Nova"].trigger()
    assert received == [("jeu", 2), "ouvrir", ("pause", True), "quitter"]


def test_paused_tray_changes_menu_and_tooltip(tray: TrayIcon) -> None:
    tray.set_running_games(["Fortnite"])
    assert tray.tooltip == "Nova — Fortnite en cours"

    tray.set_paused(True)
    assert tray.tooltip == "Nova — suivi en pause"
    assert "Reprendre le suivi" in menu_texts(tray)


def test_paused_icon_is_grey_with_an_amber_badge(qapp) -> None:
    logo = QPixmap(32, 32)
    logo.fill(QColor(COLORS["accent"]))

    image = paused_version(logo).toImage()
    corner = image.pixelColor(2, 2)
    assert corner.red() == corner.green() == corner.blue()  # grisé
    badge = image.pixelColor(24, 18)  # dans le badge, au-dessus des deux barres
    assert badge == QColor(COLORS["paused"])


# --- Fenêtre Paramètres ---


class FakeAutoStart:
    def __init__(self, refuse: bool = False) -> None:
        self.enabled = False
        self.refuse = refuse

    def is_enabled(self) -> bool:
        return self.enabled

    def enable(self) -> None:
        if self.refuse:
            raise OSError("refus simulé")
        self.enabled = True

    def disable(self) -> None:
        self.enabled = False


def test_settings_checkbox_enables_and_disables_autostart(qapp) -> None:
    autostart = FakeAutoStart()
    dialog = SettingsDialog(autostart, paused=False)

    dialog._autostart_box.setChecked(True)
    assert autostart.enabled
    dialog._autostart_box.setChecked(False)
    assert not autostart.enabled


def test_settings_checkbox_returns_to_real_state_if_windows_refuses(qapp, monkeypatch) -> None:
    monkeypatch.setattr(QMessageBox, "warning", lambda *args, **kwargs: None)
    dialog = SettingsDialog(FakeAutoStart(refuse=True), paused=False)

    dialog._autostart_box.setChecked(True)
    assert not dialog._autostart_box.isChecked()


def test_settings_pause_button(qapp) -> None:
    dialog = SettingsDialog(FakeAutoStart(), paused=False)
    requests = []
    dialog.pause_requested.connect(requests.append)

    dialog._pause_button.click()
    assert requests == [True]
    dialog.set_paused(True)
    assert dialog._pause_button.text() == "Reprendre le suivi"
    assert "En pause" in dialog._status.text()


# --- Fenêtre créée à la demande ---


def test_window_is_created_only_when_first_needed() -> None:
    created = []

    class FakeWindow:
        def __init__(self) -> None:
            self.quitting = False
            created.append(self)

        def prepare_quit(self) -> None:
            self.quitting = True

    window = LazyWindow(FakeWindow)
    window.prepare_quit()  # jamais ouverte : rien à préparer, et rien n'est créé
    assert created == []

    assert window.get() is window.get()  # créée une seule fois
    assert len(created) == 1
    window.prepare_quit()
    assert created[0].quitting
