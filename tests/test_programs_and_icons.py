"""Tests de la liste des programmes en cours et du cache d'icônes (vrais processus Windows)."""

import os
import sys
from pathlib import Path

import psutil
import pytest
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QImage

from nova.system.icons import IconCache, trim_to_content
from nova.system.processes import list_running_programs

windows_only = pytest.mark.skipif(sys.platform != "win32", reason="Nova cible Windows")


@windows_only
def test_running_programs_include_this_test_process() -> None:
    exe = psutil.Process().exe()
    programs = list_running_programs()
    assert any(program.exe_path == exe for program in programs)


@windows_only
def test_running_programs_are_real_exes_sorted_by_memory_without_windows() -> None:
    programs = list_running_programs()
    windows_dir = os.environ.get("SystemRoot", r"C:\Windows").casefold()
    for program in programs:
        assert not program.exe_path.casefold().startswith(windows_dir + "\\")
        assert program.exe_path.casefold().endswith(".exe")
        assert os.path.isabs(program.exe_path)
    memories = [program.memory for program in programs]
    assert memories == sorted(memories, reverse=True)
    assert len({p.exe_path.casefold() for p in programs}) == len(programs)  # un par exe


@windows_only
def test_excluded_pids_are_not_listed() -> None:
    exe = psutil.Process().exe()
    same_exe = {p.pid for p in psutil.process_iter(["exe"]) if p.info["exe"] == exe}
    programs = list_running_programs(exclude_pids=same_exe)
    assert all(program.exe_path != exe for program in programs)


def make_canvas(size: int) -> QImage:
    image = QImage(size, size, QImage.Format.Format_ARGB32)
    image.fill(Qt.GlobalColor.transparent)
    return image


def test_small_icon_in_the_corner_of_a_big_image_is_cropped(qapp) -> None:
    # Ce que Windows renvoie pour un exe qui n'a qu'une icône de 32 px.
    image = make_canvas(256)
    for x in range(32):
        for y in range(32):
            image.setPixelColor(x, y, QColor("red"))

    trimmed = trim_to_content(image)
    assert (trimmed.width(), trimmed.height()) == (32, 32)


def test_cropped_icon_stays_square_and_centered(qapp) -> None:
    image = make_canvas(256)
    for x in range(100, 120):  # contenu de 20 × 40 px
        for y in range(50, 90):
            image.setPixelColor(x, y, QColor("blue"))

    trimmed = trim_to_content(image)
    assert (trimmed.width(), trimmed.height()) == (40, 40)
    assert trimmed.pixelColor(0, 20).alpha() == 0  # marge transparente à gauche
    assert trimmed.pixelColor(20, 20) == QColor("blue")


def test_fully_transparent_icon_is_left_unchanged(qapp) -> None:
    assert trim_to_content(make_canvas(64)).width() == 64


@windows_only
def test_icon_cache_extracts_stores_and_removes(qapp, tmp_path: Path) -> None:
    cache = IconCache(tmp_path / "icons")
    assert cache.icon(1) is None

    assert cache.extract(1, sys.executable)
    assert cache.path_for(1).exists()
    assert cache.icon(1) is not None

    cache.remove(1)
    assert not cache.path_for(1).exists()
    assert cache.icon(1) is None
