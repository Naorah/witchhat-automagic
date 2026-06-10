#!/usr/bin/env python3
"""
Cast speed limit calibrator — binary search with user feedback.

Usage:
    python speed-calibrator/main.py
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

CAL_DIR = Path(__file__).resolve().parent
if str(CAL_DIR) not in sys.path:
    sys.path.insert(0, str(CAL_DIR))

from PyQt6.QtWidgets import QApplication

from panel import CalibratorPanel
from src.ui.frameless_shell import FramelessShell
from src.ui.theme import apply_app_theme


def main() -> None:
    """
    Launch the speed calibrator in a frameless shell window.

    Returns
    -------
    None
    """
    app = QApplication(sys.argv)
    apply_app_theme(app)

    panel = CalibratorPanel()
    window = FramelessShell(
        "Speed Calibrator",
        panel,
        min_width=460,
        min_height=620,
        initial_size=(500, 680),
    )
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
