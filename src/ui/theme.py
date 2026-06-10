"""Flat parchment theme tokens and application stylesheet."""

from __future__ import annotations

import base64

# Surfaces — warm parchment family (base #f8e5a3)
BG_WINDOW = "#f8e5a3"
BG_TITLEBAR = "#edd88f"
BG_ELEVATED = "#fcecb8"
BG_INPUT = "#fff6d6"
BG_HOVER = "#f3dfa0"
BG_CANVAS = "#e8d4a0"

# List / annotation status
LIST_PENDING = "#b87a3a"
LIST_ANNOTATED = "#9a8868"

# Text — ink on parchment
TEXT_PRIMARY = "#3d3428"
TEXT_SECONDARY = "#6b5d45"
TEXT_MUTED = "#9a8868"

# Accent — warm bronze / amber ink
ACCENT = "#9c6b30"
ACCENT_HOVER = "#b07d3a"
ACCENT_PRESSED = "#865f28"
ACCENT_ON = "#fff8ee"

# Traffic lights (muted, still readable on parchment)
TL_CLOSE = "#d96a5c"
TL_CLOSE_HOVER = "#e47d70"
TL_MINIMIZE = "#c9a03a"
TL_MINIMIZE_HOVER = "#d9b04e"
TL_MAXIMIZE = "#5fa862"
TL_MAXIMIZE_HOVER = "#72bb74"

BORDER_SUBTLE = "#d4c48a"
BORDER_HOVER = "#b8a66a"
SLIDER_HANDLE = "#fff8e8"
RADIUS = "8px"
RADIUS_SM = "6px"

_SPIN_ARROW_UP = base64.b64encode(
    b'<svg xmlns="http://www.w3.org/2000/svg" width="10" height="6">'
    b'<polygon points="5,0 10,6 0,6" fill="#6b5d45"/></svg>'
).decode("ascii")
_SPIN_ARROW_DOWN = base64.b64encode(
    b'<svg xmlns="http://www.w3.org/2000/svg" width="10" height="6">'
    b'<polygon points="0,0 10,0 5,6" fill="#6b5d45"/></svg>'
).decode("ascii")
SPIN_ARROW_UP = f"url(data:image/svg+xml;base64,{_SPIN_ARROW_UP})"
SPIN_ARROW_DOWN = f"url(data:image/svg+xml;base64,{_SPIN_ARROW_DOWN})"


def apply_app_theme(app) -> None:
    """
    Apply parchment palette and global stylesheet to the application.

    Parameters
    ----------
    app : QApplication
        Running Qt application instance.

    Returns
    -------
    None
    """
    from PyQt6.QtGui import QColor, QPalette
    from PyQt6.QtWidgets import QStyleFactory

    app.setStyle(QStyleFactory.create("Fusion"))

    palette = QPalette()
    window = QColor(BG_WINDOW)
    text = QColor(TEXT_PRIMARY)
    base = QColor(BG_INPUT)
    elevated = QColor(BG_ELEVATED)
    accent = QColor(ACCENT)
    accent_text = QColor(ACCENT_ON)

    palette.setColor(QPalette.ColorRole.Window, window)
    palette.setColor(QPalette.ColorRole.WindowText, text)
    palette.setColor(QPalette.ColorRole.Base, base)
    palette.setColor(QPalette.ColorRole.AlternateBase, elevated)
    palette.setColor(QPalette.ColorRole.ToolTipBase, elevated)
    palette.setColor(QPalette.ColorRole.ToolTipText, text)
    palette.setColor(QPalette.ColorRole.Text, text)
    palette.setColor(QPalette.ColorRole.Button, base)
    palette.setColor(QPalette.ColorRole.ButtonText, text)
    palette.setColor(QPalette.ColorRole.BrightText, text)
    palette.setColor(QPalette.ColorRole.Link, accent)
    palette.setColor(QPalette.ColorRole.Highlight, accent)
    palette.setColor(QPalette.ColorRole.HighlightedText, accent_text)
    palette.setColor(QPalette.ColorRole.PlaceholderText, QColor(TEXT_MUTED))
    palette.setColor(QPalette.ColorRole.Light, QColor(BG_HOVER))
    palette.setColor(QPalette.ColorRole.Midlight, elevated)
    palette.setColor(QPalette.ColorRole.Dark, QColor(BORDER_HOVER))
    palette.setColor(QPalette.ColorRole.Mid, QColor(BORDER_SUBTLE))
    palette.setColor(QPalette.ColorRole.Shadow, QColor(BORDER_HOVER))

    app.setPalette(palette)
    app.setStyleSheet(application_stylesheet())


