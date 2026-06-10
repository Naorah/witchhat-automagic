"""Allow cast on ``C`` while a spin box has keyboard focus."""

from __future__ import annotations

from typing import Callable

from PyQt6.QtCore import QEvent, QObject, Qt
from PyQt6.QtWidgets import QAbstractSpinBox, QWidget


def enable_cast_key_on_spinboxes(root: QWidget, cast_fn: Callable[[], None]) -> None:
    """
    Intercept unmodified ``C`` key presses inside spin boxes.

    Parameters
    ----------
    root : QWidget
        Container whose ``QAbstractSpinBox`` descendants are wired.
    cast_fn : callable
        Cast handler invoked when ``C`` is pressed in a spin field.

    Returns
    -------
    None
    """
    class _CastKeyFilter(QObject):
        def eventFilter(self, watched, event) -> bool:  # noqa: N802
            if (
                event.type() == QEvent.Type.KeyPress
                and event.key() == Qt.Key.Key_C
                and event.modifiers() == Qt.KeyboardModifier.NoModifier
                and not event.isAutoRepeat()
            ):
                cast_fn()
                return True
            return super().eventFilter(watched, event)

    filt = _CastKeyFilter(root)
    for spin in root.findChildren(QAbstractSpinBox):
        spin.installEventFilter(filt)
    root._cast_key_filter = filt  # prevent GC
