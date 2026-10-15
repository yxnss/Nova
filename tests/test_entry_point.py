"""Tests du point d'entrée ``python -m nova``."""

from nova import __version__
from nova.__main__ import main


def test_version_has_three_parts() -> None:
    assert len(__version__.split(".")) == 3


def test_main_prints_version(capsys) -> None:
    assert main() == 0
    assert __version__ in capsys.readouterr().out
