"""Borderless main application shell."""

from __future__ import annotations

from .control_panel import ControlPanel
from .ui.frameless_shell import FramelessShell


class AppWindow(FramelessShell):
    """Frameless window with custom title bar and spell control panel."""

    def __init__(self) -> None:
        """
        Build the borderless application window.

        Returns
        -------
        None
        """
        panel = ControlPanel()
        super().__init__(
            "Witchhat Automagic",
            panel,
            min_width=520,
            min_height=520,
        )
        self.adjustSize()
        width = max(self.sizeHint().width(), 560)
        self.resize(width, self.sizeHint().height())