def application_stylesheet() -> str:
    """
    Return the global Qt stylesheet for the main application window.

    Returns
    -------
    str
        CSS rules for flat parchment styling.
    """
    return f"""
    * {{
        color: {TEXT_PRIMARY};
    }}

    QWidget {{
        color: {TEXT_PRIMARY};
    }}

    QWidget#AppRoot {{
        background-color: {BG_WINDOW};
        color: {TEXT_PRIMARY};
        font-family: "Segoe UI", "Palatino Linotype", "Book Antiqua", sans-serif;
        font-size: 13px;
    }}

    QLabel {{
        color: {TEXT_PRIMARY};
        background-color: transparent;
    }}

    QLineEdit, QAbstractSpinBox {{
        color: {TEXT_PRIMARY};
        background-color: {BG_INPUT};
        selection-background-color: {ACCENT};
        selection-color: {ACCENT_ON};
    }}

    QToolTip {{
        color: {TEXT_PRIMARY};
        background-color: {BG_ELEVATED};
        border: 1px solid {BORDER_SUBTLE};
    }}

    QMessageBox {{
        background-color: {BG_WINDOW};
    }}

    QMessageBox QLabel {{
        color: {TEXT_PRIMARY};
    }}

    QWidget#ContentPanel {{
        background-color: {BG_WINDOW};
    }}

    QLabel#SectionTitle {{
        color: {TEXT_SECONDARY};
        font-size: 11px;
        font-weight: 600;
        letter-spacing: 0.6px;
        padding-top: 4px;
        padding-bottom: 2px;
    }}

    QLabel#HintLabel {{
        color: {TEXT_MUTED};
        font-size: 11px;
    }}

    QLabel#StatusLabel {{
        color: {TEXT_SECONDARY};
        background-color: {BG_ELEVATED};
        border: 1px solid {BORDER_SUBTLE};
        border-radius: {RADIUS_SM};
        padding: 8px 10px;
    }}

    QGroupBox {{
        background-color: {BG_ELEVATED};
        border: 1px solid {BORDER_SUBTLE};
        border-radius: {RADIUS};
        margin-top: 10px;
        padding: 14px 12px 12px 12px;
        font-weight: 600;
        color: {TEXT_SECONDARY};
    }}

    QGroupBox::title {{
        subcontrol-origin: margin;
        left: 10px;
        padding: 0 6px;
    }}

    QComboBox {{
        background-color: {BG_INPUT};
        color: {TEXT_PRIMARY};
        border: 1px solid {BORDER_SUBTLE};
        border-radius: {RADIUS_SM};
        padding: 6px 8px;
        min-height: 18px;
    }}

    QSpinBox, QDoubleSpinBox {{
        background-color: {BG_INPUT};
        color: {TEXT_PRIMARY};
        border: 1px solid {BORDER_SUBTLE};
        border-radius: {RADIUS_SM};
        padding: 4px 26px 4px 8px;
        min-height: 30px;
    }}

    QComboBox:hover, QSpinBox:hover, QDoubleSpinBox:hover {{
        border-color: {BORDER_HOVER};
    }}

    QSpinBox::up-button, QDoubleSpinBox::up-button {{
        subcontrol-origin: border;
        subcontrol-position: top right;
        width: 22px;
        height: 15px;
        border: none;
        border-left: 1px solid {BORDER_SUBTLE};
        border-top-right-radius: {RADIUS_SM};
        background-color: {BG_ELEVATED};
    }}

    QSpinBox::down-button, QDoubleSpinBox::down-button {{
        subcontrol-origin: border;
        subcontrol-position: bottom right;
        width: 22px;
        height: 15px;
        border: none;
        border-left: 1px solid {BORDER_SUBTLE};
        border-bottom-right-radius: {RADIUS_SM};
        background-color: {BG_ELEVATED};
    }}

    QSpinBox::up-button:hover, QDoubleSpinBox::up-button:hover,
    QSpinBox::down-button:hover, QDoubleSpinBox::down-button:hover {{
        background-color: {BG_HOVER};
    }}

    QSpinBox::up-button:pressed, QDoubleSpinBox::up-button:pressed,
    QSpinBox::down-button:pressed, QDoubleSpinBox::down-button:pressed {{
        background-color: {BG_INPUT};
    }}

    QSpinBox::up-arrow, QDoubleSpinBox::up-arrow {{
        image: {SPIN_ARROW_UP};
        width: 10px;
        height: 6px;
    }}

    QSpinBox::down-arrow, QDoubleSpinBox::down-arrow {{
        image: {SPIN_ARROW_DOWN};
        width: 10px;
        height: 6px;
    }}

    QToolButton#SpinStepButtonUp, QToolButton#SpinStepButtonDown {{
        background-color: {BG_ELEVATED};
        border: 1px solid {BORDER_SUBTLE};
        border-left: none;
        border-radius: 0;
        padding: 0;
        color: {TEXT_SECONDARY};
    }}

    QToolButton#SpinStepButtonUp {{
        border-top-right-radius: {RADIUS_SM};
        border-bottom: none;
    }}

    QToolButton#SpinStepButtonDown {{
        border-bottom-right-radius: {RADIUS_SM};
    }}

    QToolButton#SpinStepButtonUp:hover, QToolButton#SpinStepButtonDown:hover {{
        background-color: {BG_HOVER};
        color: {TEXT_PRIMARY};
    }}

    QToolButton#SpinStepButtonUp:pressed, QToolButton#SpinStepButtonDown:pressed {{
        background-color: {BG_INPUT};
    }}

    QComboBox::drop-down {{
        border: none;
        width: 22px;
    }}

    QComboBox QAbstractItemView {{
        background-color: {BG_INPUT};
        color: {TEXT_PRIMARY};
        border: 1px solid {BORDER_SUBTLE};
        selection-background-color: {ACCENT};
        selection-color: {ACCENT_ON};
        outline: none;
    }}

    QComboBox QAbstractItemView::item {{
        min-height: 24px;
        padding: 2px 4px;
    }}

    QCheckBox, QRadioButton {{
        spacing: 8px;
        color: {TEXT_PRIMARY};
    }}

    QCheckBox::indicator, QRadioButton::indicator {{
        width: 16px;
        height: 16px;
        border-radius: 4px;
        border: 1px solid {BORDER_SUBTLE};
        background: {BG_INPUT};
    }}

    QRadioButton::indicator {{
        border-radius: 8px;
    }}

    QCheckBox::indicator:checked, QRadioButton::indicator:checked {{
        background-color: {ACCENT};
        border-color: {ACCENT};
    }}

    QCheckBox:disabled, QRadioButton:disabled {{
        color: {TEXT_MUTED};
    }}

    QCheckBox::indicator:disabled, QRadioButton::indicator:disabled {{
        background: {BG_ELEVATED};
        border-color: {BORDER_SUBTLE};
    }}

    QCheckBox::indicator:checked:disabled, QRadioButton::indicator:checked:disabled {{
        background-color: {BORDER_SUBTLE};
        border-color: {BORDER_SUBTLE};
    }}

    QPushButton {{
        background-color: {BG_INPUT};
        color: {TEXT_PRIMARY};
        border: 1px solid {BORDER_SUBTLE};
        border-radius: {RADIUS_SM};
        padding: 9px 16px;
        font-weight: 500;
    }}

    QPushButton:hover {{
        background-color: {BG_HOVER};
        border-color: {BORDER_HOVER};
    }}

    QPushButton:pressed {{
        background-color: {BG_ELEVATED};
    }}

    QPushButton:disabled {{
        color: {TEXT_MUTED};
        background-color: {BG_ELEVATED};
    }}

    QPushButton#PrimaryButton {{
        background-color: {ACCENT};
        border: none;
        color: {ACCENT_ON};
        font-weight: 600;
    }}

    QPushButton#PrimaryButton:hover {{
        background-color: {ACCENT_HOVER};
    }}

    QPushButton#PrimaryButton:pressed {{
        background-color: {ACCENT_PRESSED};
    }}

    QPushButton#GhostButton {{
        background-color: transparent;
        border: 1px solid {BORDER_SUBTLE};
    }}

    QPushButton#ModeButtonActive {{
        background-color: {ACCENT};
        border: none;
        color: {ACCENT_ON};
        font-weight: 600;
    }}

    QPushButton#ModeButtonActive:hover {{
        background-color: {ACCENT_HOVER};
    }}

    QPushButton#ModeButtonActive:pressed {{
        background-color: {ACCENT_PRESSED};
    }}

    QLabel#PageTitle {{
        font-size: 15px;
        font-weight: 600;
        color: {TEXT_PRIMARY};
    }}

    QLabel#PanelTitle {{
        font-weight: 600;
        color: {TEXT_SECONDARY};
    }}

    QLabel#SignIndexLabel {{
        font-weight: 600;
        color: {TEXT_SECONDARY};
    }}

    QLabel#FormLabel {{
        color: {TEXT_SECONDARY};
        min-width: 52px;
    }}

    QFrame#BulkSeparator {{
        color: {BORDER_SUBTLE};
        background: {BORDER_SUBTLE};
        max-height: 1px;
        margin-top: 10px;
        margin-bottom: 2px;
    }}

    QListWidget {{
        background-color: {BG_INPUT};
        color: {TEXT_PRIMARY};
        border: 1px solid {BORDER_SUBTLE};
        border-radius: {RADIUS_SM};
        padding: 4px;
        outline: none;
    }}

    QListWidget::item {{
        padding: 4px 10px;
        margin: 0;
        border-radius: 3px;
    }}

    QListWidget::item:selected {{
        background-color: {ACCENT};
        color: {ACCENT_ON};
    }}

    QListWidget::item:hover {{
        background-color: {BG_HOVER};
    }}

    QFormLayout QLabel {{
        color: {TEXT_SECONDARY};
    }}

    QScrollArea#SignsScroll {{
        background-color: {BG_ELEVATED};
        border: none;
    }}

    QWidget#SignsScrollContent {{
        background-color: {BG_ELEVATED};
    }}

    QScrollBar:vertical {{
        background: {BG_ELEVATED};
        width: 8px;
        margin: 2px 0;
    }}

    QScrollBar::handle:vertical {{
        background: {BORDER_SUBTLE};
        border-radius: 4px;
        min-height: 24px;
    }}

    QScrollBar::handle:vertical:hover {{
        background: {BORDER_HOVER};
    }}

    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
        height: 0;
    }}

    QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{
        background: {BG_ELEVATED};
    }}

    QSlider::groove:horizontal {{
        height: 6px;
        background: {BG_INPUT};
        border: 1px solid {BORDER_SUBTLE};
        border-radius: 3px;
    }}

    QSlider::sub-page:horizontal {{
        background: {ACCENT};
        border-radius: 3px;
    }}

    QSlider::add-page:horizontal {{
        background: {BG_INPUT};
        border-radius: 3px;
    }}

    QSlider::handle:horizontal {{
        width: 14px;
        height: 14px;
        margin: -5px 0;
        background: {SLIDER_HANDLE};
        border: 1px solid {BORDER_HOVER};
        border-radius: 7px;
    }}

    QSlider::handle:horizontal:hover {{
        background: {BG_INPUT};
        border-color: {ACCENT};
    }}
    """
