"""Modèle de la liste des jeux (barre latérale) : données, recherche et tris.

Qt sépare les données (le modèle) de leur affichage (la vue). ``GameListModel``
contient les jeux ; ``GameFilterProxy`` se place entre le modèle et la vue pour
filtrer selon la recherche et trier selon le mode choisi, sans copier les données.

Les méthodes en camelCase (``rowCount``, ``lessThan``…) redéfinissent celles de Qt :
leur nom est imposé.
"""

from collections.abc import Callable
from dataclasses import dataclass, replace
from enum import Enum

from PySide6.QtCore import (
    QAbstractListModel,
    QModelIndex,
    QPersistentModelIndex,
    QPointF,
    QSize,
    QSortFilterProxyModel,
    Qt,
)
from PySide6.QtGui import QColor, QIcon, QPainter
from PySide6.QtWidgets import QStyledItemDelegate, QStyleOptionViewItem

from nova.core.models import Game, GameStats
from nova.ui.formatting import sort_key
from nova.ui.icons import generic_game_icon
from nova.ui.theme.palette import COLORS

type Index = QModelIndex | QPersistentModelIndex


class SortMode(Enum):
    RECENT = "Trier par dernière utilisation"
    PLAYTIME = "Trier par temps de jeu"
    NAME = "Trier par ordre alphabétique"


@dataclass(frozen=True)
class GameRow:
    game: Game
    stats: GameStats
    running_since: float | None  # début de la session en cours, None si fermé

    @property
    def running(self) -> bool:
        return self.running_since is not None


class GameListModel(QAbstractListModel):
    GameIdRole = Qt.ItemDataRole.UserRole + 1
    RunningRole = Qt.ItemDataRole.UserRole + 2

    def __init__(self, icon_for: Callable[[int], QIcon | None]) -> None:
        super().__init__()
        self._icon_for = icon_for
        self._rows: list[GameRow] = []

    def rowCount(self, parent: Index = QModelIndex()) -> int:  # noqa: B008
        return 0 if parent.isValid() else len(self._rows)

    def data(self, index: Index, role: int = Qt.ItemDataRole.DisplayRole):
        if not index.isValid():
            return None
        row = self._rows[index.row()]
        match role:
            case Qt.ItemDataRole.DisplayRole:
                return row.game.display_name
            case Qt.ItemDataRole.DecorationRole:
                return self._icon_for(row.game.id) or generic_game_icon()
            case Qt.ItemDataRole.ToolTipRole:
                return row.game.process_name
            case self.GameIdRole:
                return row.game.id
            case self.RunningRole:
                return row.running
        return None

    def set_library(
        self, games: list[Game], stats: dict[int, GameStats], running: dict[int, float]
    ) -> None:
        self.beginResetModel()
        self._rows = [
            GameRow(game, stats.get(game.id, GameStats(game.id, 0, None, 0)), running.get(game.id))
            for game in games
        ]
        self.endResetModel()

    def set_running(self, game_id: int, since: float | None) -> None:
        for number, row in enumerate(self._rows):
            if row.game.id == game_id:
                self._rows[number] = replace(row, running_since=since)
                index = self.index(number)
                self.dataChanged.emit(index, index, [self.RunningRole])
                return

    def row_at(self, number: int) -> GameRow:
        return self._rows[number]

    def find(self, game_id: int) -> GameRow | None:
        return next((row for row in self._rows if row.game.id == game_id), None)


class GameFilterProxy(QSortFilterProxyModel):
    def __init__(self, model: GameListModel) -> None:
        super().__init__()
        self._model = model
        self._search = ""
        self._mode = SortMode.RECENT
        self.setSourceModel(model)
        self.sort(0)

    def set_search(self, text: str) -> None:
        self._search = sort_key(text.strip())
        self.invalidate()

    def set_sort_mode(self, mode: SortMode) -> None:
        self._mode = mode
        self.invalidate()

    def filterAcceptsRow(self, source_row: int, source_parent: Index) -> bool:
        if not self._search:
            return True
        game = self._model.row_at(source_row).game
        return self._search in sort_key(game.display_name) or self._search in game.process_name

    def lessThan(self, left: Index, right: Index) -> bool:
        return self._key(self._model.row_at(left.row())) < self._key(
            self._model.row_at(right.row())
        )

    def _key(self, row: GameRow) -> tuple:
        """Clé de tri : la plus petite clé apparaît en haut de la liste."""
        name = sort_key(row.game.display_name)
        match self._mode:
            case SortMode.PLAYTIME:
                return (-row.stats.total_seconds, name)
            case SortMode.RECENT:
                # Jeux en cours d'abord, puis du plus récent au plus ancien, puis jamais joués.
                return (not row.running, -(row.stats.last_played_at or 0), name)
            case SortMode.NAME:
                return (name,)


class GameItemDelegate(QStyledItemDelegate):
    """Dessine chaque jeu comme Qt le fait, plus une pastille verte s'il est en cours."""

    ROW_HEIGHT = 40

    def sizeHint(self, option: QStyleOptionViewItem, index: Index) -> QSize:
        hint = super().sizeHint(option, index)
        return QSize(hint.width(), max(hint.height(), self.ROW_HEIGHT))

    def paint(self, painter: QPainter, option: QStyleOptionViewItem, index: Index) -> None:
        super().paint(painter, option, index)
        if index.data(GameListModel.RunningRole):
            painter.save()
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(COLORS["running"]))
            center = QPointF(option.rect.right() - 14, option.rect.center().y())
            painter.drawEllipse(center, 4, 4)
            painter.restore()
