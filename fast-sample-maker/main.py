#!/usr/bin/env python3
"""
Fast sample maker — quick sigil/sign picker with overlay preview.

Usage:
    python fast-sample-maker/main.py
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

FAST_DIR = Path(__file__).resolve().parent
if str(FAST_DIR) not in sys.path:
    sys.path.insert(0, str(FAST_DIR))

from PyQt6.QtWidgets import QApplication

from panel import FastSamplePanel
from src.ui.frameless_shell import FramelessShell
from src.ui.theme import apply_app_theme


def main() -> None:
    """
    Launch the fast sample maker in a frameless shell window.

    Returns
    -------
    None
    """
    app = QApplication(sys.argv)
    apply_app_theme(app)

    panel = FastSamplePanel()
    window = FramelessShell(
        "Fast Sample Maker",
        panel,
        min_width=480,
        min_height=620,
        initial_size=(520, 680),
    )
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
