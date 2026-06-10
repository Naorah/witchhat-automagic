"""Application entry point for Witchhat Automagic."""

import sys

from PyQt6.QtWidgets import QApplication

from src.app_window import AppWindow
from src.ui.theme import apply_app_theme


def main() -> None:
    """
    Launch the spell configuration control panel.

    Returns
    -------
    None
    """
    app = QApplication(sys.argv)
    apply_app_theme(app)
    window = AppWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
