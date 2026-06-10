"""Spin box with external step buttons (reliable on Windows)."""

from __future__ import annotations

from typing import Optional, Union

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QAbstractSpinBox,
    QDoubleSpinBox,
    QHBoxLayout,
    QSpinBox,
    QToolButton,
    QVBoxLayout,
    QWidget,
)


class SpinInput(QWidget):
    """Horizontal spin field with dedicated up/down controls on the right."""

    def __init__(
        self,
        spin: Union[QSpinBox, QDoubleSpinBox],
        parent: Optional[QWidget] = None,
    ) -> None:
        """
        Wrap a spin box and hide its built-in arrow sub-controls.

        Parameters
        ----------
        spin : QSpinBox or QDoubleSpinBox
            Underlying value editor.
        parent : QWidget, optional
            Parent widget.
        """
        super().__init__(parent)
        self._spin = spin
        self._spin.setButtonSymbols(QAbstractSpinBox.ButtonSymbols.NoButtons)

        root = QHBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        self._spin.setStyleSheet(
            "QSpinBox, QDoubleSpinBox {"
            "  border-top-right-radius: 0;"
            "  border-bottom-right-radius: 0;"
            "  padding-right: 8px;"
            "  color: palette(text);"
            "  background-color: palette(base);"
            "}"
        )

        root.addWidget(self._spin, stretch=1)

        step_col = QVBoxLayout()
        step_col.setContentsMargins(0, 0, 0, 0)
        step_col.setSpacing(0)

        self._up = QToolButton()
        self._down = QToolButton()
        self._up.setObjectName("SpinStepButtonUp")
        self._down.setObjectName("SpinStepButtonDown")
        for button, slot in ((self._up, self._spin.stepUp), (self._down, self._spin.stepDown)):
            button.setFixedSize(22, 15)
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            button.clicked.connect(slot)

        self._up.setArrowType(Qt.ArrowType.UpArrow)
        self._down.setArrowType(Qt.ArrowType.DownArrow)

        step_col.addWidget(self._up)
        step_col.addWidget(self._down)
        root.addLayout(step_col)

        button_col_w = self._up.width()
        spin_w = self._spin.width()
        if self._spin.minimumWidth() == self._spin.maximumWidth() and spin_w > 0:
            self.setFixedWidth(spin_w + button_col_w)
        self.setFixedHeight(max(self._spin.sizeHint().height(), 30))

    def spin_box(self) -> Union[QSpinBox, QDoubleSpinBox]:
        """
        Return the wrapped spin box.

        Returns
        -------
        QSpinBox or QDoubleSpinBox
            Underlying editor widget.
        """
        return self._spin
