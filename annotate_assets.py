#!/usr/bin/env python3
"""
Manual editor for sigil and sign point graphs.

Walk through images one by one: place points, create links, validate, next.

Usage:
    python annotate_assets.py
    python annotate_assets.py --kind signs
    python annotate_assets.py --from Crosshair
"""

from __future__ import annotations

import argparse
import math
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Tuple

from PyQt6.QtCore import QPointF, QSize, Qt, pyqtSignal
from PyQt6.QtGui import (
    QBrush,
    QColor,
    QCursor,
    QFont,
    QKeySequence,
    QPainter,
    QPen,
    QPixmap,
    QShortcut,
)
from PyQt6.QtWidgets import (
    QApplication,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from src.assets import (
    PATH_SIGILS_DIR,
    PATH_SIGNS_DIR,
    WEBP_SIGILS_DIR,
    WEBP_SIGNS_DIR,
    normalize_asset_name,
)
from src.models import Point
from src.point_graph import PointGraph
from src.point_graph_io import merge_nearby_vertices, try_load_point_graph, write_point_graph_svg
from src.ui.frameless_shell import FramelessShell
from src.ui.theme import (
    ACCENT,
    BG_CANVAS,
    BG_INPUT,
    BORDER_SUBTLE,
    LIST_ANNOTATED,
    LIST_PENDING,
    TEXT_PRIMARY,
    apply_app_theme,
)

Edge = Tuple[int, int]

VIEWBOX = 100.0
HIT_RADIUS = 10.0
DELETE_HIT_RADIUS = 14.0
LIST_COLOR_ANNOTATED = QColor(LIST_ANNOTATED)
LIST_COLOR_PENDING = QColor(LIST_PENDING)
# 13px font (~16px line) + 4px vertical padding × 2
LIST_ITEM_HEIGHT = 24


@dataclass
class AssetItem:
    """
    One raster source image and its target point-graph SVG path.

    Attributes
    ----------
    kind : str
        Asset kind (``sigil`` or ``sign``).
    name : str
        Normalized catalogue name.
    image_path : Path
        Source WebP file under ``images/webp/``.
    svg_path : Path
        Output point-graph SVG under ``path/``.
    """

    kind: str
    name: str
    image_path: Path
    svg_path: Path


def _discover_assets(kind_filter: Optional[str] = None) -> List[AssetItem]:
    """
    List WebP sources that can be manually annotated.

    Parameters
    ----------
    kind_filter : str or None, optional
        When set, limit to ``sigil`` or ``sign``.

    Returns
    -------
    list of AssetItem
        Sorted catalogue entries with image and SVG paths.
    """
    items: List[AssetItem] = []
    pairs = [
        ("sigil", WEBP_SIGILS_DIR, PATH_SIGILS_DIR),
        ("sign", WEBP_SIGNS_DIR, PATH_SIGNS_DIR),
    ]
    for kind, image_dir, svg_dir in pairs:
        if kind_filter and kind != kind_filter:
            continue
        if not image_dir.is_dir():
            continue
        for image_path in sorted(image_dir.glob("*.webp")):
            name = normalize_asset_name(image_path.stem)
            svg_path = svg_dir / f"{name}.svg"
            items.append(AssetItem(kind, name, image_path, svg_path))
    return items


class AnnotationCanvas(QWidget):
    """
    Interactive canvas for placing vertices and edges on a reference image.

    Signals
    -------
    about_to_change
        Emitted before a mutating edit so the host can snapshot undo state.
    graph_changed
        Emitted after the point graph changes.
    """

    about_to_change = pyqtSignal()
    graph_changed = pyqtSignal()

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        """
        Initialize an empty annotation canvas.

        Parameters
        ----------
        parent : QWidget or None, optional
            Parent widget.

        Returns
        -------
        None
        """
        super().__init__(parent)
        self.setMinimumSize(520, 520)
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

        self._pixmap: Optional[QPixmap] = None
        self._vertices: List[Point] = []
        self._edges: List[Edge] = []
        self._mode = "point"
        self._link_start: Optional[int] = None
        self._hover_index: Optional[int] = None
        self._drag_index: Optional[int] = None
        self._image_rect = self.rect()

    def set_image(self, path: Path) -> None:
        """
        Load the reference WebP shown behind the graph.

        Parameters
        ----------
        path : Path
            Raster image file path.

        Returns
        -------
        None
        """
        self._pixmap = QPixmap(str(path))
        self.update()

    def set_graph(self, graph: PointGraph) -> None:
        """
        Replace the current point graph and refresh the canvas.

        Parameters
        ----------
        graph : PointGraph
            Vertices and edges in viewBox coordinates.

        Returns
        -------
        None
        """
        self._vertices = list(graph.vertices)
        self._edges = list(graph.edges)
        self._link_start = None
        self.update()
        self.graph_changed.emit()

    def get_graph(self) -> PointGraph:
        """
        Return a copy of the current point graph.

        Returns
        -------
        PointGraph
            Vertices and edges in viewBox coordinates.
        """
        return PointGraph(vertices=list(self._vertices), edges=list(self._edges))

    def set_mode(self, mode: str) -> None:
        """
        Switch interaction mode and update the cursor.

        Parameters
        ----------
        mode : str
            One of ``point``, ``link``, ``move``, or ``delete``.

        Returns
        -------
        None
        """
        self._mode = mode
        self._link_start = None
        self._drag_index = None
        if mode == "move":
            self.setCursor(QCursor(Qt.CursorShape.SizeAllCursor))
        elif mode == "delete":
            self.setCursor(QCursor(Qt.CursorShape.CrossCursor))
        else:
            self.setCursor(QCursor(Qt.CursorShape.ArrowCursor))
        self.update()

    def current_mode(self) -> str:
        """Return the active canvas interaction mode."""
        return self._mode

    def hovered_vertex(self) -> Optional[int]:
        """Return the vertex index under the cursor, if any."""
        return self._hover_index

    def edges_incident(self, index: int) -> List[Edge]:
        """Return all edges connected to vertex ``index``."""
        return self._edges_incident(index)

    def clear_graph(self) -> None:
        """Remove all vertices and edges from the canvas."""
        self._vertices.clear()
        self._edges.clear()
        self._link_start = None
        self.update()
        self.graph_changed.emit()

    def undo_graph(self, graph: PointGraph) -> None:
        """
        Restore a previously snapshotted graph.

        Parameters
        ----------
        graph : PointGraph
            Graph state to restore.

        Returns
        -------
        None
        """
        self.set_graph(graph)

    def _content_rect(self) -> Tuple[float, float, float, float]:
        if not self._pixmap or self._pixmap.isNull():
            margin = 20.0
            w = max(1.0, self.width() - 2 * margin)
            h = max(1.0, self.height() - 2 * margin)
            return margin, margin, w, h

        pw = float(self._pixmap.width())
        ph = float(self._pixmap.height())
        scale = min(self.width() / pw, self.height() / ph) * 0.92
        draw_w = pw * scale
        draw_h = ph * scale
        x = (self.width() - draw_w) / 2
        y = (self.height() - draw_h) / 2
        return x, y, draw_w, draw_h

    def _viewbox_to_widget(self, point: Point) -> QPointF:
        x, y, w, h = self._content_rect()
        wx = x + (point[0] / VIEWBOX) * w
        wy = y + (point[1] / VIEWBOX) * h
        return QPointF(wx, wy)

    def _widget_to_viewbox(self, wx: float, wy: float) -> Point:
        x, y, w, h = self._content_rect()
        vx = max(0.0, min(VIEWBOX, (wx - x) / w * VIEWBOX))
        vy = max(0.0, min(VIEWBOX, (wy - y) / h * VIEWBOX))
        return (vx, vy)

    def _hit_radius(self) -> float:
        """Pick radius for vertex hit-testing (larger in delete mode)."""
        return DELETE_HIT_RADIUS if self._mode == "delete" else HIT_RADIUS

    def _edges_incident(self, index: int) -> List[Edge]:
        """Return all edges connected to vertex ``index``."""
        return [(a, b) for a, b in self._edges if a == index or b == index]

    def _nearest_vertex(self, wx: float, wy: float) -> Optional[int]:
        best_idx: Optional[int] = None
        best_dist = self._hit_radius()
        for idx, vertex in enumerate(self._vertices):
            pos = self._viewbox_to_widget(vertex)
            dist = math.hypot(wx - pos.x(), wy - pos.y())
            if dist <= best_dist:
                best_dist = dist
                best_idx = idx
        return best_idx

    def _push_undo(self) -> PointGraph:
        return self.get_graph()

    def _add_edge(self, a: int, b: int) -> None:
        if a == b:
            return
        key = (a, b) if a < b else (b, a)
        if key in self._edges:
            return
        self._edges.append(key)
        self.graph_changed.emit()

    def _reindex_after_vertex_removed(self, index: int) -> None:
        """Adjust transient indices after vertex ``index`` was removed."""
        if self._link_start is not None:
            if self._link_start == index:
                self._link_start = None
            elif self._link_start > index:
                self._link_start -= 1
        if self._drag_index is not None:
            if self._drag_index == index:
                self._drag_index = None
            elif self._drag_index > index:
                self._drag_index -= 1
        if self._hover_index is not None:
            if self._hover_index == index:
                self._hover_index = None
            elif self._hover_index > index:
                self._hover_index -= 1

    def _remove_vertex(self, index: int) -> int:
        """
        Remove a vertex and every edge incident to it.

        Parameters
        ----------
        index : int
            Vertex index to delete.

        Returns
        -------
        int
            Number of edges removed.
        """
        if index < 0 or index >= len(self._vertices):
            return 0
        removed_edges = len(self._edges_incident(index))
        self._vertices.pop(index)
        self._edges = [
            (a, b)
            for a, b in self._edges
            if a != index and b != index
        ]
        self._edges = [
            (a - 1 if a > index else a, b - 1 if b > index else b)
            for a, b in self._edges
        ]
        self._reindex_after_vertex_removed(index)
        self.graph_changed.emit()
        return removed_edges

    def delete_vertex(self, index: int) -> bool:
        """
        Delete a vertex and its links (records undo snapshot first).

        Parameters
        ----------
        index : int
            Vertex index to delete.

        Returns
        -------
        bool
            ``True`` if a vertex was removed.
        """
        if index < 0 or index >= len(self._vertices):
            return False
        self.about_to_change.emit()
        self._remove_vertex(index)
        self.update()
        return True

    def delete_hovered_vertex(self) -> bool:
        """
        Delete the vertex currently under the cursor in delete mode.

        Returns
        -------
        bool
            ``True`` if a vertex was removed.
        """
        if self._mode != "delete" or self._hover_index is None:
            return False
        return self.delete_vertex(self._hover_index)

    def mousePressEvent(self, event) -> None:
        if event.button() != Qt.MouseButton.LeftButton:
            return

        wx, wy = event.position().x(), event.position().y()
        hit = self._nearest_vertex(wx, wy)

        if self._mode == "move":
            if hit is not None:
                self.about_to_change.emit()
                self._drag_index = hit
            self.update()
            return

        if self._mode == "point":
            if hit is not None:
                return
            self.about_to_change.emit()
            self._vertices.append(self._widget_to_viewbox(wx, wy))
            self.graph_changed.emit()
            self.update()
            return

        if self._mode == "link":
            if hit is None:
                return
            if self._link_start is None:
                self._link_start = hit
            else:
                self.about_to_change.emit()
                self._add_edge(self._link_start, hit)
                self._link_start = None
            self.update()
            return

        if self._mode == "delete":
            if hit is not None:
                self.delete_vertex(hit)
            return

    def mouseMoveEvent(self, event) -> None:
        wx, wy = event.position().x(), event.position().y()

        if self._mode == "move" and self._drag_index is not None:
            self._vertices[self._drag_index] = self._widget_to_viewbox(wx, wy)
            self.graph_changed.emit()
            self.update()
            return

        prev_hover = self._hover_index
        self._hover_index = self._nearest_vertex(wx, wy)
        if self._mode == "delete" and self._hover_index != prev_hover:
            self.graph_changed.emit()
        self.update()

    def mouseReleaseEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_index = None
            self.update()

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        painter.fillRect(self.rect(), QColor(BG_CANVAS))

        x, y, w, h = self._content_rect()
        self._image_rect = self.rect()
        painter.setPen(QPen(QColor(BORDER_SUBTLE), 1))
        painter.setBrush(QBrush(QColor(BG_INPUT)))
        painter.drawRect(int(x - 4), int(y - 4), int(w + 8), int(h + 8))

        if self._pixmap and not self._pixmap.isNull():
            painter.drawPixmap(int(x), int(y), int(w), int(h), self._pixmap)

        delete_target = (
            self._hover_index
            if self._mode == "delete" and self._hover_index is not None
            else None
        )
        incident: set[Edge] = set()
        if delete_target is not None:
            incident = {tuple(sorted(e)) for e in self._edges_incident(delete_target)}

        for a, b in self._edges:
            if a < len(self._vertices) and b < len(self._vertices):
                p1 = self._viewbox_to_widget(self._vertices[a])
                p2 = self._viewbox_to_widget(self._vertices[b])
                key = tuple(sorted((a, b)))
                if key in incident:
                    painter.setPen(QPen(QColor(255, 90, 90, 200), 3))
                else:
                    painter.setPen(QPen(QColor(ACCENT), 2))
                painter.drawLine(p1, p2)

        if self._link_start is not None and self._link_start < len(self._vertices):
            painter.setPen(QPen(QColor(255, 200, 80), 2, Qt.PenStyle.DashLine))
            center = self._viewbox_to_widget(self._vertices[self._link_start])
            painter.drawEllipse(center, 14, 14)

        font = QFont("Segoe UI", 9)
        painter.setFont(font)
        for idx, vertex in enumerate(self._vertices):
            pos = self._viewbox_to_widget(vertex)
            selected = idx in (self._link_start, self._hover_index, self._drag_index)
            if self._mode == "delete" and idx == self._hover_index:
                color = QColor(255, 60, 60)
                radius = 9
            elif idx == self._drag_index:
                color = QColor(100, 220, 120)
                radius = 7
            elif selected:
                color = QColor(255, 120, 80)
                radius = 7
            else:
                color = QColor(255, 70, 70)
                radius = 7
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QBrush(color))
            painter.drawEllipse(pos, radius, radius)
            if self._mode == "delete" and idx == self._hover_index:
                painter.setPen(QPen(QColor(255, 255, 255), 2))
                r = radius * 0.55
                painter.drawLine(
                    QPointF(pos.x() - r, pos.y() - r),
                    QPointF(pos.x() + r, pos.y() + r),
                )
                painter.drawLine(
                    QPointF(pos.x() + r, pos.y() - r),
                    QPointF(pos.x() - r, pos.y() + r),
                )
            painter.setPen(QPen(QColor(TEXT_PRIMARY)))
            painter.drawText(
                int(pos.x() + 10),
                int(pos.y() + 4),
                str(idx),
            )

        painter.end()


