"""Tests de la liste des jeux : recherche et tris."""

import pytest

from nova.core.models import Game, GameStats
from nova.ui.library_model import GameFilterProxy, GameListModel, SortMode

GAMES = [
    Game(1, "zelda.exe", "Zelda", None, 0),
    Game(2, "elden.exe", "Élden Ring", None, 0),
    Game(3, "apex.exe", "Apex", None, 0),
    Game(4, "never.exe", "Jamais joué", None, 0),
]
STATS = {
    1: GameStats(1, total_seconds=500, last_played_at=3000, last_7_days_seconds=0),
    2: GameStats(2, total_seconds=9000, last_played_at=1000, last_7_days_seconds=0),
    3: GameStats(3, total_seconds=100, last_played_at=2000, last_7_days_seconds=0),
}


@pytest.fixture
def proxy(qapp) -> GameFilterProxy:
    model = GameListModel(lambda game_id: None)
    model.set_library(GAMES, STATS, running={})
    return GameFilterProxy(model)


def visible_names(proxy: GameFilterProxy) -> list[str]:
    return [proxy.index(row, 0).data() for row in range(proxy.rowCount())]


def test_sort_by_recent_use(proxy) -> None:
    proxy.set_sort_mode(SortMode.RECENT)
    assert visible_names(proxy) == ["Zelda", "Apex", "Élden Ring", "Jamais joué"]


def test_sort_by_playtime(proxy) -> None:
    proxy.set_sort_mode(SortMode.PLAYTIME)
    assert visible_names(proxy) == ["Élden Ring", "Zelda", "Apex", "Jamais joué"]


def test_sort_by_name_ignores_accents(proxy) -> None:
    proxy.set_sort_mode(SortMode.NAME)
    assert visible_names(proxy) == ["Apex", "Élden Ring", "Jamais joué", "Zelda"]


def test_running_game_comes_first_when_sorting_by_recent_use(proxy) -> None:
    proxy.sourceModel().set_running(4, since=5000)
    proxy.set_sort_mode(SortMode.RECENT)
    assert visible_names(proxy)[0] == "Jamais joué"


def test_search_matches_name_without_accents_or_process_name(proxy) -> None:
    proxy.set_search("elden")
    assert visible_names(proxy) == ["Élden Ring"]
    proxy.set_search("APEX.EXE")
    assert visible_names(proxy) == ["Apex"]
    proxy.set_search("")
    assert len(visible_names(proxy)) == 4
