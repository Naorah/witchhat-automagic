"""Borderless window title bar with macOS-style traffic lights."""

from __future__ import annotations

from typing import Optional

from PyQt6.QtCore import QPoint, QPointF, Qt, pyqtSignal
from PyQt6.QtGui import QColor, QPainter
from PyQt6.QtWidgets import QHBoxLayout, QLabel, QWidget

from .theme import (
    BG_TITLEBAR,
    TL_CLOSE,
    TL_CLOSE_HOVER,
    TL_MAXIMIZE,
    TL_MAXIMIZE_HOVER,
    TL_MINIMIZE,
    TL_MINIMIZE_HOVER,
    TEXT_PRIMARY,
)

TITLE_BAR_HEIGHT = 40
BUTTON_SIZE = 12
BUTTON_GAP = 7
BUTTON_MARGIN_RIGHT = 8
TITLE_MARGIN_LEFT = 12


class TrafficLight(QWidget):
    """Single circular window control button."""

    clicked = pyqtSignal()

    def __init__(
        self,
        base_color: str,
        hover_color: str,
        parent: Optional[QWidget] = None,
    ) -> None:
        """
        Build one traffic-light control.

        Parameters
        ----------
        base_color : str
            Hex fill color at rest.
        hover_color : str
            Hex fill color on hover.
        parent : QWidget, optional
            Parent widget.
        """
        super().__init__(parent)
        self._base = QColor(base_color)
        self._hover = QColor(hover_color)
        self._hovering = False
        self.setFixedSize(BUTTON_SIZE, BUTTON_SIZE)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def enterEvent(self, event) -> None:
        self._hovering = True
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:
        self._hovering = False
        self.update()
        super().leaveEvent(event)

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()
            event.accept()
            return
        super().mousePressEvent(event)

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        color = self._hover if self._hovering else self._base
        cx = self.width() / 2
        cy = self.height() / 2
        radius = BUTTON_SIZE / 2 - 0.5
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(color)
        painter.drawEllipse(QPointF(cx, cy), radius, radius)
        painter.end()


class TitleBar(QWidget):
    """Custom top bar: draggable title on the left, traffic lights on the right."""

    def __init__(self, title: str, parent: Optional[QWidget] = None) -> None:
        """
        Create a frameless window title bar.

        Parameters
        ----------
        title : str
            Window title text shown beside the traffic lights.
        parent : QWidget, optional
            Host window widget.
        """
        super().__init__(parent)
        self.setObjectName("TitleBar")
        self.setFixedHeight(TITLE_BAR_HEIGHT)
        self._drag_offset: Optional[QPoint] = None

        layout = QHBoxLayout(self)
        layout.setContentsMargins(TITLE_MARGIN_LEFT, 0, BUTTON_MARGIN_RIGHT, 0)
        layout.setSpacing(0)

        self._title = QLabel(title)
        self._title.setStyleSheet(
            f"color: {TEXT_PRIMARY}; font-size: 12px; font-weight: 600; "
            "background: transparent;"
        )
        layout.addWidget(self._title)
        layout.addStretch(1)

        lights = QHBoxLayout()
        lights.setSpacing(BUTTON_GAP)
        self._btn_minimize = TrafficLight(TL_MINIMIZE, TL_MINIMIZE_HOVER)
        self._btn_maximize = TrafficLight(TL_MAXIMIZE, TL_MAXIMIZE_HOVER)
        self._btn_close = TrafficLight(TL_CLOSE, TL_CLOSE_HOVER)
        lights.addWidget(self._btn_minimize)
        lights.addWidget(self._btn_maximize)
        lights.addWidget(self._btn_close)
        layout.addLayout(lights)

        self._btn_close.clicked.connect(self._on_close)
        self._btn_minimize.clicked.connect(self._on_minimize)
        self._btn_maximize.clicked.connect(self._on_toggle_maximize)

        self.setStyleSheet(f"background-color: {BG_TITLEBAR};")

    def _host(self) -> QWidget:
        return self.window()

    def _on_close(self) -> None:
        self._host().close()

    def _on_minimize(self) -> None:
        self._host().showMinimized()

    def _on_toggle_maximize(self) -> None:
        host = self._host()
        if host.isMaximized():
            host.showNormal()
        else:
            host.showMaximized()

    def mousePressEvent(self, event) -> None:
        if event.button() != Qt.MouseButton.LeftButton:
            super().mousePressEvent(event)
            return

        host = self._host()
        global_pos = event.globalPosition().toPoint()

        if host.isMaximized():
            normal = host.normalGeometry()
            ratio = event.position().x() / max(self.width(), 1)
            host.showNormal()
            new_x = global_pos.x() - int(normal.width() * ratio)
            new_y = global_pos.y() - int(event.position().y())
            host.move(new_x, new_y)

        self._drag_offset = global_pos - host.pos()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:
        if (
            event.buttons() & Qt.MouseButton.LeftButton
            and self._drag_offset is not None
        ):
            host = self._host()
            if not host.isMaximized():
                host.move(event.globalPosition().toPoint() - self._drag_offset)
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:
        self._drag_offset = None
        super().mouseReleaseEvent(event)

    def mouseDoubleClickEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._on_toggle_maximize()
        super().mouseDoubleClickEvent(event)
