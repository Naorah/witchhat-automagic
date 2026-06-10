"""Reusable borderless window shell with custom title bar."""

from __future__ import annotations

from typing import Optional, Tuple

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QSizePolicy, QVBoxLayout, QWidget

from .title_bar import TitleBar


class FramelessShell(QWidget):
    """Frameless window wrapping arbitrary central content."""

    def __init__(
        self,
        title: str,
        content: QWidget,
        *,
        min_width: int = 400,
        min_height: int = 520,
        initial_size: Optional[Tuple[int, int]] = None,
    ) -> None:
        """
        Build a borderless shell around ``content``.

        Parameters
        ----------
        title : str
            Title shown in the custom title bar.
        content : QWidget
            Main panel widget.
        min_width, min_height : int, optional
            Minimum window dimensions.
        initial_size : tuple of int, optional
            ``(width, height)`` passed to ``resize`` when set.
        """
        super().__init__()
        self.setObjectName("AppRoot")
        self.setWindowTitle(title)
        self.setWindowFlags(
            Qt.WindowType.Window
            | Qt.WindowType.FramelessWindowHint
        )
        self.setMinimumSize(min_width, min_height)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        self._title_bar = TitleBar(title, self)
        content.setObjectName("ContentPanel")
        content.setSizePolicy(
            QSizePolicy.Policy.Preferred,
            QSizePolicy.Policy.Expanding,
        )

        root.addWidget(self._title_bar)
        root.addWidget(content, stretch=1)

        if initial_size is not None:
            self.resize(initial_size[0], initial_size[1])
