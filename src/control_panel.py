"""Main Qt control panel for spell configuration and casting."""

from __future__ import annotations

from typing import List, Optional

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QKeySequence, QShortcut
from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFormLayout,
    QFrame,
    QGroupBox,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QRadioButton,
    QScrollArea,
    QSlider,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from .assets import list_sigils
from .models import SignDirection, SignSlot, SpellConfig
from .mouse_drawer import (
    DEFAULT_POINT_DELAY_S,
    SHAKE_DEFAULT_PCT,
    SHAKE_MAX_PCT,
    SHAKE_MIN_PCT,
    DrawWorker,
    shake_amplitude_from_percent,
)
from .overlay_window import OverlayWindow
from .spell_composer import compose_spell
from .ui.cast_key_filter import enable_cast_key_on_spinboxes
from .ui.sign_preview import populate_sign_combo
from .ui.spin_input import SpinInput
from .ui.theme import BG_ELEVATED

SPEED_MIN_S = 0.0
SPEED_MAX_S = 1.0
SPEED_STEP_S = 0.01
SPEED_SLIDER_STEPS = int(SPEED_MAX_S / SPEED_STEP_S)
SCALE_MIN_PCT = 10
SCALE_MAX_PCT = 200
DEFAULT_SCALE_PCT = 100
SIGNS_SCROLL_MAX_HEIGHT = 168


def _make_percent_spin(tooltip: str) -> tuple[QSpinBox, SpinInput]:
    """
    Build a compact percent spin box with step buttons.

    Parameters
    ----------
    tooltip : str
        Widget tooltip text.

    Returns
    -------
    tuple of (QSpinBox, SpinInput)
        Raw spin box and wrapped input widget.
    """
    spin = QSpinBox()
    spin.setRange(SCALE_MIN_PCT, SCALE_MAX_PCT)
    spin.setSuffix("%")
    spin.setValue(DEFAULT_SCALE_PCT)
    spin.setToolTip(tooltip)
    spin.setFixedWidth(72)
    return spin, SpinInput(spin)


class SignSlotWidget(QWidget):
    """Single sign row: index, type, direction, rotation, and size."""

    def __init__(self, index: int, parent: Optional[QWidget] = None) -> None:
        """
        Build one sign configuration row.

        Parameters
        ----------
        index : int
            Zero-based sign index for the label.
        parent : QWidget, optional
            Qt parent widget.
        """
        super().__init__(parent)
        self._index = index

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        index_label = QLabel(f"#{index + 1}")
        index_label.setFixedWidth(26)
        index_label.setObjectName("SignIndexLabel")

        self.type_combo = QComboBox()
        self.type_combo.setMinimumWidth(100)
        populate_sign_combo(self.type_combo)

        self.inward_radio = QRadioButton("In")
        self.outward_radio = QRadioButton("Out")
        self.inward_radio.setChecked(True)
        self.inward_radio.setToolTip("Face toward the circle center")
        self.outward_radio.setToolTip("Face away from the circle center")

        self.rotation_spin = QSpinBox()
        self.rotation_spin.setRange(-90, 90)
        self.rotation_spin.setSuffix("°")
        self.rotation_spin.setToolTip("Extra rotation (-90° to 90°)")
        self.rotation_spin.setFixedWidth(72)
        self.rotation_input = SpinInput(self.rotation_spin)

        self.scale_spin, self.scale_input = _make_percent_spin(
            "Sign size (10% to 200%)"
        )

        layout.addWidget(index_label)
        layout.addWidget(self.type_combo, stretch=1)
        layout.addWidget(self.inward_radio)
        layout.addWidget(self.outward_radio)
        layout.addWidget(self.rotation_input)
        layout.addWidget(self.scale_input)

    def to_slot(self) -> SignSlot:
        """
        Read the current UI state as a ``SignSlot``.

        Returns
        -------
        SignSlot
            Selected sign type, direction, rotation, and size.
        """
        return SignSlot(
            sign_type=str(self.type_combo.currentData()),
            direction=(
                SignDirection.INWARD
                if self.inward_radio.isChecked()
                else SignDirection.OUTWARD
            ),
            rotation_deg=float(self.rotation_spin.value()),
            scale_pct=float(self.scale_spin.value()),
        )

    def set_slot(self, slot: SignSlot) -> None:
        """
        Populate the row from a ``SignSlot``.

        Parameters
        ----------
        slot : SignSlot
            Values to display.

        Returns
        -------
        None
        """
        idx = self.type_combo.findData(slot.sign_type)
        if idx >= 0:
            self.type_combo.setCurrentIndex(idx)
        if slot.direction == SignDirection.INWARD:
            self.inward_radio.setChecked(True)
        else:
            self.outward_radio.setChecked(True)
        self.rotation_spin.setValue(int(round(slot.rotation_deg)))
        self.scale_spin.setValue(
            int(round(max(SCALE_MIN_PCT, min(SCALE_MAX_PCT, slot.scale_pct))))
        )

    def set_rotation(self, degrees: float) -> None:
        """
        Set the rotation spinbox to ``degrees``.

        Parameters
        ----------
        degrees : float
            Rotation in degrees (-90 to 90).

        Returns
        -------
        None
        """
        self.rotation_spin.setValue(int(round(max(-90, min(90, degrees)))))

    def set_scale(self, percent: float) -> None:
        """
        Set the size spinbox to ``percent``.

        Parameters
        ----------
        percent : float
            Size percent (10 to 200).

        Returns
        -------
        None
        """
        self.scale_spin.setValue(
            int(round(max(SCALE_MIN_PCT, min(SCALE_MAX_PCT, percent))))
        )


