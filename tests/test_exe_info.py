"""Tests du choix du nom affiché à partir des métadonnées d'un exe."""

import sys

import pytest

from nova.system.exe_info import pick_display_name, read_version_strings, suggest_display_name


@pytest.mark.parametrize(
    ("strings", "stem", "expected"),
    [
        # Cas réels relevés sur Fortnite, Valorant et le Bloc-notes.
        (
            {"ProductName": "Unreal Engine", "FileDescription": "Fortnite"},
            "FortniteClient-Win64-Shipping",
            "Fortnite",
        ),
        (
            {"ProductName": "VALORANT", "FileDescription": "VALORANT"},
            "VALORANT-Win64-Shipping",
            "VALORANT",
        ),
        (
            {
                "ProductName": "Système d'exploitation Microsoft® Windows®",
                "FileDescription": "Bloc-notes",
            },
            "notepad",
            "Bloc-notes",
        ),
        # Repli sur ProductName, puis sur le nom du fichier nettoyé.
        ({"ProductName": "ELDEN RING™"}, "eldenring", "ELDEN RING"),
        ({"ProductName": "Unreal Engine"}, "MyGame-Win64-Shipping", "MyGame"),
        ({"FileDescription": "BootstrapPackagedGame"}, "VALORANT", "VALORANT"),
        ({}, "game", "game"),
    ],
)
def test_pick_display_name(strings: dict[str, str], stem: str, expected: str) -> None:
    assert pick_display_name(strings, stem) == expected


@pytest.mark.skipif(sys.platform != "win32", reason="métadonnées Windows")
def test_reads_metadata_of_a_real_exe() -> None:
    assert suggest_display_name(sys.executable) == "Python"


def test_missing_file_has_no_metadata(tmp_path) -> None:
    assert read_version_strings(tmp_path / "absent.exe") == {}
