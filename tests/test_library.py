"""Tests du service de bibliothèque : ajout, retrait, icônes."""

import sqlite3
import sys
from pathlib import Path

import pytest

from fakes import FakeClock, FakeTracking
from nova.services.library import LibraryError, LibraryService, normalize_new_process_name
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
def library(db: sqlite3.Connection, tracking: FakeTracking, icons: IconCache) -> LibraryService:
    return LibraryService(db, tracking, icons, FakeClock())


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
