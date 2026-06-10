"""Draggable overlay preview for a single asset sample."""

from __future__ import annotations

import math
from dataclasses import replace
from typing import List, Optional

from PyQt6.QtCore import QPoint, Qt, pyqtSignal
from PyQt6.QtGui import QColor, QPainter, QPen, QShowEvent
from PyQt6.QtWidgets import QWidget

from src.models import Stroke

from composer import SampleConfig, compose_sample

OVERLAY_MARGIN = 48
BOUNDS_PADDING = 20


class SampleOverlay(QWidget):
    """Frameless, draggable preview of one sigil or sign."""

    center_moved = pyqtSignal(float, float)

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        """
        Create a frameless, draggable sample preview window.

        Parameters
        ----------
        parent : QWidget or None, optional
            Parent widget.

        Returns
        -------
        None
        """
        super().__init__(parent)
        self._config: Optional[SampleConfig] = None
        self._strokes: List[Stroke] = []
        self._dragging = False
        self._drag_offset = QPoint()

        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setMouseTracking(True)

    def update_sample(self, config: SampleConfig) -> None:
        """
        Apply a new sample configuration and refresh the preview.

        Parameters
        ----------
        config : SampleConfig
            Sample rotation, scale, name, and overlay center.

        Returns
        -------
        None
        """
        self._config = config
        self._recompose(keep_position=True)

    def _preview_config(self) -> SampleConfig:
        assert self._config is not None
        size = self.width() if self.width() > 0 else 320
        local_center = (size / 2.0, size / 2.0)
        return replace(self._config, overlay_center=local_center)

    def _refresh_strokes(self) -> None:
        if not self._config or not self._config.name:
            self._strokes = []
            return
        self._strokes = compose_sample(self._preview_config()).strokes

    def _stroke_half_extent(self) -> float:
        assert self._config is not None
        cx, cy = self._local_center()
        if self._strokes:
            extent = 40.0
            for stroke in self._strokes:
                for x, y in stroke:
                    extent = max(extent, math.hypot(x - cx, y - cy))
            return extent + BOUNDS_PADDING
        return 40.0 * (self._config.scale_pct / 100.0) + BOUNDS_PADDING

    def _recompose(self, *, keep_position: bool = False) -> None:
        if not self._config:
            return

        old_center = self.center() if keep_position and self.isVisible() else None
        min_size = 160
        self.setFixedSize(min_size, min_size)
        self._refresh_strokes()

        needed = int(self._stroke_half_extent() * 2 + OVERLAY_MARGIN)
        size = max(min_size, needed)
        if size != min_size:
            self.setFixedSize(size, size)
            self._refresh_strokes()

        if keep_position and old_center:
            top_left_x = int(old_center[0] - size / 2)
            top_left_y = int(old_center[1] - size / 2)
        else:
            top_left_x = int(self._config.overlay_center[0] - size / 2)
            top_left_y = int(self._config.overlay_center[1] - size / 2)

        self.move(top_left_x, top_left_y)
        self.update()

    def showEvent(self, event: QShowEvent) -> None:
        super().showEvent(event)
        if self._config:
            cx, cy = self.center()
            self._config.overlay_center = (cx, cy)
            self._recompose(keep_position=True)

    def center(self) -> tuple[float, float]:
        """
        Return the overlay center in screen coordinates.

        Returns
        -------
        tuple of float
            ``(x, y)`` center position.
        """
        geo = self.geometry()
        return (geo.x() + geo.width() / 2, geo.y() + geo.height() / 2)

    def _local_center(self) -> tuple[float, float]:
        return (self.width() / 2, self.height() / 2)

    def paintEvent(self, event) -> None:  # noqa: N802
        if not self._config:
            return

        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        w, h = self.width(), self.height()
        painter.fillRect(0, 0, w, h, QColor(30, 30, 30, 90))

        local_cx, local_cy = w / 2, h / 2
        cross_pen = QPen(QColor(200, 200, 200, 120))
        cross_pen.setWidth(1)
        painter.setPen(cross_pen)
        painter.drawLine(int(local_cx - 14), int(local_cy), int(local_cx + 14), int(local_cy))
        painter.drawLine(int(local_cx), int(local_cy - 14), int(local_cx), int(local_cy + 14))

        if self._strokes:
            pen = QPen(QColor(120, 120, 120, 200))
            pen.setWidthF(1.5)
            painter.setPen(pen)
            for stroke in self._strokes:
                if len(stroke) < 2:
                    continue
                for i in range(len(stroke) - 1):
                    x1, y1 = stroke[i]
                    x2, y2 = stroke[i + 1]
                    painter.drawLine(int(x1), int(y1), int(x2), int(y2))
        else:
            radius = 30.0 * (self._config.scale_pct / 100.0)
            ring_pen = QPen(QColor(200, 200, 200, 100))
            ring_pen.setWidth(1)
            ring_pen.setStyle(Qt.PenStyle.DashLine)
            painter.setPen(ring_pen)
            painter.drawEllipse(
                int(local_cx - radius),
                int(local_cy - radius),
                int(radius * 2),
                int(radius * 2),
            )

        painter.end()

    def mousePressEvent(self, event) -> None:  # noqa: N802
        if event.button() != Qt.MouseButton.LeftButton or not self._config:
            return
        self._dragging = True
        self._drag_offset = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
        self.setCursor(Qt.CursorShape.ClosedHandCursor)

    def mouseMoveEvent(self, event) -> None:  # noqa: N802
        if not self._config:
            return

        if self._dragging:
            new_pos = event.globalPosition().toPoint() - self._drag_offset
            self.move(new_pos)
            cx = new_pos.x() + self.width() / 2
            cy = new_pos.y() + self.height() / 2
            self._config.overlay_center = (cx, cy)
            self.center_moved.emit(cx, cy)
            self.update()
            return

        self.setCursor(Qt.CursorShape.OpenHandCursor)

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton:
            self._dragging = False
            self.setCursor(Qt.CursorShape.OpenHandCursor)
