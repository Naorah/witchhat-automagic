"""Clickable thumbnail grid for sigils and signs."""

from __future__ import annotations

from typing import Dict, Optional, Tuple

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (
    QFrame,
    QGridLayout,
    QLabel,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from src.ui.theme import ACCENT, BG_ELEVATED, BORDER_SUBTLE, TEXT_MUTED, TEXT_PRIMARY

from asset_preview import GRID_PREVIEW_SIZE, asset_preview_pixmap, list_assets

AssetKey = Tuple[str, str]
COLUMNS = 4


class AssetTile(QFrame):
    """One selectable asset thumbnail."""

    clicked = pyqtSignal(str, str)

    def __init__(
        self,
        kind: str,
        name: str,
        parent: Optional[QWidget] = None,
    ) -> None:
        """
        Build a thumbnail tile for one catalogue asset.

        Parameters
        ----------
        kind : str
            Asset kind (``sigil`` or ``sign``).
        name : str
            Asset catalogue name.
        parent : QWidget or None, optional
            Parent widget.

        Returns
        -------
        None
        """
        super().__init__(parent)
        self._kind = kind
        self._name = name
        self._selected = False
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedSize(96, 112)
        self.setObjectName("AssetTile")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 4)
        layout.setSpacing(4)

        self._image = QLabel()
        self._image.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._image.setFixedSize(GRID_PREVIEW_SIZE, GRID_PREVIEW_SIZE)

        pixmap = asset_preview_pixmap(kind, name)
        if pixmap is not None and not pixmap.isNull():
            self._image.setPixmap(pixmap)
        else:
            self._image.setText("?")
            self._image.setStyleSheet(f"color: {TEXT_MUTED};")

        self._label = QLabel(name)
        self._label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._label.setWordWrap(True)
        font = QFont()
        font.setPointSize(8)
        self._label.setFont(font)

        layout.addWidget(self._image, alignment=Qt.AlignmentFlag.AlignHCenter)
        layout.addWidget(self._label)

        self._apply_style()

    def kind(self) -> str:
        """Return the asset kind (``sigil`` or ``sign``)."""
        return self._kind

    def name(self) -> str:
        """Return the asset catalogue name."""
        return self._name

    def set_selected(self, selected: bool) -> None:
        """
        Highlight or clear the tile selection state.

        Parameters
        ----------
        selected : bool
            Whether this tile is the active selection.
        """
        self._selected = selected
        self._apply_style()
        self.update()

    def _apply_style(self) -> None:
        if self._selected:
            border = ACCENT
            background = "#fff3d0"
        else:
            border = BORDER_SUBTLE
            background = BG_ELEVATED
        self.setStyleSheet(
            f"QFrame#AssetTile {{"
            f"  background-color: {background};"
            f"  border: 2px solid {border};"
            f"  border-radius: 8px;"
            f"}}"
            f"QLabel {{ color: {TEXT_PRIMARY}; background: transparent; border: none; }}"
        )

    def mousePressEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit(self._kind, self._name)
        super().mousePressEvent(event)


class AssetGrid(QWidget):
    """Scrollable combined list of sigils and signs."""

    asset_selected = pyqtSignal(str, str)

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        """
        Build the scrollable sigil and sign thumbnail grid.

        Parameters
        ----------
        parent : QWidget or None, optional
            Parent widget.

        Returns
        -------
        None
        """
        super().__init__(parent)
        self._selected: Optional[AssetKey] = None
        self._tiles: Dict[AssetKey, AssetTile] = {}

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)

        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._scroll.setFrameShape(QFrame.Shape.NoFrame)

        self._inner = QWidget()
        self._layout = QVBoxLayout(self._inner)
        self._layout.setContentsMargins(4, 4, 4, 4)
        self._layout.setSpacing(10)
        self._scroll.setWidget(self._inner)
        root.addWidget(self._scroll)

        self._build_all()

    def _build_all(self) -> None:
        self._clear()
        self._add_section("Sigils", "sigil", list_assets("sigil"))
        self._add_separator()
        self._add_section("Signs", "sign", list_assets("sign"))
        self._layout.addStretch()

    def _add_section(self, title: str, kind: str, names: list[str]) -> None:
        heading = QLabel(title)
        heading.setObjectName("SectionTitle")
        self._layout.addWidget(heading)

        grid_host = QWidget()
        grid = QGridLayout(grid_host)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setSpacing(8)

        for index, name in enumerate(names):
            tile = AssetTile(kind, name)
            tile.clicked.connect(self._on_tile_clicked)
            row, col = divmod(index, COLUMNS)
            grid.addWidget(tile, row, col)
            self._tiles[(kind, name)] = tile

        self._layout.addWidget(grid_host)

    def _add_separator(self) -> None:
        separator = QFrame()
        separator.setObjectName("BulkSeparator")
        separator.setFrameShape(QFrame.Shape.HLine)
        separator.setFrameShadow(QFrame.Shadow.Plain)
        self._layout.addWidget(separator)

    def selected_asset(self) -> Optional[AssetKey]:
        """
        Return the currently selected asset key, if any.

        Returns
        -------
        tuple of (str, str) or None
            ``(kind, name)`` for the selection, or ``None``.
        """
        return self._selected

    def select_asset(self, kind: str, name: str) -> None:
        """
        Highlight an asset without emitting ``asset_selected``.

        Parameters
        ----------
        kind : str
            Asset kind.
        name : str
            Asset catalogue name.

        Returns
        -------
        None
        """
        self._selected = (kind, name)
        for key, tile in self._tiles.items():
            tile.set_selected(key == self._selected)

    def _clear(self) -> None:
        while self._layout.count():
            item = self._layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()
        self._tiles.clear()
        self._selected = None

    def _on_tile_clicked(self, kind: str, name: str) -> None:
        self.select_asset(kind, name)
        self.asset_selected.emit(kind, name)
