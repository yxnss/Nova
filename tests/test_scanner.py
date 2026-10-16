"""Tests du scanner réel (psutil) sur de vrais processus Windows."""

import os
import subprocess
import sys
import time

import psutil
import pytest

from nova.core.scanner import PsutilScanner

pytestmark = pytest.mark.skipif(sys.platform != "win32", reason="Nova cible Windows")


@pytest.fixture
def ping_process():
    """Lance un petit processus Windows (ping.exe) qui dure 30 s, puis le termine."""
    process = subprocess.Popen(
        ["ping", "-n", "30", "127.0.0.1"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    yield process
    process.kill()
    process.wait(timeout=10)


def test_find_ignores_case() -> None:
    name = psutil.Process().name()
    found = PsutilScanner().find({name.upper()})
    assert os.getpid() in found[name.lower()]


def test_find_returns_only_running_names() -> None:
    found = PsutilScanner().find({"ce-jeu-n-existe-pas.exe"})
    assert found == {}


def test_find_without_names_returns_nothing() -> None:
    assert PsutilScanner().find(set()) == {}


def test_still_running_detects_end_of_process(ping_process) -> None:
    scanner = PsutilScanner()
    pid = ping_process.pid
    assert pid in scanner.find({"PING.EXE"})["ping.exe"]
    assert scanner.still_running({pid}) == {pid}

    ping_process.kill()
    ping_process.wait(timeout=10)
    # Windows met parfois quelques instants à retirer un processus terminé ; le moteur
    # réel revérifie de toute façon toutes les 5 s.
    deadline = time.monotonic() + 3
    while scanner.still_running({pid}) and time.monotonic() < deadline:
        time.sleep(0.05)
    assert scanner.still_running({pid}) == set()


def test_still_running_ignores_pids_not_seen_by_a_scan() -> None:
    assert PsutilScanner().still_running({os.getpid()}) == set()


def test_exe_path_of_current_process() -> None:
    scanner = PsutilScanner()
    path = scanner.exe_path(os.getpid())
    assert path is not None
    assert path.lower().endswith(psutil.Process().name().lower())


def test_exe_path_of_missing_process_is_none(ping_process) -> None:
    pid = ping_process.pid
    ping_process.kill()
    ping_process.wait(timeout=10)
    assert PsutilScanner().exe_path(pid) is None
