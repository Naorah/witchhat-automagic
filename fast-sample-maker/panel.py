"""Fast sample maker control panel."""

from __future__ import annotations

import random
from typing import Optional

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QKeySequence, QShortcut
from PyQt6.QtWidgets import (
    QCheckBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from src.mouse_drawer import (
    RANDOM_SHAKE_MAX_PCT,
    RANDOM_SHAKE_MIN_PCT,
    SHAKE_DEFAULT_PCT,
    SHAKE_MAX_PCT,
    SHAKE_MIN_PCT,
    DrawPacing,
    DrawWorker,
    shake_amplitude_from_percent,
)
from src.ui.cast_key_filter import enable_cast_key_on_spinboxes
from src.ui.spin_input import SpinInput

from asset_grid import AssetGrid
from composer import SampleConfig, compose_sample
from overlay import SampleOverlay

SCALE_MIN_PCT = 100
SCALE_MAX_PCT = 500
DEFAULT_SCALE_PCT = 100
RANDOM_SCALE_MIN_PCT = 200
RANDOM_SCALE_MAX_PCT = 400

# Much faster than global TURBO_PLUS_PACING — fast sample maker only.
FAST_SAMPLE_TURBO_PLUS_PACING = DrawPacing(
    point_delay_s=0.00005,
    stroke_delay_s=0.0,
    segment_px=16.0,
    press_settle_s=0.0,
    release_settle_s=0.0,
)


class FastSamplePanel(QWidget):
    """Quick picker for one sigil or sign with overlay preview and draw."""

    def __init__(self) -> None:
        """
        Build the panel, wire signals, and enable cast shortcuts in spinboxes.

        Returns
        -------
        None
        """
        super().__init__()
        self._config = SampleConfig(scale_pct=DEFAULT_SCALE_PCT)
        self._overlay = SampleOverlay()
        self._worker: Optional[DrawWorker] = None
        self._overlay_visible = False
        self._random_rotation_deg: Optional[float] = None
        self._random_scale_pct: Optional[float] = None
        self._random_shake_pct: Optional[float] = None

        self._build_ui()
        self._wire_signals()
        enable_cast_key_on_spinboxes(self, self._cast)

    def _build_ui(self) -> None:
        """Lay out asset grid, settings form, and action buttons."""
        root = QVBoxLayout(self)
        root.setContentsMargins(18, 16, 18, 18)
        root.setSpacing(12)

        hint = QLabel(
            "Pick an asset, position the overlay, then cast to draw."
        )
        hint.setObjectName("HintLabel")
        hint.setWordWrap(True)
        root.addWidget(hint)

        self._grid = AssetGrid()
        self._grid.setMinimumHeight(280)
        root.addWidget(self._grid, stretch=1)

        form = QFormLayout()
        form.setSpacing(10)

        self._selection_label = QLabel("—")
        form.addRow("Selection:", self._selection_label)

        rotation_row = QWidget()
        rotation_layout = QHBoxLayout(rotation_row)
        rotation_layout.setContentsMargins(0, 0, 0, 0)
        rotation_layout.setSpacing(8)

        self._rotation_spin = QSpinBox()
        self._rotation_spin.setRange(-180, 180)
        self._rotation_spin.setSuffix("°")
        self._rotation_spin.setToolTip("Pattern rotation")
        self._rotation_spin.setFixedWidth(80)
        self._rotation_input = SpinInput(self._rotation_spin)

        self._random_rotation_check = QCheckBox("Random rotation")
        self._random_rotation_check.setToolTip(
            "Pick a rotation between 0° and 360° on each cast"
        )

        rotation_layout.addWidget(self._rotation_input)
        rotation_layout.addWidget(self._random_rotation_check)
        rotation_layout.addStretch()
        form.addRow("Rotation:", rotation_row)

        size_row = QWidget()
        size_layout = QHBoxLayout(size_row)
        size_layout.setContentsMargins(0, 0, 0, 0)
        size_layout.setSpacing(8)

        self._size_spin = QSpinBox()
        self._size_spin.setRange(SCALE_MIN_PCT, SCALE_MAX_PCT)
        self._size_spin.setSuffix("%")
        self._size_spin.setValue(DEFAULT_SCALE_PCT)
        self._size_spin.setToolTip(
            f"Pattern size ({SCALE_MIN_PCT}% to {SCALE_MAX_PCT}%)"
        )
        self._size_spin.setFixedWidth(80)
        self._size_input = SpinInput(self._size_spin)

        self._random_size_check = QCheckBox("Random size")
        self._random_size_check.setToolTip(
            f"Pick a size between {RANDOM_SCALE_MIN_PCT}% and {RANDOM_SCALE_MAX_PCT}% "
            "on each cast"
        )

        size_layout.addWidget(self._size_input)
        size_layout.addWidget(self._random_size_check)
        size_layout.addStretch()
        form.addRow("Size:", size_row)

        self._center_label = QLabel("—")
        form.addRow("Center:", self._center_label)

        root.addLayout(form)

        options_row = QHBoxLayout()
        options_row.setSpacing(16)

        self._turbo_plus_check = QCheckBox("Speed ++ (experimental)")
        self._turbo_plus_check.setToolTip(
            "Ultra-fast draw: ~0.05 ms/point, 16 px steps, no stroke pause "
            "(vs ~1 ms/point in base turbo). May be too fast for some games."
        )
        options_row.addWidget(self._turbo_plus_check)

        self._always_on_top_check = QCheckBox("Always on top")
        self._always_on_top_check.setToolTip(
            "Keep this window above other applications"
        )
        self._always_on_top_check.toggled.connect(self._on_always_on_top_toggled)
        options_row.addWidget(self._always_on_top_check)
        options_row.addStretch()
        root.addLayout(options_row)

        shake_row = QWidget()
        shake_layout = QHBoxLayout(shake_row)
        shake_layout.setContentsMargins(0, 0, 0, 0)
        shake_layout.setSpacing(8)

        self._shake_check = QCheckBox("Shake (hand tremor)")
        self._shake_check.setToolTip(
            "Add a subtle hand tremor while drawing"
        )

        self._shake_spin = QSpinBox()
        self._shake_spin.setRange(SHAKE_MIN_PCT, SHAKE_MAX_PCT)
        self._shake_spin.setSuffix("%")
        self._shake_spin.setValue(SHAKE_DEFAULT_PCT)
        self._shake_spin.setToolTip(
            f"Shake intensity ({SHAKE_MIN_PCT}%–{SHAKE_MAX_PCT}%)"
        )
        self._shake_spin.setFixedWidth(80)
        self._shake_input = SpinInput(self._shake_spin)

        self._random_shake_check = QCheckBox("Random shake")
        self._random_shake_check.setToolTip(
            f"Pick an intensity between {RANDOM_SHAKE_MIN_PCT}% and "
            f"{RANDOM_SHAKE_MAX_PCT}% on each cast"
        )

        shake_layout.addWidget(self._shake_check)
        shake_layout.addWidget(self._shake_input)
        shake_layout.addWidget(self._random_shake_check)
        shake_layout.addStretch()
        root.addWidget(shake_row)

        actions = QHBoxLayout()
        actions.setSpacing(8)
        self._preview_btn = QPushButton("Show overlay")
        self._preview_btn.setObjectName("GhostButton")
        self._cast_btn = QPushButton("Cast (C)")
        self._cast_btn.setObjectName("PrimaryButton")
        self._cast_btn.setToolTip("Start drawing (C)")
        self._cancel_btn = QPushButton("Cancel")
        self._cancel_btn.setEnabled(False)
        actions.addWidget(self._preview_btn)
        actions.addWidget(self._cast_btn, stretch=1)
        actions.addWidget(self._cancel_btn)
        root.addLayout(actions)

        self._progress = QProgressBar()
        self._progress.setRange(0, 100)
        self._progress.setValue(0)
        self._progress.setTextVisible(True)
        self._progress.setFormat("%p %")
        self._progress.setVisible(False)
        root.addWidget(self._progress)

        self._status_label = QLabel("Pick a sigil or sign.")
        self._status_label.setObjectName("StatusLabel")
        root.addWidget(self._status_label)

    def _wire_signals(self) -> None:
        """Connect UI widgets, shortcuts, and overlay signals."""
        self._grid.asset_selected.connect(self._on_asset_selected)
        self._rotation_spin.valueChanged.connect(self._on_preview_settings_changed)
        self._random_rotation_check.toggled.connect(self._on_random_rotation_toggled)
        self._size_spin.valueChanged.connect(self._on_preview_settings_changed)
        self._random_size_check.toggled.connect(self._on_random_size_toggled)
        self._shake_check.toggled.connect(self._on_shake_toggled)
        self._random_shake_check.toggled.connect(self._on_random_shake_toggled)
        self._on_shake_toggled(self._shake_check.isChecked())
        self._preview_btn.clicked.connect(self._toggle_preview)
        self._cast_btn.clicked.connect(self._cast)
        self._cancel_btn.clicked.connect(self._cancel_draw)
        self._overlay.center_moved.connect(self._on_overlay_moved)

        self._cast_shortcut = QShortcut(QKeySequence("C"), self)
        self._cast_shortcut.setContext(Qt.ShortcutContext.ApplicationShortcut)
        self._cast_shortcut.activated.connect(self._cast)

        QShortcut(QKeySequence("P"), self).activated.connect(self._toggle_preview)
        QShortcut(QKeySequence(Qt.Key.Key_Escape), self).activated.connect(
            self._on_escape
        )

    def _on_asset_selected(self, kind: str, name: str) -> None:
        """
        Store the picked asset and refresh overlay preview when visible.

        Parameters
        ----------
        kind : str
            Asset kind (``sigil`` or ``sign``).
        name : str
            Asset catalogue name.

        Returns
        -------
        None
        """
        if self._worker and self._worker.isRunning():
            return

        self._config.kind = kind
        self._config.name = name
        self._update_selection_label()
        self._status_label.setText(
            f"{self._config.kind.capitalize()} \"{name}\" selected — cast to draw."
        )
        if self._random_rotation_check.isChecked():
            self._roll_random_rotation()
        if self._random_size_check.isChecked():
            self._roll_random_scale()
        if self._overlay_visible:
            self._sync_overlay()

    def _on_random_rotation_toggled(self, enabled: bool) -> None:
        """Enable or disable manual rotation when random rotation is toggled."""
        self._rotation_spin.setEnabled(not enabled)
        if enabled:
            self._roll_random_rotation()
        else:
            self._random_rotation_deg = None
        if self._overlay_visible:
            self._sync_overlay()

    def _roll_random_rotation(self) -> float:
        """
        Draw a new random rotation in degrees.

        Returns
        -------
        float
            Rotation between 0 and 360 degrees.
        """
        self._random_rotation_deg = float(random.randint(0, 360))
        return self._random_rotation_deg

    def _on_shake_toggled(self, enabled: bool) -> None:
        """Update shake spinbox state when shake is enabled or disabled."""
        self._update_shake_inputs()
        if not enabled:
            self._random_shake_pct = None

    def _on_random_shake_toggled(self, enabled: bool) -> None:
        """Enable random shake intensity when the checkbox is toggled."""
        self._update_shake_inputs()
        if enabled:
            self._roll_random_shake()
        else:
            self._random_shake_pct = None

    def _update_shake_inputs(self) -> None:
        """Enable shake controls according to shake and random-shake flags."""
        shake_on = self._shake_check.isChecked()
        random_on = self._random_shake_check.isChecked()
        self._random_shake_check.setEnabled(shake_on)
        self._shake_spin.setEnabled(shake_on and not random_on)

    def _roll_random_shake(self) -> float:
        """
        Draw a new random shake intensity percent.

        Returns
        -------
        float
            Intensity between ``RANDOM_SHAKE_MIN_PCT`` and ``RANDOM_SHAKE_MAX_PCT``.
        """
        self._random_shake_pct = float(
            random.randint(RANDOM_SHAKE_MIN_PCT, RANDOM_SHAKE_MAX_PCT)
        )
        return self._random_shake_pct

    def _effective_shake_pct(self, *, fresh_random: bool = False) -> float:
        """
        Resolve shake intensity from manual, random, or disabled state.

        Parameters
        ----------
        fresh_random : bool, optional
            When ``True``, roll a new random value on this cast.

        Returns
        -------
        float
            Shake intensity percent (0 when shake is off).
        """
        if not self._shake_check.isChecked():
            self._random_shake_pct = None
            return 0.0
        if self._random_shake_check.isChecked():
            if fresh_random or self._random_shake_pct is None:
                return self._roll_random_shake()
            return self._random_shake_pct
        self._random_shake_pct = None
        return float(self._shake_spin.value())

    def _shake_amplitude_px(self, *, fresh_random: bool = False) -> float:
        """
        Convert effective shake percent to pixel amplitude for the worker.

        Parameters
        ----------
        fresh_random : bool, optional
            When ``True``, roll a new random shake value.

        Returns
        -------
        float
            Tremor amplitude in screen pixels.
        """
        return shake_amplitude_from_percent(
            self._effective_shake_pct(fresh_random=fresh_random)
        )

    def _on_always_on_top_toggled(self, enabled: bool) -> None:
        """Toggle ``WindowStaysOnTopHint`` on the host window."""
        window = self.window()
        flags = window.windowFlags()
        if enabled:
            flags |= Qt.WindowType.WindowStaysOnTopHint
        else:
            flags &= ~Qt.WindowType.WindowStaysOnTopHint
        window.setWindowFlags(flags)
        window.show()

    def _on_random_size_toggled(self, enabled: bool) -> None:
        """Enable or disable manual size when random size is toggled."""
        self._size_spin.setEnabled(not enabled)
        if enabled:
            self._roll_random_scale()
        else:
            self._random_scale_pct = None
        if self._overlay_visible:
            self._sync_overlay()

    def _roll_random_scale(self) -> float:
        """
        Draw a new random scale percent.

        Returns
        -------
        float
            Scale between ``RANDOM_SCALE_MIN_PCT`` and ``RANDOM_SCALE_MAX_PCT``.
        """
        self._random_scale_pct = float(
            random.randint(RANDOM_SCALE_MIN_PCT, RANDOM_SCALE_MAX_PCT)
        )
        return self._random_scale_pct

    def _effective_rotation(self, *, fresh_random: bool = False) -> float:
        """
        Resolve rotation from manual spinbox or random mode.

        Parameters
        ----------
        fresh_random : bool, optional
            When ``True``, roll a new random rotation on this cast.

        Returns
        -------
        float
            Rotation in degrees.
        """
        if self._random_rotation_check.isChecked():
            if fresh_random or self._random_rotation_deg is None:
                return self._roll_random_rotation()
            return self._random_rotation_deg
        self._random_rotation_deg = None
        return float(self._rotation_spin.value())

    def _effective_scale(self, *, fresh_random: bool = False) -> float:
        """
        Resolve scale from manual spinbox or random mode.

        Parameters
        ----------
        fresh_random : bool, optional
            When ``True``, roll a new random scale on this cast.

        Returns
        -------
        float
            Scale percent.
        """
        if self._random_size_check.isChecked():
            if fresh_random or self._random_scale_pct is None:
                return self._roll_random_scale()
            return self._random_scale_pct
        self._random_scale_pct = None
        return float(self._size_spin.value())

    def _update_selection_label(self) -> None:
        """Refresh the selection summary label from ``_config``."""
        if self._config.name:
            kind_label = "Sigil" if self._config.kind == "sigil" else "Sign"
            self._selection_label.setText(f"{kind_label} — {self._config.name}")
        else:
            self._selection_label.setText("—")

    def _on_preview_settings_changed(self, _value: int) -> None:
        """Refresh overlay preview when rotation or size changes."""
        if self._overlay_visible:
            self._sync_overlay()

    def _collect_config(self, *, fresh_random: bool = False) -> SampleConfig:
        """
        Build a ``SampleConfig`` from current UI state.

        Parameters
        ----------
        fresh_random : bool, optional
            When ``True``, re-roll random rotation, size, and shake values.

        Returns
        -------
        SampleConfig
            Configuration ready for composition or drawing.
        """
        self._config.rotation_deg = self._effective_rotation(fresh_random=fresh_random)
        self._config.scale_pct = self._effective_scale(fresh_random=fresh_random)
        if self._overlay.isVisible():
            self._config.overlay_center = self._overlay.center()
        return self._config

    def _preview_config(self) -> SampleConfig:
        """
        Return config for overlay preview (empty name allowed).

        Returns
        -------
        SampleConfig
            Copy of the current configuration.
        """
        config = self._collect_config()
        if not config.name:
            config.name = ""
        return config

    def _toggle_preview(self) -> None:
        """Show or hide the targeting overlay."""
        if self._overlay_visible:
            self._hide_overlay()
        else:
            self._show_overlay()

    def _show_overlay(self) -> None:
        """Display the draggable overlay and update button label."""
        self._sync_overlay()
        self._overlay.show()
        self._overlay_visible = True
        self._preview_btn.setText("Hide overlay")
        self._status_label.setText(
            "Overlay shown — drag it onto the drawing area."
        )

    def _hide_overlay(self) -> None:
        """Hide the overlay and restore the preview button label."""
        self._overlay.hide()
        self._overlay_visible = False
        self._preview_btn.setText("Show overlay")

    def _sync_overlay(self) -> None:
        """Push the current preview config to the overlay and center label."""
        self._overlay.update_sample(self._preview_config())
        cx, cy = self._overlay.center()
        self._center_label.setText(f"({cx:.0f}, {cy:.0f})")

    def _on_overlay_moved(self, cx: float, cy: float) -> None:
        """
        Track overlay center when the user drags it.

        Parameters
        ----------
        cx : float
            Overlay center X in screen coordinates.
        cy : float
            Overlay center Y in screen coordinates.

        Returns
        -------
        None
        """
        self._config.overlay_center = (cx, cy)
        self._center_label.setText(f"({cx:.0f}, {cy:.0f})")

    def _cast(self) -> None:
        """Compose the sample plan and start the background draw worker."""
        if self._worker and self._worker.isRunning():
            return
        if not self._config.name:
            QMessageBox.information(
                self,
                "Selection required",
                "Pick a sigil or sign first by clicking its thumbnail.",
            )
            return

        self._hide_overlay()
        config = self._collect_config(fresh_random=True)
        plan = compose_sample(config)
        if not plan.strokes:
            QMessageBox.warning(self, "Error", "No strokes to draw.")
            return

        self._worker = DrawWorker(plan)
        self._worker.cast_countdown = False
        self._worker.set_point_delay(0.0)
        if self._turbo_plus_check.isChecked():
            self._worker.set_pacing(FAST_SAMPLE_TURBO_PLUS_PACING)
        self._worker.set_shake_amplitude(self._shake_amplitude_px(fresh_random=True))
        self._worker.progress.connect(self._status_label.setText)
        self._worker.draw_progress.connect(self._on_draw_progress)
        self._worker.finished_ok.connect(self._on_draw_finished)
        self._worker.finished_cancelled.connect(self._on_draw_cancelled)
        self._worker.error.connect(self._on_draw_error)

        self._progress.setValue(0)
        self._progress.setVisible(True)

        kind_label = "Sigil" if config.kind == "sigil" else "Sign"
        self._cast_btn.setEnabled(False)
        self._cast_shortcut.setEnabled(False)
        self._preview_btn.setEnabled(False)
        self._cancel_btn.setEnabled(True)
        self._grid.setEnabled(False)
        self._status_label.setText(
            f"Drawing {kind_label} \"{config.name}\" "
            f"({config.scale_pct:.0f}%, {config.rotation_deg:.0f}°)…"
        )
        self._worker.start()

    def _cancel_draw(self) -> None:
        """Request cancellation of the active draw worker."""
        if self._worker:
            self._worker.cancel()

    def _on_escape(self) -> None:
        """Cancel an active draw or hide the overlay on Escape."""
        if self._worker and self._worker.isRunning():
            self._cancel_draw()
        elif self._overlay_visible:
            self._hide_overlay()

    def _on_draw_progress(self, percent: int) -> None:
        """Update the progress bar during drawing."""
        self._progress.setValue(percent)

    def _reset_draw_ui(self) -> None:
        """Re-enable controls after a draw finishes, is cancelled, or errors."""
        self._cast_btn.setEnabled(True)
        self._cast_shortcut.setEnabled(True)
        self._preview_btn.setEnabled(True)
        self._cancel_btn.setEnabled(False)
        self._grid.setEnabled(True)
        self._worker = None
        self._progress.setVisible(False)
        self._progress.setValue(0)

    def _on_draw_finished(self) -> None:
        """Handle successful draw completion."""
        self._reset_draw_ui()
        self._status_label.setText("Drawing finished.")

    def _on_draw_cancelled(self) -> None:
        """Handle user-cancelled draw."""
        self._reset_draw_ui()
        self._status_label.setText("Drawing cancelled.")

    def _on_draw_error(self, message: str) -> None:
        """
        Show draw errors and restore the UI.

        Parameters
        ----------
        message : str
            Error text from the draw worker.

        Returns
        -------
        None
        """
        self._reset_draw_ui()
        QMessageBox.critical(self, "Error", message)
        self._status_label.setText(f"Error: {message}")
