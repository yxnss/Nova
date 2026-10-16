"""Tests du service de bibliothèque : ajout, retrait, icônes."""

import sqlite3
import sys
from pathlib import Path

import pytest
from PySide6.QtGui import QColor, QImage

from fakes import FakeClock, FakeTracking
from nova.core.events import GameStarted, GameStopped, StopReason
from nova.data.sessions_repo import SessionRepository
from nova.services.library import LibraryError, LibraryService, normalize_new_process_name
from nova.system.banners import BannerStore
from nova.system.icons import IconCache


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("EldenRing.exe", "eldenring.exe"),
        ("  Jeu  ", "jeu.exe"),  # « .exe » ajouté automatiquement
        ('"C:\\Jeux\\Mon Jeu\\Game.EXE"', "game.exe"),  # chemin complet collé par erreur
        ("D:/Jeux/game.exe", "game.exe"),
    ],
)
def test_normalize_new_process_name(text: str, expected: str) -> None:
    assert normalize_new_process_name(text) == expected


@pytest.mark.parametrize("text", ["", "   ", "jeu?.exe", "a<b.exe"])
def test_invalid_process_names_are_refused(text: str) -> None:
    with pytest.raises(LibraryError):
        normalize_new_process_name(text)


@pytest.fixture
def tracking(qapp) -> FakeTracking:
    return FakeTracking()


@pytest.fixture
def icons(tmp_path: Path) -> IconCache:
    return IconCache(tmp_path / "icons")


@pytest.fixture
def library(
    db: sqlite3.Connection, tracking: FakeTracking, icons: IconCache, tmp_path: Path
) -> LibraryService:
    return LibraryService(db, tracking, icons, BannerStore(tmp_path / "banners"), FakeClock())


def test_adding_a_game_reloads_tracking_and_notifies(library, tracking) -> None:
    notified = []
    library.changed.connect(lambda: notified.append(True))

    game = library.add_game("Game", "  Mon   jeu ")

    assert (game.process_name, game.display_name, game.exe_path) == ("game.exe", "Mon jeu", None)
    assert [g.id for g in library.games()] == [game.id]
    assert tracking.reloads == 1
    assert notified == [True]


def test_display_name_defaults_to_the_process_name(library) -> None:
    assert library.add_game("eldenring.exe", "   ").display_name == "eldenring"


def test_duplicate_game_gives_a_readable_error(library) -> None:
    library.add_game("game.exe", "Game")
    with pytest.raises(LibraryError, match="déjà dans votre bibliothèque"):
        library.add_game("GAME.EXE", "Autre")


@pytest.mark.skipif(sys.platform != "win32", reason="icônes Windows")
def test_icon_is_extracted_when_the_path_is_known(library, icons) -> None:
    game = library.add_game("python.exe", "Python", sys.executable)
    assert icons.path_for(game.id).exists()
    assert library.icon(game.id) is not None


def test_removal_goes_through_tracking_then_cleans_up(library, tracking, icons) -> None:
    game = library.add_game("game.exe", "Game")
    icons.path_for(game.id).write_bytes(b"fausse icone")
    notified = []
    library.changed.connect(lambda: notified.append(True))

    library.remove_game(game.id)
    assert tracking.removal_requests == [game.id]  # rien n'est supprimé directement

    tracking.game_removed.emit(game.id)  # le thread de suivi a supprimé le jeu
    assert not icons.path_for(game.id).exists()
    assert notified == [True]


@pytest.mark.skipif(sys.platform != "win32", reason="icônes Windows")
def test_icon_appears_when_the_path_of_a_game_added_by_name_is_found(library, tracking) -> None:
    game = library.add_game("python.exe", "Python")
    assert library.icon(game.id) is None

    tracking.game_path_found.emit(game.id, sys.executable)
    assert library.icon(game.id) is not None


def make_banner(path: Path) -> Path:
    image = QImage(600, 200, QImage.Format.Format_RGB32)
    image.fill(QColor("#7D27FA"))
    image.save(str(path))
    return path


def test_banner_is_set_replaced_and_reset(library, tmp_path) -> None:
    game = library.add_game("game.exe", "Game")
    library.set_banner(game.id, str(make_banner(tmp_path / "a.png")))
    first = library.banner_path(library.games()[0])
    assert first is not None and first.exists()

    library.set_banner(game.id, str(make_banner(tmp_path / "b.png")))
    second = library.banner_path(library.games()[0])
    assert second != first and second.exists()
    assert not first.exists()  # l'ancienne copie est supprimée

    library.reset_banner(game.id)
    assert library.banner_path(library.games()[0]) is None
    assert not second.exists()


def test_unreadable_banner_gives_a_readable_error(library, tmp_path) -> None:
    game = library.add_game("game.exe", "Game")
    fake = tmp_path / "faux.png"
    fake.write_text("pas une image", encoding="utf-8")
    with pytest.raises(LibraryError, match="n'a pas pu être lue"):
        library.set_banner(game.id, str(fake))


def test_removing_a_game_deletes_its_banner(library, tracking, tmp_path) -> None:
    game = library.add_game("game.exe", "Game")
    library.set_banner(game.id, str(make_banner(tmp_path / "a.png")))
    banner = library.banner_path(library.games()[0])

    tracking.game_removed.emit(game.id)
    assert not banner.exists()


def test_launch_failure_is_remembered(library, tracking) -> None:
    game = library.add_game("game.exe", "Game", sys.executable)
    library._launcher.launch_failed.emit(game.id, "Ce jeu ne se lance pas directement.")

    assert library.games()[0].launch_error == "Ce jeu ne se lance pas directement."


def test_running_and_recent_games_for_the_tray(library, tracking, db) -> None:
    library.add_game("never.exe", "Jamais joué")
    old = library.add_game("old.exe", "Ancien")
    running = library.add_game("running.exe", "En cours")
    sessions = SessionRepository(db)
    sessions.close_session(sessions.open_session(old.id, 100, 100), 200)

    tracking.game_started.emit(GameStarted(running.id, 1000, None))
    assert library.running() == {running.id: 1000}
    assert library.running_names() == ["En cours"]
    # Jeu en cours d'abord, puis les derniers joués ; un jeu jamais joué n'y est pas.
    assert [(game.display_name, now) for game, now in library.recent_games()] == [
        ("En cours", True),
        ("Ancien", False),
    ]

    tracking.game_stopped.emit(GameStopped(running.id, 1000, 1004, StopReason.CLOSED, False))
    assert library.running() == {}
