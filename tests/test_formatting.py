"""Tests de la mise en forme des durées et des dates."""

from datetime import datetime

import pytest

from nova.ui.formatting import format_duration, format_last_played, sort_key

NOW = datetime(2026, 10, 16, 15, 30).timestamp()  # heure locale


@pytest.mark.parametrize(
    ("seconds", "expected"),
    [
        (0, "0 min"),
        (30, "moins d'une minute"),
        (59, "moins d'une minute"),
        (60, "1 min"),
        (45 * 60 + 59, "45 min"),
        (3 * 3600 + 5 * 60, "3 h 05 min"),
        (1234 * 3600, "1 234 h 00 min"),
    ],
)
def test_format_duration(seconds: float, expected: str) -> None:
    assert format_duration(seconds) == expected


@pytest.mark.parametrize(
    ("moment", "expected"),
    [
        (None, "Jamais"),
        (datetime(2026, 10, 16, 14, 5), "Aujourd'hui à 14:05"),
        (datetime(2026, 10, 15, 22, 10), "Hier à 22:10"),
        (datetime(2026, 10, 13, 9, 0), "Il y a 3 jours"),
        (datetime(2026, 8, 2, 20, 0), "2 août 2026"),
    ],
)
def test_format_last_played(moment: datetime | None, expected: str) -> None:
    timestamp = moment.timestamp() if moment else None
    assert format_last_played(timestamp, NOW) == expected


def test_sort_key_ignores_accents_and_case() -> None:
    assert sort_key("Élan") == sort_key("elan")
    assert sorted(["Zelda", "élan", "Alba"], key=sort_key) == ["Alba", "élan", "Zelda"]
