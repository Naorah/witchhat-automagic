"""Draggable overlay showing the calibration test pattern."""

from __future__ import annotations

from typing import List, Optional

from PyQt6.QtCore import QPoint, Qt, pyqtSignal
from PyQt6.QtGui import QColor, QPainter, QPen, QShowEvent
from PyQt6.QtWidgets import QWidget

from src.models import Point, Stroke

OVERLAY_MARGIN = 48


class CalibratorOverlay(QWidget):
    """Frameless overlay for positioning the calibration draw area."""

    center_moved = pyqtSignal(float, float)

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        """
        Create a frameless overlay for calibration pattern preview.

        Parameters
        ----------
        parent : QWidget or None, optional
            Parent widget.

        Returns
        -------
        None
        """
        super().__init__(parent)
        self._center: Point = (400.0, 400.0)
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

    def set_preview(self, center: Point, strokes: List[Stroke], size_px: int) -> None:
        """
        Update center, local preview strokes, and window size.

        Parameters
        ----------
        center : tuple of float
            Overlay center in screen coordinates.
        strokes : list of Stroke
            Test pattern strokes to preview.
        size_px : int
            Nominal pattern size in pixels.

        Returns
        -------
        None
        """
        self._center = center
        self._strokes = strokes
        extent = size_px / 2.0 + OVERLAY_MARGIN
        side = int(extent * 2)
        self.setFixedSize(side, side)
        top_left_x = int(center[0] - side / 2)
        top_left_y = int(center[1] - side / 2)
        self.move(top_left_x, top_left_y)
        self.update()

    def center(self) -> Point:
        """
        Return the overlay center in screen coordinates.

        Returns
        -------
        tuple of float
            ``(x, y)`` center position.
        """
        geo = self.geometry()
        return (geo.x() + geo.width() / 2, geo.y() + geo.height() / 2)

    def showEvent(self, event: QShowEvent) -> None:
        super().showEvent(event)
        self._center = self.center()

    def paintEvent(self, event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()
        painter.fillRect(0, 0, w, h, QColor(30, 30, 30, 90))

        cx, cy = w / 2, h / 2
        offset_x = cx - self._center[0]
        offset_y = cy - self._center[1]

        pen = QPen(QColor(120, 200, 120, 220))
        pen.setWidthF(1.5)
        painter.setPen(pen)
        for stroke in self._strokes:
            if len(stroke) < 2:
                continue
            for i in range(len(stroke) - 1):
                x1, y1 = stroke[i]
                x2, y2 = stroke[i + 1]
                painter.drawLine(
                    int(x1 + offset_x),
                    int(y1 + offset_y),
                    int(x2 + offset_x),
                    int(y2 + offset_y),
                )
        painter.end()

    def mousePressEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton:
            self._dragging = True
            self._drag_offset = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            self.setCursor(Qt.CursorShape.ClosedHandCursor)

    def mouseMoveEvent(self, event) -> None:  # noqa: N802
        if self._dragging:
            new_pos = event.globalPosition().toPoint() - self._drag_offset
            self.move(new_pos)
            self._center = self.center()
            self.center_moved.emit(self._center[0], self._center[1])
            self.update()
        else:
            self.setCursor(Qt.CursorShape.OpenHandCursor)

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton:
            self._dragging = False
            self.setCursor(Qt.CursorShape.OpenHandCursor)
