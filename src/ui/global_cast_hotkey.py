"""System-wide Ctrl+Q hotkey to trigger a cast from any foreground app."""

from __future__ import annotations

from typing import Optional

from PyQt6.QtCore import QObject, pyqtSignal
from pynput import keyboard

CAST_HOTKEY = "<ctrl>+q"


class GlobalCastHotkey(QObject):
    """Listen for Ctrl+Q globally and emit ``triggered`` on the Qt main thread."""

    triggered = pyqtSignal()

    def __init__(self, parent: Optional[QObject] = None) -> None:
        super().__init__(parent)
        self._enabled = True
        self._listener: Optional[keyboard.GlobalHotKeys] = None
        if parent is not None:
            parent.destroyed.connect(self.stop)
        self.start()

    def start(self) -> None:
        """Start the global hotkey listener if it is not already running."""
        if self._listener is not None:
            return
        self._listener = keyboard.GlobalHotKeys({CAST_HOTKEY: self._on_hotkey})
        self._listener.start()

    def stop(self) -> None:
        """Stop the global hotkey listener."""
        if self._listener is None:
            return
        self._listener.stop()
        self._listener = None

    def set_enabled(self, enabled: bool) -> None:
        """Enable or disable hotkey handling without stopping the listener."""
        self._enabled = enabled

    def _on_hotkey(self) -> None:
        if self._enabled:
            self.triggered.emit()