class ControlPanel(QWidget):
    """Main configuration window for spell casting."""

    def __init__(self) -> None:
        """
        Initialize the control panel, overlay, and signal wiring.

        Returns
        -------
        None
        """
        super().__init__()
        self._config = SpellConfig()
        self._sign_widgets: List[SignSlotWidget] = []
        self._overlay = OverlayWindow()
        self._worker: Optional[DrawWorker] = None

        self._build_ui()
        self._rebuild_sign_widgets()
        self._escape_shortcut = QShortcut(QKeySequence(Qt.Key.Key_Escape), self)
        self._escape_shortcut.setContext(Qt.ShortcutContext.ApplicationShortcut)
        self._escape_shortcut.activated.connect(self._on_escape_cancel)
        self._cast_shortcut = QShortcut(QKeySequence("C"), self)
        self._cast_shortcut.setContext(Qt.ShortcutContext.ApplicationShortcut)
        self._cast_shortcut.activated.connect(self._cast)
        self._overlay.center_moved.connect(self._on_overlay_moved)
        self._overlay.diameter_changed.connect(self._on_diameter_changed)
        self._overlay.rotation_changed.connect(self._on_overlay_rotation_changed)
        self.sigil_combo.currentIndexChanged.connect(self._refresh_overlay_if_visible)
        self.sign_count_spin.valueChanged.connect(self._refresh_overlay_if_visible)

    def _build_ui(self) -> None:
        """
        Construct all widgets and layouts.

        Returns
        -------
        None
        """
        root = QVBoxLayout(self)
        root.setContentsMargins(18, 16, 18, 18)
        root.setSpacing(12)

        form = QFormLayout()
        form.setSpacing(10)

        self.sigil_combo = QComboBox()
        for name in list_sigils():
            self.sigil_combo.addItem(name, name)
        form.addRow("Sigil:", self.sigil_combo)

        self.sigil_scale_spin, self.sigil_scale_input = _make_percent_spin(
            "Sigil size relative to default (10% to 200%)"
        )
        self.sigil_scale_spin.valueChanged.connect(self._refresh_overlay_if_visible)
        form.addRow("Sigil size:", self.sigil_scale_input)

        self.sign_count_spin = QSpinBox()
        self.sign_count_spin.setRange(1, 12)
        self.sign_count_spin.setValue(4)
        self.sign_count_spin.valueChanged.connect(self._on_sign_count_changed)
        self.sign_count_input = SpinInput(self.sign_count_spin)
        form.addRow("Number of signs:", self.sign_count_input)

        self.diameter_label = QLabel(f"{self._config.circle_diameter_px} px")
        form.addRow("Circle diameter:", self.diameter_label)

        self.spell_rotation_label = QLabel(f"{self._config.overlay_rotation_deg:.0f}°")
        form.addRow("Spell rotation:", self.spell_rotation_label)

        root.addLayout(form)

        speed_row = QWidget()
        speed_layout = QHBoxLayout(speed_row)
        speed_layout.setContentsMargins(0, 0, 0, 0)
        speed_layout.setSpacing(10)

        self.speed_slider = QSlider(Qt.Orientation.Horizontal)
        self.speed_slider.setRange(0, SPEED_SLIDER_STEPS)
        self.speed_slider.setSingleStep(1)
        self.speed_slider.setPageStep(10)
        self.speed_slider.setToolTip(
            "0 = turbo (~1 ms/pt), 0.01 = normal (~6 ms/pt), 0.02+ = slower"
        )

        self.speed_spin = QDoubleSpinBox()
        self.speed_spin.setRange(SPEED_MIN_S, SPEED_MAX_S)
        self.speed_spin.setSingleStep(SPEED_STEP_S)
        self.speed_spin.setDecimals(2)
        self.speed_spin.setSpecialValueText("max")
        self.speed_spin.setSuffix(" s/pt")
        self.speed_spin.setFixedWidth(88)
        self.speed_spin.setToolTip(self.speed_slider.toolTip())
        self.speed_spin_input = SpinInput(self.speed_spin)

        self._set_speed_value(DEFAULT_POINT_DELAY_S)
        self.speed_slider.valueChanged.connect(self._on_speed_slider_changed)
        self.speed_spin.valueChanged.connect(self._on_speed_spin_changed)

        speed_layout.addWidget(self.speed_slider, stretch=1)
        speed_layout.addWidget(self.speed_spin_input)
        form.addRow("Draw speed:", speed_row)

        shake_row = QWidget()
        shake_layout = QHBoxLayout(shake_row)
        shake_layout.setContentsMargins(0, 0, 0, 0)
        shake_layout.setSpacing(8)
        self.shake_check = QCheckBox("Shake")
        self.shake_check.setToolTip("Add a subtle hand tremor while drawing")
        self.shake_spin = QSpinBox()
        self.shake_spin.setRange(SHAKE_MIN_PCT, SHAKE_MAX_PCT)
        self.shake_spin.setSuffix("%")
        self.shake_spin.setValue(SHAKE_DEFAULT_PCT)
        self.shake_spin.setToolTip(f"Shake intensity ({SHAKE_MIN_PCT}% to {SHAKE_MAX_PCT}%)")
        self.shake_spin.setFixedWidth(72)
        self.shake_input = SpinInput(self.shake_spin)
        self.shake_check.toggled.connect(self._on_shake_toggled)
        shake_layout.addWidget(self.shake_check)
        shake_layout.addWidget(self.shake_input)
        shake_layout.addStretch()
        form.addRow("Hand tremor:", shake_row)
        self._on_shake_toggled(self.shake_check.isChecked())

        draw_group = QGroupBox("Draw components")
        draw_layout = QVBoxLayout(draw_group)
        self.draw_sigil_check = QCheckBox("Sigil")
        self.draw_signs_check = QCheckBox("Signs")
        self.draw_circle_check = QCheckBox("Circle")
        self.close_circle_check = QCheckBox("Close circle (complete spell)")
        for box in (
            self.draw_sigil_check,
            self.draw_signs_check,
            self.draw_circle_check,
            self.close_circle_check,
        ):
            box.setChecked(True)
        self.close_circle_check.setToolTip(
            "Draw the final circle segment to complete the spell"
        )
        self.draw_circle_check.toggled.connect(self._on_draw_circle_toggled)
        for box in (
            self.draw_sigil_check,
            self.draw_signs_check,
            self.draw_circle_check,
            self.close_circle_check,
        ):
            box.toggled.connect(self._refresh_overlay_if_visible)
        draw_layout.addWidget(self.draw_sigil_check)
        draw_layout.addWidget(self.draw_signs_check)
        draw_layout.addWidget(self.draw_circle_check)
        draw_layout.addWidget(self.close_circle_check)
        self._on_draw_circle_toggled(self.draw_circle_check.isChecked())
        root.addWidget(draw_group)

        signs_group = QGroupBox("Signs")
        signs_layout = QVBoxLayout(signs_group)

        self.signs_scroll = QScrollArea()
        self.signs_scroll.setObjectName("SignsScroll")
        self.signs_scroll.setWidgetResizable(True)
        self.signs_scroll.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        self.signs_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.signs_scroll.setMaximumHeight(SIGNS_SCROLL_MAX_HEIGHT)
        self.signs_scroll.viewport().setStyleSheet(
            f"background-color: {BG_ELEVATED};"
        )

        self._signs_inner = QWidget()
        self._signs_inner.setObjectName("SignsScrollContent")
        self.signs_container = QVBoxLayout(self._signs_inner)
        self.signs_container.setContentsMargins(0, 0, 4, 0)
        self.signs_container.setSpacing(6)
        self.signs_scroll.setWidget(self._signs_inner)
        signs_layout.addWidget(self.signs_scroll)

        bulk_separator = QFrame()
        bulk_separator.setObjectName("BulkSeparator")
        bulk_separator.setFrameShape(QFrame.Shape.HLine)
        bulk_separator.setFrameShadow(QFrame.Shadow.Plain)
        signs_layout.addWidget(bulk_separator)

        bulk_title = QLabel("Apply to all signs")
        bulk_title.setObjectName("SectionTitle")
        signs_layout.addWidget(bulk_title)

        bulk_grid = QGridLayout()
        bulk_grid.setHorizontalSpacing(8)
        bulk_grid.setVerticalSpacing(8)
        label_align = (
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        )
        input_align = Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter

        rot_label = QLabel("Rotation")
        rot_label.setObjectName("FormLabel")
        self.apply_all_rotation_spin = QSpinBox()
        self.apply_all_rotation_spin.setRange(-90, 90)
        self.apply_all_rotation_spin.setSuffix("°")
        self.apply_all_rotation_spin.setValue(0)
        self.apply_all_rotation_spin.setToolTip("Rotation applied to every sign")
        self.apply_all_rotation_spin.setFixedWidth(72)
        self.apply_all_rotation_input = SpinInput(self.apply_all_rotation_spin)
        self.apply_all_rotations_btn = QPushButton("Apply")
        self.apply_all_rotations_btn.setObjectName("GhostButton")
        self.apply_all_rotations_btn.setToolTip(
            "Set this rotation on every sign (-90° to 90°)"
        )
        self.apply_all_rotations_btn.clicked.connect(self._apply_rotation_to_all_signs)

        size_label = QLabel("Size")
        size_label.setObjectName("FormLabel")
        self.apply_all_scale_spin, self.apply_all_scale_input = _make_percent_spin(
            "Size applied to every sign (10% to 200%)"
        )
        self.apply_all_scales_btn = QPushButton("Apply")
        self.apply_all_scales_btn.setObjectName("GhostButton")
        self.apply_all_scales_btn.setToolTip(
            "Set this size on every sign (10% to 200%)"
        )
        self.apply_all_scales_btn.clicked.connect(self._apply_scale_to_all_signs)

        bulk_grid.addWidget(rot_label, 0, 0, alignment=label_align)
        bulk_grid.addWidget(self.apply_all_rotation_input, 0, 1, alignment=input_align)
        bulk_grid.addWidget(self.apply_all_rotations_btn, 0, 2, alignment=input_align)
        bulk_grid.addWidget(size_label, 1, 0, alignment=label_align)
        bulk_grid.addWidget(self.apply_all_scale_input, 1, 1, alignment=input_align)
        bulk_grid.addWidget(self.apply_all_scales_btn, 1, 2, alignment=input_align)
        bulk_grid.setColumnStretch(2, 1)
        signs_layout.addLayout(bulk_grid)

        root.addWidget(signs_group)

        overlay_info = QWidget()
        overlay_info_layout = QVBoxLayout(overlay_info)
        overlay_info_layout.setContentsMargins(0, 0, 0, 0)
        overlay_info_layout.setSpacing(6)
        self.center_label = QLabel("Overlay center: —")
        self.cast_countdown_check = QCheckBox("Cast countdown (3s)")
        self.cast_countdown_check.setChecked(True)
        self.cast_countdown_check.setToolTip(
            "Wait 3 seconds after casting before the draw starts"
        )
        overlay_info_layout.addWidget(self.center_label)
        overlay_info_layout.addWidget(self.cast_countdown_check)
        root.addWidget(overlay_info)

        hint = QLabel(
            "Tip: drag the overlay to move it; white handle (top) resizes; "
            "amber handle (right) rotates the whole spell."
        )
        hint.setObjectName("HintLabel")
        hint.setWordWrap(True)
        root.addWidget(hint)

        self.status_label = QLabel("Ready.")
        self.status_label.setObjectName("StatusLabel")
        self.status_label.setWordWrap(True)
        root.addWidget(self.status_label)

        self.overlay_toggle = QCheckBox("Targeting overlay")
        self.overlay_toggle.setToolTip("Show or hide the targeting overlay")
        self.overlay_toggle.toggled.connect(self._on_overlay_toggled)
        root.addWidget(self.overlay_toggle)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(10)
        self.cast_btn = QPushButton("Cast spell (C)")
        self.cast_btn.setObjectName("PrimaryButton")
        self.cast_btn.setToolTip("Start drawing the spell (C)")
        self.cast_btn.clicked.connect(self._cast)
        self.cancel_btn = QPushButton("Cancel")
        self.cancel_btn.setObjectName("GhostButton")
        self.cancel_btn.clicked.connect(self._cancel_draw)
        self.cancel_btn.setEnabled(False)
        btn_row.addWidget(self.cast_btn, stretch=1)
        btn_row.addWidget(self.cancel_btn, stretch=1)
        root.addLayout(btn_row)

        bottom_row = QHBoxLayout()
        bottom_row.setSpacing(16)
        self.dry_run_check = QCheckBox("Debug mode (no mouse)")
        self.always_on_top_check = QCheckBox("Always on top")
        self.always_on_top_check.setToolTip("Keep this window above other applications")
        self.always_on_top_check.toggled.connect(self._on_always_on_top_toggled)
        bottom_row.addWidget(self.dry_run_check)
        bottom_row.addWidget(self.always_on_top_check)
        bottom_row.addStretch(1)
        root.addLayout(bottom_row)

    def _on_always_on_top_toggled(self, enabled: bool) -> None:
        """
        Toggle ``WindowStaysOnTopHint`` on the host window.

        Parameters
        ----------
        enabled : bool
            ``True`` to keep the caster above other windows.

        Returns
        -------
        None
        """
        window = self.window()
        flags = window.windowFlags()
        if enabled:
            flags |= Qt.WindowType.WindowStaysOnTopHint
        else:
            flags &= ~Qt.WindowType.WindowStaysOnTopHint
        window.setWindowFlags(flags)
        window.show()

    def _set_speed_value(self, delay_s: float) -> None:
        """
        Set draw speed on slider and spinbox without signal loops.

        Parameters
        ----------
        delay_s : float
            Point delay in seconds (0 = max speed).

        Returns
        -------
        None
        """
        delay_s = max(SPEED_MIN_S, min(SPEED_MAX_S, delay_s))
        slider_value = round(delay_s / SPEED_STEP_S)
        self.speed_slider.blockSignals(True)
        self.speed_spin.blockSignals(True)
        self.speed_slider.setValue(slider_value)
        self.speed_spin.setValue(delay_s)
        self.speed_spin.blockSignals(False)
        self.speed_slider.blockSignals(False)

    def _on_speed_slider_changed(self, slider_value: int) -> None:
        """
        Mirror slider movement to the precision spinbox.

        Parameters
        ----------
        slider_value : int
            Slider position (0 = max speed, 100 = 1.00 s/pt).

        Returns
        -------
        None
        """
        delay_s = slider_value * SPEED_STEP_S
        self.speed_spin.blockSignals(True)
        self.speed_spin.setValue(delay_s)
        self.speed_spin.blockSignals(False)

    def _on_shake_toggled(self, enabled: bool) -> None:
        self.shake_spin.setEnabled(enabled)

    def _shake_amplitude_px(self) -> float:
        if not self.shake_check.isChecked():
            return 0.0
        return shake_amplitude_from_percent(float(self.shake_spin.value()))

    def _on_speed_spin_changed(self, delay_s: float) -> None:
        """
        Mirror spinbox edits to the slider.

        Parameters
        ----------
        delay_s : float
            Point delay in seconds.

        Returns
        -------
        None
        """
        slider_value = round(delay_s / SPEED_STEP_S)
        self.speed_slider.blockSignals(True)
        self.speed_slider.setValue(slider_value)
        self.speed_slider.blockSignals(False)

    def _on_draw_circle_toggled(self, enabled: bool) -> None:
        """
        Enable or disable the close-circle option with the circle toggle.

        Parameters
        ----------
        enabled : bool
            Whether the circle component is included.

        Returns
        -------
        None
        """
        self.close_circle_check.setEnabled(enabled)
        if not enabled:
            self.close_circle_check.setChecked(False)

    def _on_sign_count_changed(self, _value: int) -> None:
        """
        Rebuild sign rows when the sign count spinbox changes.

        Parameters
        ----------
        _value : int
            New sign count (unused).

        Returns
        -------
        None
        """
        self._rebuild_sign_widgets()

    def _rebuild_sign_widgets(self) -> None:
        """
        Create one ``SignSlotWidget`` per current sign count.

        Returns
        -------
        None
        """
        while self.signs_container.count():
            item = self.signs_container.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self._sign_widgets.clear()

        count = self.sign_count_spin.value()
        for i in range(count):
            widget = SignSlotWidget(i)
            if i < len(self._config.signs):
                widget.set_slot(self._config.signs[i])
            self._sign_widgets.append(widget)
            self.signs_container.addWidget(widget)
            widget.type_combo.currentIndexChanged.connect(
                self._refresh_overlay_if_visible
            )
            widget.inward_radio.toggled.connect(self._refresh_overlay_if_visible)
            widget.rotation_spin.valueChanged.connect(self._refresh_overlay_if_visible)
            widget.scale_spin.valueChanged.connect(self._refresh_overlay_if_visible)

        enable_cast_key_on_spinboxes(self, self._cast)

    def _apply_rotation_to_all_signs(self) -> None:
        """
        Apply the bulk rotation input to every sign row.

        Returns
        -------
        None
        """
        degrees = float(self.apply_all_rotation_spin.value())
        for widget in self._sign_widgets:
            widget.set_rotation(degrees)
        self._refresh_overlay_if_visible()

    def _apply_scale_to_all_signs(self) -> None:
        """
        Apply the bulk size input to every sign row.

        Returns
        -------
        None
        """
        percent = float(self.apply_all_scale_spin.value())
        for widget in self._sign_widgets:
            widget.set_scale(percent)
        self._refresh_overlay_if_visible()

    def _collect_config(self) -> SpellConfig:
        """
        Snapshot UI fields into ``SpellConfig``.

        Returns
        -------
        SpellConfig
            Current spell configuration including overlay geometry when visible.
        """
        self._config.sigil = self.sigil_combo.currentData()
        self._config.sigil_scale_pct = float(self.sigil_scale_spin.value())
        self._config.sign_count = self.sign_count_spin.value()
        if self._overlay.isVisible():
            self._config.overlay_center = self._overlay.center()
            self._config.circle_diameter_px = self._overlay.diameter()
            self._config.overlay_rotation_deg = self._overlay.rotation()
        self._config.signs = [w.to_slot() for w in self._sign_widgets]
        self._config.draw_sigil = self.draw_sigil_check.isChecked()
        self._config.draw_signs = self.draw_signs_check.isChecked()
        self._config.draw_circle = self.draw_circle_check.isChecked()
        self._config.close_circle = self.close_circle_check.isChecked()
        self._config.cast_countdown = self.cast_countdown_check.isChecked()
        self._config.ensure_signs()
        return self._config

    def _on_overlay_toggled(self, enabled: bool) -> None:
        """
        Show or hide the targeting overlay.

        Parameters
        ----------
        enabled : bool
            ``True`` to show the overlay.

        Returns
        -------
        None
        """
        if enabled:
            self._sync_overlay()
            self.status_label.setText("Overlay shown — drag it over the draw area.")
        else:
            self._overlay.hide()
            self.status_label.setText("Overlay hidden.")

    def _sync_overlay(self) -> None:
        """
        Push current config to the overlay and display it.

        Returns
        -------
        None
        """
        config = self._collect_config()
        self._overlay.update_spell(config)
        self._overlay.show()
        cx, cy = self._overlay.center()
        self.center_label.setText(f"Overlay center: ({cx:.0f}, {cy:.0f})")
        self.diameter_label.setText(f"{self._overlay.diameter()} px")
        self.spell_rotation_label.setText(f"{self._overlay.rotation():.0f}°")

    def _refresh_overlay_if_visible(self) -> None:
        """
        Update the overlay preview when settings change.

        Returns
        -------
        None
        """
        if self.overlay_toggle.isChecked() and not (
            self._worker and self._worker.isRunning()
        ):
            self._sync_overlay()

    def _on_overlay_moved(self, cx: float, cy: float) -> None:
        """
        Update the center label when the overlay is dragged.

        Parameters
        ----------
        cx, cy : float
            New overlay center in screen coordinates.

        Returns
        -------
        None
        """
        self.center_label.setText(f"Overlay center: ({cx:.0f}, {cy:.0f})")

    def _on_diameter_changed(self, diameter: int) -> None:
        """
        Update the diameter label when the overlay is resized.

        Parameters
        ----------
        diameter : int
            New circle diameter in pixels.

        Returns
        -------
        None
        """
        self.diameter_label.setText(f"{diameter} px")
        self._config.circle_diameter_px = diameter

    def _on_overlay_rotation_changed(self, degrees: float) -> None:
        """
        Update the rotation label when the overlay is rotated.

        Parameters
        ----------
        degrees : float
            Whole-spell rotation in degrees.

        Returns
        -------
        None
        """
        self._config.overlay_rotation_deg = degrees
        self.spell_rotation_label.setText(f"{degrees:.0f}°")

    def _cast(self) -> None:
        """
        Start the spell draw sequence in a background thread.

        Returns
        -------
        None
        """
        if self._worker and self._worker.isRunning():
            return

        config = self._collect_config()

        self.overlay_toggle.blockSignals(True)
        self.overlay_toggle.setChecked(False)
        self.overlay_toggle.blockSignals(False)
        self._overlay.hide()

        if not (config.draw_sigil or config.draw_signs or config.draw_circle):
            QMessageBox.warning(
                self,
                "Error",
                "Select at least one component to draw (sigil, signs, or circle).",
            )
            return

        plan = compose_spell(config)
        if not plan.strokes:
            QMessageBox.warning(self, "Error", "No strokes to draw.")
            return

        self._worker = DrawWorker(plan)
        self._worker.dry_run = self.dry_run_check.isChecked()
        self._worker.cast_countdown = config.cast_countdown
        self._worker.set_point_delay(self.speed_spin.value())
        self._worker.set_shake_amplitude(self._shake_amplitude_px())
        self._worker.progress.connect(self.status_label.setText)
        self._worker.finished_ok.connect(self._on_draw_finished)
        self._worker.finished_cancelled.connect(self._on_draw_cancelled)
        self._worker.error.connect(self._on_draw_error)

        self.cast_btn.setEnabled(False)
        self._cast_shortcut.setEnabled(False)
        self.overlay_toggle.setEnabled(False)
        self.cancel_btn.setEnabled(True)
        self.status_label.setText("Preparing spell…")
        self._worker.start()

    def _on_escape_cancel(self) -> None:
        """
        Cancel an in-progress cast when Escape is pressed.

        Returns
        -------
        None
        """
        if self._worker and self._worker.isRunning():
            self._cancel_draw()

    def _cancel_draw(self) -> None:
        """
        Cancel the running draw worker.

        Returns
        -------
        None
        """
        if self._worker:
            self._worker.cancel()

    def _on_draw_finished(self) -> None:
        """
        Handle successful spell completion.

        Returns
        -------
        None
        """
        self._reset_draw_ui()
        self.status_label.setText("Spell complete.")

    def _on_draw_cancelled(self) -> None:
        """
        Handle user-cancelled spell drawing.

        Returns
        -------
        None
        """
        self._reset_draw_ui()
        self.status_label.setText("Spell cancelled.")

    def _on_draw_error(self, message: str) -> None:
        """
        Handle draw worker errors.

        Parameters
        ----------
        message : str
            Error description.

        Returns
        -------
        None
        """
        self._reset_draw_ui()
        QMessageBox.critical(self, "Error", message)
        self.status_label.setText(f"Error: {message}")

    def _reset_draw_ui(self) -> None:
        """
        Re-enable controls after a draw finishes or is cancelled.

        Returns
        -------
        None
        """
        self.cast_btn.setEnabled(True)
        self._cast_shortcut.setEnabled(True)
        self.overlay_toggle.setEnabled(True)
        self.cancel_btn.setEnabled(False)
        self._worker = None
        if self.overlay_toggle.isChecked():
            self._sync_overlay()
