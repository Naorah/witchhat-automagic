"""Speed calibrator control panel."""

from __future__ import annotations

from typing import Optional

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QKeySequence, QShortcut
from PyQt6.QtWidgets import (
    QApplication,
    QComboBox,
    QDoubleSpinBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from src.mouse_drawer import DrawWorker, NORMAL_PACING
from src.ui.cast_key_filter import enable_cast_key_on_spinboxes
from src.ui.spin_input import SpinInput

from calibrator import Calibrator
from overlay import CalibratorOverlay
from test_patterns import build_test_plan

PATTERN_CHOICES = [
    ("Line", "line"),
    ("Cross (2 strokes)", "cross"),
    ("Arc 270°", "arc"),
]


class CalibratorPanel(QWidget):
    """Binary-search UI to find the fastest reliable cast pacing."""

    def __init__(self) -> None:
        """
        Build the panel and start the first calibration trial.

        Returns
        -------
        None
        """
        super().__init__()
        self._calibrator = Calibrator()
        self._overlay = CalibratorOverlay()
        self._overlay_visible = False
        self._center = (400.0, 400.0)
        self._worker: Optional[DrawWorker] = None

        self._build_ui()
        self._wire_signals()
        enable_cast_key_on_spinboxes(self, self._run_test)
        self._refresh_trial_labels()

    def _build_ui(self) -> None:
        """Lay out pattern settings, trial controls, and result panels."""
        root = QVBoxLayout(self)
        root.setContentsMargins(18, 16, 18, 18)
        root.setSpacing(10)

        hint = QLabel(
            "1) Show the overlay on the game drawing area. "
            "2) Run a trial (C). "
            "3) Indicate whether the stroke was detected (Y/N). "
            "Binary search typically converges in ~8–12 trials."
        )
        hint.setWordWrap(True)
        hint.setObjectName("HintLabel")
        root.addWidget(hint)

        form = QFormLayout()
        form.setSpacing(8)

        self._pattern_combo = QComboBox()
        for label, value in PATTERN_CHOICES:
            self._pattern_combo.addItem(label, value)
        form.addRow("Pattern:", self._pattern_combo)

        self._size_spin = QSpinBox()
        self._size_spin.setRange(40, 600)
        self._size_spin.setSuffix(" px")
        self._size_spin.setValue(160)
        self._size_spin.setToolTip("Test stroke size")
        self._size_input = SpinInput(self._size_spin)
        form.addRow("Size:", self._size_input)

        self._segment_spin = QDoubleSpinBox()
        self._segment_spin.setRange(2.0, 16.0)
        self._segment_spin.setSingleStep(0.5)
        self._segment_spin.setDecimals(1)
        self._segment_spin.setSuffix(" px")
        self._segment_spin.setValue(self._calibrator.fixed_segment_px)
        self._segment_spin.setToolTip(
            "Fixed interpolation step during the delay phase"
        )
        self._segment_input = SpinInput(self._segment_spin)
        form.addRow("Step (phase 1):", self._segment_input)

        self._phase_label = QLabel("Phase 1 — delay")
        self._phase_label.setObjectName("SectionTitle")
        form.addRow("Stage:", self._phase_label)

        self._trial_label = QLabel("—")
        self._trial_label.setObjectName("StatusLabel")
        form.addRow("Trial:", self._trial_label)

        self._bounds_label = QLabel("—")
        form.addRow("Bounds:", self._bounds_label)

        root.addLayout(form)

        row_test = QHBoxLayout()
        self._overlay_btn = QPushButton("Overlay (P)")
        self._overlay_btn.setObjectName("GhostButton")
        self._test_btn = QPushButton("Run trial (C)")
        self._test_btn.setObjectName("PrimaryButton")
        row_test.addWidget(self._overlay_btn)
        row_test.addWidget(self._test_btn, stretch=1)
        root.addLayout(row_test)

        row_feedback = QHBoxLayout()
        self._ok_btn = QPushButton("Detected ✓ (Y)")
        self._ok_btn.setObjectName("PrimaryButton")
        self._fail_btn = QPushButton("Missed ✗ (N)")
        self._fail_btn.setObjectName("GhostButton")
        self._push_btn = QPushButton("Push faster")
        self._push_btn.setObjectName("GhostButton")
        self._push_btn.setToolTip(
            "Restart binary search below the best delay found (down to 0.05 ms/pt)"
        )
        self._reset_btn = QPushButton("Reset")
        self._reset_btn.setObjectName("GhostButton")
        row_feedback.addWidget(self._ok_btn)
        row_feedback.addWidget(self._fail_btn)
        row_feedback.addWidget(self._push_btn)
        row_feedback.addWidget(self._reset_btn)
        root.addLayout(row_feedback)

        self._log = QTextEdit()
        self._log.setReadOnly(True)
        self._log.setMaximumHeight(120)
        root.addWidget(self._log)

        self._result = QTextEdit()
        self._result.setReadOnly(True)
        self._result.setMaximumHeight(140)
        self._result.setPlaceholderText(
            "Result and TURBO_PACING snippet to copy…"
        )
        root.addWidget(self._result)

        copy_row = QHBoxLayout()
        self._copy_btn = QPushButton("Copy profile")
        self._copy_btn.setObjectName("GhostButton")
        copy_row.addWidget(self._copy_btn)
        copy_row.addStretch()
        root.addLayout(copy_row)

        self._status = QLabel("Ready.")
        root.addWidget(self._status)

    def _wire_signals(self) -> None:
        """Connect UI widgets and keyboard shortcuts."""
        self._pattern_combo.currentIndexChanged.connect(self._sync_overlay)
        self._size_spin.valueChanged.connect(self._sync_overlay)
        self._segment_spin.valueChanged.connect(self._on_segment_changed)
        self._overlay_btn.clicked.connect(self._toggle_overlay)
        self._test_btn.clicked.connect(self._run_test)
        self._ok_btn.clicked.connect(lambda: self._record(True))
        self._fail_btn.clicked.connect(lambda: self._record(False))
        self._push_btn.clicked.connect(self._push_faster)
        self._reset_btn.clicked.connect(self._reset)
        self._copy_btn.clicked.connect(self._copy_result)
        self._overlay.center_moved.connect(self._on_overlay_moved)

        QShortcut(QKeySequence("C"), self).activated.connect(self._run_test)
        QShortcut(QKeySequence("Y"), self).activated.connect(lambda: self._record(True))
        QShortcut(QKeySequence("N"), self).activated.connect(lambda: self._record(False))
        QShortcut(QKeySequence("P"), self).activated.connect(self._toggle_overlay)

    def _on_segment_changed(self, value: float) -> None:
        """
        Update the fixed segment step when the spinbox changes.

        Parameters
        ----------
        value : float
            New segment step in pixels.

        Returns
        -------
        None
        """
        self._calibrator.set_fixed_segment(value)
        self._refresh_trial_labels()

    def _pattern(self) -> str:
        """Return the selected test pattern id."""
        return str(self._pattern_combo.currentData())

    def _build_plan(self):
        """Build a test draw plan at the current overlay center."""
        center = self._overlay.center() if self._overlay.isVisible() else self._center
        return build_test_plan(center, self._size_spin.value(), self._pattern())

    def _sync_overlay(self) -> None:
        """Refresh overlay preview strokes when settings change."""
        if not self._overlay_visible:
            return
        center = self._overlay.center()
        plan = build_test_plan(center, self._size_spin.value(), self._pattern())
        self._overlay.set_preview(center, plan.strokes, self._size_spin.value())

    def _toggle_overlay(self) -> None:
        """Show or hide the calibration overlay."""
        if self._overlay_visible:
            self._overlay.hide()
            self._overlay_visible = False
            self._overlay_btn.setText("Overlay (P)")
        else:
            center = self._center
            plan = build_test_plan(center, self._size_spin.value(), self._pattern())
            self._overlay.set_preview(center, plan.strokes, self._size_spin.value())
            self._overlay.show()
            self._overlay_visible = True
            self._overlay_btn.setText("Hide overlay")
            self._center = self._overlay.center()

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
        self._center = (cx, cy)
        self._sync_overlay()

    def _refresh_trial_labels(self) -> None:
        """Update phase, trial, bounds, and result panels from calibrator state."""
        delay_s, segment_px = self._calibrator.current_trial()
        phase = self._calibrator.phase
        phase_text = {
            "delay": "Phase 1 — delay (ms/pt)",
            "segment": "Phase 2 — step (px)",
            "done": "Complete",
        }.get(phase, phase)
        self._phase_label.setText(phase_text)
        self._trial_label.setText(
            f"{delay_s * 1000:.3f} ms/pt — step {segment_px:.1f} px"
        )
        if phase == "delay":
            self._bounds_label.setText(
                f"delay {self._calibrator.delay_lo_s * 1000:.3f}–"
                f"{self._calibrator.delay_hi_s * 1000:.3f} ms"
            )
        elif phase == "segment":
            self._bounds_label.setText(
                f"step {self._calibrator.segment_lo_px:.1f}–"
                f"{self._calibrator.segment_hi_px:.1f} px @ "
                f"{delay_s * 1000:.2f} ms/pt"
            )
        else:
            self._bounds_label.setText("—")
        self._result.setPlainText(self._calibrator.summary())
        self._push_btn.setEnabled(
            self._calibrator.best_pacing is not None
            and not (self._worker and self._worker.isRunning())
        )

    def _set_busy(self, busy: bool) -> None:
        """
        Disable or re-enable controls while a trial is running.

        Parameters
        ----------
        busy : bool
            Whether a draw worker is active.

        Returns
        -------
        None
        """
        for widget in (
            self._test_btn,
            self._ok_btn,
            self._fail_btn,
            self._overlay_btn,
            self._reset_btn,
            self._push_btn,
        ):
            widget.setEnabled(not busy)
        if not busy:
            self._refresh_trial_labels()

    def _run_test(self) -> None:
        """Draw the test pattern with the current or best pacing profile."""
        if self._worker and self._worker.isRunning():
            return

        plan = self._build_plan()
        if self._calibrator.is_done() and self._calibrator.best_pacing:
            pacing = self._calibrator.best_pacing
        else:
            pacing = self._calibrator.current_pacing()
        self._worker = DrawWorker(plan)
        self._worker.cast_countdown = False
        self._worker.set_pacing(pacing)
        self._worker.progress.connect(self._status.setText)
        self._worker.finished_ok.connect(self._on_test_done)
        self._worker.finished_cancelled.connect(self._on_test_done)
        self._worker.error.connect(self._on_test_error)

        delay_ms = pacing.point_delay_s * 1000
        self._status.setText(f"Trial running — {delay_ms:.3f} ms/pt…")
        self._set_busy(True)
        self._worker.start()

    def _on_test_done(self) -> None:
        """Prompt for Y/N feedback after a trial finishes."""
        self._set_busy(False)
        self._worker = None
        self._status.setText(
            "Trial finished — did the game detect the stroke? (Y/N)"
        )

    def _on_test_error(self, message: str) -> None:
        """
        Show draw errors and restore controls.

        Parameters
        ----------
        message : str
            Error text from the draw worker.

        Returns
        -------
        None
        """
        self._set_busy(False)
        self._worker = None
        QMessageBox.critical(self, "Error", message)

    def _record(self, success: bool) -> None:
        """
        Record trial success or failure and advance the search.

        Parameters
        ----------
        success : bool
            Whether the game detected the stroke.

        Returns
        -------
        None
        """
        if self._worker and self._worker.isRunning():
            return
        if self._calibrator.is_done():
            return

        delay_s, segment_px = self._calibrator.current_trial()
        tag = "OK" if success else "FAIL"
        self._log.append(
            f"[{tag}] {delay_s * 1000:.3f} ms/pt — step {segment_px:.1f} px"
        )
        message = self._calibrator.record(success)
        self._refresh_trial_labels()
        self._status.setText(message)

    def _push_faster(self) -> None:
        """Search for faster pacing below the current best delay."""
        if self._worker and self._worker.isRunning():
            return
        message = self._calibrator.push_faster()
        self._segment_spin.setValue(self._calibrator.fixed_segment_px)
        self._refresh_trial_labels()
        self._status.setText(message)
        self._log.append(f"--- {message}")

    def _reset(self) -> None:
        """Clear history and restart calibration."""
        if self._worker and self._worker.isRunning():
            return
        self._calibrator.reset()
        self._segment_spin.setValue(self._calibrator.fixed_segment_px)
        self._log.clear()
        self._refresh_trial_labels()
        self._status.setText(
            f"Reset. Safe reference: {NORMAL_PACING.point_delay_s * 1000:.1f} ms/pt."
        )

    def _copy_result(self) -> None:
        """Copy the summary and TURBO_PACING snippet to the clipboard."""
        text = self._calibrator.summary()
        if not text.strip():
            return
        QApplication.clipboard().setText(text)
        self._status.setText("Profile copied to clipboard.")
