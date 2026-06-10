"""Frameless targeting overlay with spell preview, drag, resize, and rotate."""

from __future__ import annotations

import math
from dataclasses import replace
from typing import List, Optional

from PyQt6.QtCore import QPoint, Qt, pyqtSignal
from PyQt6.QtGui import QColor, QPainter, QPainterPath, QPen, QShowEvent
from PyQt6.QtWidgets import QWidget

from .models import SpellConfig, Stroke
from .spell_composer import compose_spell

OVERLAY_MARGIN = 40
MIN_DIAMETER = 80
MAX_DIAMETER = 800
BORDER_HIT_PX = 10
HANDLE_HIT_PX = 12
HANDLE_RADIUS = 5
BOUNDS_PADDING = 16


class OverlayWindow(QWidget):
    """Frameless targeting overlay with drag, circle resize, and spell rotation."""

    center_moved = pyqtSignal(float, float)
    diameter_changed = pyqtSignal(int)
    rotation_changed = pyqtSignal(float)

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        """
        Create a translucent, always-on-top overlay widget.

        Parameters
        ----------
        parent : QWidget, optional
            Qt parent widget.
        """
        super().__init__(parent)
        self._config: Optional[SpellConfig] = None
        self._strokes: List[Stroke] = []
        self._dragging = False
        self._resizing = False
        self._rotating = False
        self._drag_offset = QPoint()
        self._rotate_start_angle = 0.0
        self._rotate_start_value = 0.0

        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setMouseTracking(True)

    def update_spell(self, config: SpellConfig) -> None:
        """
        Apply a new spell configuration and refresh the preview.

        Parameters
        ----------
        config : SpellConfig
            Spell parameters and overlay geometry.

        Returns
        -------
        None
        """
        self._config = config
        self._recompose(keep_position=True)

    def _preview_config(self) -> SpellConfig:
        """
        Build a config with overlay center at the widget's local midpoint.

        Returns
        -------
        SpellConfig
            Copy of the current config for local-coordinate preview strokes.
        """
        assert self._config is not None
        size = self.width() if self.width() > 0 else int(
            self._config.circle_diameter_px + OVERLAY_MARGIN * 2
        )
        local_center = (size / 2.0, size / 2.0)
        return replace(self._config, overlay_center=local_center)

    def _refresh_strokes(self) -> None:
        """
        Recompute preview strokes in local widget coordinates.

        Returns
        -------
        None
        """
        if not self._config:
            return
        self._strokes = compose_spell(self._preview_config()).strokes

    def _stroke_half_extent(self) -> float:
        """
        Return the farthest stroke distance from the local center.

        Returns
        -------
        float
            Half-size needed to contain the preview.
        """
        assert self._config is not None
        cx, cy = self._local_center()
        extent = self._config.circle_diameter_px / 2.0
        for stroke in self._strokes:
            for x, y in stroke:
                extent = max(extent, math.hypot(x - cx, y - cy))
        return extent + BOUNDS_PADDING

    def _recompose(self, *, keep_position: bool = False) -> None:
        """
        Resize the window, refresh strokes, and position on screen.

        Parameters
        ----------
        keep_position : bool, optional
            When ``True``, keep the current screen center while resizing.

        Returns
        -------
        None
        """
        if not self._config:
            return

        old_center = self.center() if keep_position and self.isVisible() else None
        min_size = int(self._config.circle_diameter_px + OVERLAY_MARGIN * 2)
        self.setFixedSize(min_size, min_size)
        self._refresh_strokes()

        needed = int(self._stroke_half_extent() * 2)
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
        """
        Sync screen center and refresh strokes after the window is shown.

        Parameters
        ----------
        event : QShowEvent
            Qt show event.

        Returns
        -------
        None
        """
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
            ``(x, y)`` screen position of the widget center.
        """
        geo = self.geometry()
        return (geo.x() + geo.width() / 2, geo.y() + geo.height() / 2)

    def diameter(self) -> int:
        """
        Return the current circle diameter in pixels.

        Returns
        -------
        int
            Circle diameter from the active config.
        """
        if not self._config:
            return MIN_DIAMETER
        return self._config.circle_diameter_px

    def rotation(self) -> float:
        """
        Return the current whole-spell rotation in degrees.

        Returns
        -------
        float
            Rotation from the active config.
        """
        if not self._config:
            return 0.0
        return self._config.overlay_rotation_deg

    def _local_center(self) -> tuple[float, float]:
        """
        Return the widget center in local coordinates.

        Returns
        -------
        tuple of float
            ``(width/2, height/2)``.
        """
        return (self.width() / 2, self.height() / 2)

    def _circle_radius(self) -> float:
        assert self._config is not None
        return self._config.circle_diameter_px / 2.0

    def _resize_handle_pos(self) -> tuple[float, float]:
        cx, cy = self._local_center()
        return cx, cy - self._circle_radius()

    def _rotate_handle_pos(self) -> tuple[float, float]:
        cx, cy = self._local_center()
        return cx + self._circle_radius(), cy

    def _border_distance(self, local_x: float, local_y: float) -> float:
        """
        Distance from ``(local_x, local_y)`` to the circle border.

        Parameters
        ----------
        local_x, local_y : float
            Point in widget coordinates.

        Returns
        -------
        float
            Absolute difference between point radius and circle radius.
        """
        if not self._config:
            return float("inf")
        cx, cy = self._local_center()
        radius = self._circle_radius()
        dist = math.hypot(local_x - cx, local_y - cy)
        return abs(dist - radius)

    def _handle_distance(
        self,
        local_x: float,
        local_y: float,
        handle_x: float,
        handle_y: float,
    ) -> float:
        return math.hypot(local_x - handle_x, local_y - handle_y)

    def _draw_handle(
        self,
        painter: QPainter,
        x: float,
        y: float,
        *,
        fill: QColor,
        outline: QColor,
    ) -> None:
        painter.setPen(QPen(outline, 1))
        painter.setBrush(fill)
        painter.drawEllipse(QPoint(int(x), int(y)), HANDLE_RADIUS, HANDLE_RADIUS)

    def paintEvent(self, event) -> None:  # noqa: N802
        """
        Draw the dimmed mask, preview strokes, circle, and handles.

        Parameters
        ----------
        event : QPaintEvent
            Qt paint event.

        Returns
        -------
        None
        """
        if not self._config or not self._strokes:
            return

        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        w, h = self.width(), self.height()
        local_cx, local_cy = w / 2, h / 2
        radius = self._circle_radius()

        outer = QPainterPath()
        outer.addRect(0, 0, w, h)
        hole = QPainterPath()
        hole.addEllipse(local_cx - radius, local_cy - radius, radius * 2, radius * 2)
        mask = outer.subtracted(hole)

        painter.fillPath(mask, QColor(30, 30, 30, 90))

        pen = QPen(QColor(120, 120, 120, 180))
        pen.setWidthF(1.5)
        painter.setPen(pen)

        for stroke in self._strokes:
            if len(stroke) < 2:
                continue
            for i in range(len(stroke) - 1):
                x1, y1 = stroke[i]
                x2, y2 = stroke[i + 1]
                painter.drawLine(int(x1), int(y1), int(x2), int(y2))

        border_pen = QPen(QColor(200, 200, 200, 160))
        border_pen.setWidth(2)
        border_pen.setStyle(Qt.PenStyle.DashLine)
        painter.setPen(border_pen)
        painter.drawEllipse(
            int(local_cx - radius),
            int(local_cy - radius),
            int(radius * 2),
            int(radius * 2),
        )

        resize_x, resize_y = self._resize_handle_pos()
        rotate_x, rotate_y = self._rotate_handle_pos()
        self._draw_handle(
            painter,
            resize_x,
            resize_y,
            fill=QColor(255, 255, 255, 180),
            outline=QColor(255, 255, 255, 200),
        )
        self._draw_handle(
            painter,
            rotate_x,
            rotate_y,
            fill=QColor(255, 196, 96, 200),
            outline=QColor(255, 220, 140, 220),
        )

        painter.end()

    def mousePressEvent(self, event) -> None:  # noqa: N802
        """
        Start dragging, resizing, or rotating on left mouse press.

        Parameters
        ----------
        event : QMouseEvent
            Qt mouse event.

        Returns
        -------
        None
        """
        if event.button() != Qt.MouseButton.LeftButton or not self._config:
            return

        pos = event.position()
        px, py = pos.x(), pos.y()
        resize_x, resize_y = self._resize_handle_pos()
        rotate_x, rotate_y = self._rotate_handle_pos()

        if self._handle_distance(px, py, resize_x, resize_y) <= HANDLE_HIT_PX:
            self._resizing = True
            return

        if self._handle_distance(px, py, rotate_x, rotate_y) <= HANDLE_HIT_PX:
            cx, cy = self._local_center()
            self._rotating = True
            self._rotate_start_angle = math.degrees(math.atan2(py - cy, px - cx))
            self._rotate_start_value = self._config.overlay_rotation_deg
            return

        if self._border_distance(px, py) <= BORDER_HIT_PX:
            self._resizing = True
            return

        self._dragging = True
        self._drag_offset = event.globalPosition().toPoint() - self.frameGeometry().topLeft()

    def mouseMoveEvent(self, event) -> None:  # noqa: N802
        """
        Handle overlay drag, circle resize, rotation, and cursor updates.

        Parameters
        ----------
        event : QMouseEvent
            Qt mouse event.

        Returns
        -------
        None
        """
        if not self._config:
            return

        pos = event.position()
        px, py = pos.x(), pos.y()

        if self._resizing:
            cx, cy = self._local_center()
            new_radius = math.hypot(px - cx, py - cy)
            new_diameter = int(round(new_radius * 2))
            new_diameter = max(MIN_DIAMETER, min(MAX_DIAMETER, new_diameter))
            if new_diameter != self._config.circle_diameter_px:
                self._config.circle_diameter_px = new_diameter
                self._recompose(keep_position=True)
                self.diameter_changed.emit(new_diameter)
            return

        if self._rotating:
            cx, cy = self._local_center()
            angle = math.degrees(math.atan2(py - cy, px - cx))
            delta = angle - self._rotate_start_angle
            new_rotation = self._rotate_start_value + delta
            if new_rotation != self._config.overlay_rotation_deg:
                self._config.overlay_rotation_deg = new_rotation
                self._recompose(keep_position=True)
                self.rotation_changed.emit(new_rotation)
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

        resize_x, resize_y = self._resize_handle_pos()
        rotate_x, rotate_y = self._rotate_handle_pos()
        if self._handle_distance(px, py, resize_x, resize_y) <= HANDLE_HIT_PX:
            self.setCursor(Qt.CursorShape.SizeVerCursor)
        elif self._handle_distance(px, py, rotate_x, rotate_y) <= HANDLE_HIT_PX:
            self.setCursor(Qt.CursorShape.CrossCursor)
        elif self._border_distance(px, py) <= BORDER_HIT_PX:
            self.setCursor(Qt.CursorShape.SizeFDiagCursor)
        else:
            self.setCursor(Qt.CursorShape.OpenHandCursor)

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802
        """
        End drag, resize, or rotate on left mouse release.

        Parameters
        ----------
        event : QMouseEvent
            Qt mouse event.

        Returns
        -------
        None
        """
        if event.button() == Qt.MouseButton.LeftButton:
            self._dragging = False
            self._resizing = False
            self._rotating = False
            self.setCursor(Qt.CursorShape.ArrowCursor)