class AnnotatorWindow(QWidget):
    """Annotation workspace panel (embedded in a frameless shell)."""

    def __init__(self, assets: List[AssetItem], start_index: int = 0) -> None:
        """
        Build the asset list, canvas, and annotation controls.

        Parameters
        ----------
        assets : list of AssetItem
            Catalogue entries to annotate in order.
        start_index : int, optional
            Initial list selection index, by default ``0``.

        Returns
        -------
        None
        """
        super().__init__()
        self._assets = assets
        self._index = start_index
        self._undo_stack: List[PointGraph] = []
        self._mode_buttons: dict[str, QPushButton] = {}

        root = QVBoxLayout(self)
        root.setContentsMargins(18, 16, 18, 18)
        root.setSpacing(12)

        self._title = QLabel()
        self._title.setObjectName("PageTitle")
        root.addWidget(self._title)

        self._hint = QLabel(
            "Points (P) · Links (L) · Move (M) · Delete point (D) · "
            "Delete/Backspace removes hovered point · Enter = validate"
        )
        self._hint.setObjectName("HintLabel")
        self._hint.setWordWrap(True)
        root.addWidget(self._hint)

        body = QHBoxLayout()

        list_panel = QVBoxLayout()
        list_label = QLabel("Images")
        list_label.setObjectName("PanelTitle")
        list_panel.addWidget(list_label)

        self._list = QListWidget()
        self._list.setMinimumWidth(200)
        self._list.setMaximumWidth(260)
        self._list.setSpacing(0)
        for item in self._assets:
            row = QListWidgetItem()
            row.setToolTip(str(item.image_path))
            self._update_list_item(row, item)
            self._list.addItem(row)
        self._list.currentRowChanged.connect(self._on_list_select)
        list_panel.addWidget(self._list)
        body.addLayout(list_panel)

        right = QVBoxLayout()
        self._canvas = AnnotationCanvas()
        self._canvas.about_to_change.connect(self._snapshot)
        self._canvas.graph_changed.connect(self._update_status)
        self._active_mode = "point"
        right.addWidget(self._canvas, stretch=1)

        self._status = QLabel()
        self._status.setObjectName("StatusLabel")
        self._status.setWordWrap(True)
        right.addWidget(self._status)
        body.addLayout(right, stretch=1)
        root.addLayout(body, stretch=1)

        buttons = QHBoxLayout()
        self._btn_point = QPushButton("Points (P)")
        self._btn_link = QPushButton("Links (L)")
        self._btn_move = QPushButton("Move (M)")
        self._btn_delete = QPushButton("Delete point (D)")
        self._btn_delete.setToolTip(
            "Click a point to remove it and all of its links"
        )
        self._btn_undo = QPushButton("Undo (Ctrl+Z)")
        self._btn_clear = QPushButton("Clear")
        self._btn_prev = QPushButton("← Previous")
        self._btn_skip = QPushButton("Skip")
        self._btn_validate = QPushButton("Validate (Enter)")
        self._btn_validate.setObjectName("PrimaryButton")
        self._btn_next = QPushButton("Next →")

        self._mode_buttons = {
            "point": self._btn_point,
            "link": self._btn_link,
            "move": self._btn_move,
            "delete": self._btn_delete,
        }

        for btn in (
            self._btn_point,
            self._btn_link,
            self._btn_move,
            self._btn_delete,
            self._btn_undo,
            self._btn_clear,
            self._btn_prev,
            self._btn_skip,
            self._btn_validate,
            self._btn_next,
        ):
            buttons.addWidget(btn)

        root.addLayout(buttons)

        self._btn_point.clicked.connect(lambda: self._set_mode("point"))
        self._btn_link.clicked.connect(lambda: self._set_mode("link"))
        self._btn_move.clicked.connect(lambda: self._set_mode("move"))
        self._btn_delete.clicked.connect(lambda: self._set_mode("delete"))
        self._btn_undo.clicked.connect(self._undo)
        self._btn_clear.clicked.connect(self._clear)
        self._btn_prev.clicked.connect(self._prev_asset)
        self._btn_skip.clicked.connect(self._next_asset)
        self._btn_validate.clicked.connect(self._validate)
        self._btn_next.clicked.connect(self._next_asset)

        QShortcut(QKeySequence("P"), self, activated=lambda: self._set_mode("point"))
        QShortcut(QKeySequence("L"), self, activated=lambda: self._set_mode("link"))
        QShortcut(QKeySequence("M"), self, activated=lambda: self._set_mode("move"))
        QShortcut(QKeySequence("D"), self, activated=lambda: self._set_mode("delete"))
        QShortcut(QKeySequence("Ctrl+Z"), self, activated=self._undo)
        QShortcut(QKeySequence("Return"), self, activated=self._validate)
        QShortcut(QKeySequence("Enter"), self, activated=self._validate)
        QShortcut(QKeySequence(Qt.Key.Key_Right), self, activated=self._next_asset)
        QShortcut(QKeySequence(Qt.Key.Key_Left), self, activated=self._prev_asset)
        QShortcut(QKeySequence(Qt.Key.Key_Delete), self, activated=self._delete_hovered)
        QShortcut(QKeySequence(Qt.Key.Key_Backspace), self, activated=self._delete_hovered)

        self._load_current()
        self._set_mode("point")

    def _set_mode(self, mode: str) -> None:
        self._active_mode = mode
        self._canvas.set_mode(mode)
        self._update_status()
        for name, btn in self._mode_buttons.items():
            btn.setObjectName("ModeButtonActive" if name == mode else "")
            btn.style().unpolish(btn)
            btn.style().polish(btn)

    def _snapshot(self) -> None:
        self._undo_stack.append(self._canvas.get_graph())
        if len(self._undo_stack) > 50:
            self._undo_stack.pop(0)

    def _undo(self) -> None:
        if not self._undo_stack:
            return
        graph = self._undo_stack.pop()
        self._canvas.undo_graph(graph)

    def _clear(self) -> None:
        if self._vertices_edges_count()[0] == 0:
            return
        reply = QMessageBox.question(
            self,
            "Clear",
            "Remove all points and links for this image?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            self._snapshot()
            self._canvas.clear_graph()

    def _vertices_edges_count(self) -> Tuple[int, int]:
        g = self._canvas.get_graph()
        return len(g.vertices), len(g.edges)

    def _delete_hovered(self) -> None:
        """Delete the vertex under the cursor when delete mode is active."""
        if self._active_mode != "delete":
            return
        self._canvas.delete_hovered_vertex()

    def _update_status(self) -> None:
        v, e = self._vertices_edges_count()
        text = f"Points: {v} · Links: {e}"
        if self._active_mode == "delete":
            hover = self._canvas.hovered_vertex()
            if hover is not None:
                incident = len(self._canvas.edges_incident(hover))
                text += f" · Delete point {hover} ({incident} link(s))"
            else:
                text += " · Delete: click a point (links removed too)"
        self._status.setText(text)

    def _on_list_select(self, row: int) -> None:
        if row < 0 or row >= len(self._assets) or row == self._index:
            return
        self._index = row
        self._load_current(sync_list=False)

    def _update_list_item(self, list_item: QListWidgetItem, item: AssetItem) -> None:
        """
        Refresh list label, checkmark, and color for one asset.

        Parameters
        ----------
        list_item : QListWidgetItem
            Row to update.
        item : AssetItem
            Asset metadata.

        Returns
        -------
        None
        """
        annotated = try_load_point_graph(item.svg_path) is not None
        kind_tag = "sigil" if item.kind == "sigil" else "sign"
        label = f"[{kind_tag}] {item.name}"
        if annotated:
            label += " ✓"
        list_item.setText(label)
        list_item.setSizeHint(QSize(0, LIST_ITEM_HEIGHT))
        list_item.setForeground(
            QBrush(LIST_COLOR_ANNOTATED if annotated else LIST_COLOR_PENDING)
        )

    def _refresh_list_marks(self) -> None:
        for row, item in enumerate(self._assets):
            list_item = self._list.item(row)
            if list_item is None:
                continue
            self._update_list_item(list_item, item)

    def _load_current(self, *, sync_list: bool = True) -> None:
        if not self._assets:
            return
        item = self._assets[self._index]
        self._undo_stack.clear()
        self._title.setText(
            f"[{self._index + 1}/{len(self._assets)}] "
            f"{item.kind.upper()} — {item.name}"
        )
        if sync_list:
            self._list.blockSignals(True)
            self._list.setCurrentRow(self._index)
            self._list.blockSignals(False)

        self._canvas.set_image(item.image_path)

        existing = try_load_point_graph(item.svg_path)
        if existing:
            self._canvas.set_graph(existing)
        else:
            self._canvas.clear_graph()

        self._update_status()

    def _validate(self) -> None:
        if not self._assets:
            return
        item = self._assets[self._index]
        graph = merge_nearby_vertices(self._canvas.get_graph())

        if len(graph.vertices) < 2:
            QMessageBox.warning(
                self,
                "Incomplete",
                "Place at least 2 points before validating.",
            )
            return
        if not graph.edges:
            reply = QMessageBox.question(
                self,
                "No links",
                "No links defined. Save anyway?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            if reply != QMessageBox.StandardButton.Yes:
                return

        write_point_graph_svg(item.svg_path, item.name, graph)
        self._canvas.set_graph(graph)
        self._refresh_list_marks()
        QMessageBox.information(
            self,
            "Saved",
            f"SVG saved:\n{item.svg_path}",
        )
        self._next_asset()

    def _next_asset(self) -> None:
        if self._index < len(self._assets) - 1:
            self._index += 1
            self._load_current()
        else:
            QMessageBox.information(
                self,
                "Done",
                "All images have been reviewed.",
            )

    def _prev_asset(self) -> None:
        if self._index > 0:
            self._index -= 1
            self._load_current()


def main() -> int:
    """
    Launch the manual point-graph annotation tool.

    Returns
    -------
    int
        Qt event-loop exit code (``1`` when no assets are found).
    """
    parser = argparse.ArgumentParser(
        description="Manually annotate sigils and signs (points + links)."
    )
    parser.add_argument(
        "--kind",
        choices=("sigil", "sign"),
        help="Limit to sigils or signs only.",
    )
    parser.add_argument(
        "--from",
        dest="start_name",
        metavar="NAME",
        help="Start at this asset (e.g. Crosshair).",
    )
    args = parser.parse_args()

    assets = _discover_assets(args.kind)
    if not assets:
        print("No WebP images found in images/webp/.", file=sys.stderr)
        return 1

    start_index = 0
    if args.start_name:
        target = normalize_asset_name(args.start_name)
        for i, item in enumerate(assets):
            if item.name.lower() == target.lower():
                start_index = i
                break

    app = QApplication(sys.argv)
    apply_app_theme(app)
    panel = AnnotatorWindow(assets, start_index)
    window = FramelessShell(
        "Manual annotation — Witchhat Automagic",
        panel,
        min_width=1000,
        min_height=680,
        initial_size=(1100, 720),
    )
    window.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
