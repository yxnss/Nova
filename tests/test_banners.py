"""Tests du stockage des bannières personnalisées."""

from pathlib import Path

import pytest
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QImage

from nova.system.banners import MAX_HEIGHT, MAX_WIDTH, BannerError, BannerStore


def make_image(path: Path, width: int, height: int, transparent: bool = False) -> Path:
    image = QImage(width, height, QImage.Format.Format_ARGB32)
    image.fill(Qt.GlobalColor.transparent if transparent else QColor("#3E05C2"))
    image.save(str(path))
    return path


@pytest.fixture
def store(qapp, tmp_path: Path) -> BannerStore:
    return BannerStore(tmp_path / "banners")


def test_big_image_is_copied_and_reduced(store: BannerStore, tmp_path: Path) -> None:
    source = make_image(tmp_path / "grande.png", 3840, 1240)
    name = store.import_image(7, source)

    copy = QImage(str(store.path(name)))
    assert name.startswith("7-") and name.endswith(".jpg")
    assert copy.width() <= MAX_WIDTH and copy.height() <= MAX_HEIGHT
    assert copy.width() / copy.height() == pytest.approx(3840 / 1240, rel=0.01)
    assert source.exists()  # l'original n'est jamais touché


def test_image_with_transparency_stays_png(store: BannerStore, tmp_path: Path) -> None:
    name = store.import_image(1, make_image(tmp_path / "logo.png", 800, 300, transparent=True))
    assert name.endswith(".png")


def test_unreadable_file_gives_a_readable_error(store: BannerStore, tmp_path: Path) -> None:
    fake = tmp_path / "pas-une-image.png"
    fake.write_text("bonjour", encoding="utf-8")
    with pytest.raises(BannerError, match="n'a pas pu être lue"):
        store.import_image(1, fake)


def test_all_banners_of_a_game_can_be_removed(store: BannerStore, tmp_path: Path) -> None:
    source = make_image(tmp_path / "b.png", 400, 120)
    first, second = store.import_image(3, source), store.import_image(3, source)
    other = store.import_image(30, source)  # « 30- » ne doit pas être confondu avec « 3- »

    store.remove_all_for(3)
    assert not store.path(first).exists()
    assert not store.path(second).exists()
    assert store.path(other).exists()
