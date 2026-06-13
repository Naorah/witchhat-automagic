"""Background mouse drawing worker for spell execution."""

from __future__ import annotations

import math
import random
import time
from dataclasses import dataclass
from typing import List, Optional, Tuple

from PyQt6.QtCore import QObject, QThread, pyqtSignal
from pynput import keyboard
from pynput.mouse import Button, Controller

from .models import SpellPlan, Stroke

DEFAULT_POINT_DELAY_S = 0.01
COUNTDOWN_SECONDS = 3
MIN_SEGMENT_PX = 2.0
NORMAL_BAND_MAX_S = 0.02
SHAKE_MAX_AMPLITUDE_PX = 3.5
SHAKE_MIN_PCT = 10
SHAKE_MAX_PCT = 200
SHAKE_DEFAULT_PCT = 45
RANDOM_SHAKE_MIN_PCT = 50
RANDOM_SHAKE_MAX_PCT = 170


def shake_amplitude_from_percent(percent: float) -> float:
    """Convert a shake intensity percent to a pixel amplitude."""
    return SHAKE_MAX_AMPLITUDE_PX * (max(0.0, percent) / 100.0)


@dataclass(frozen=True)
class DrawPacing:
    """Mouse pacing profile for stroke execution."""

    point_delay_s: float
    stroke_delay_s: float
    segment_px: float
    press_settle_s: float
    release_settle_s: float


NORMAL_PACING = DrawPacing(
    point_delay_s=0.006,
    stroke_delay_s=0.02,
    segment_px=3.0,
    press_settle_s=0.012,
    release_settle_s=0.008,
)

TURBO_PACING = DrawPacing(
    point_delay_s=0.001,
    stroke_delay_s=0.004,
    segment_px=5.0,
    press_settle_s=0.004,
    release_settle_s=0.002,
)

TURBO_PLUS_PACING = DrawPacing(
    point_delay_s=0.0007,
    stroke_delay_s=0.002,
    segment_px=6.0,
    press_settle_s=0.003,
    release_settle_s=0.002,
)

ULTRA_TURBO_PLUS_PACING = DrawPacing(
    point_delay_s=0.00005,
    stroke_delay_s=0.0,
    segment_px=16.0,
    press_settle_s=0.0,
    release_settle_s=0.0,
)


def _interpolate_stroke(stroke: Stroke, min_step: float = MIN_SEGMENT_PX) -> Stroke:
    """
    Densify a stroke so consecutive points are at most ``min_step`` apart.

    Parameters
    ----------
    stroke : Stroke
        Input polyline.
    min_step : float, optional
        Maximum segment length in pixels, by default ``MIN_SEGMENT_PX``.

    Returns
    -------
    Stroke
        Interpolated polyline including the original endpoints.
    """
    if len(stroke) < 2:
        return stroke

    result: Stroke = [stroke[0]]
    for i in range(1, len(stroke)):
        x0, y0 = result[-1]
        x1, y1 = stroke[i]
        dist = math.hypot(x1 - x0, y1 - y0)
        if dist <= min_step:
            result.append((x1, y1))
            continue
        steps = max(1, int(math.ceil(dist / min_step)))
        for s in range(1, steps + 1):
            t = s / steps
            result.append((x0 + (x1 - x0) * t, y0 + (y1 - y0) * t))
    return result


class HandTremor:
    """Stateful micro-jitter mimicking a human hand tremor."""

    def __init__(self, amplitude_px: float) -> None:
        self._amplitude_px = max(0.0, amplitude_px)
        self._offset_x = 0.0
        self._offset_y = 0.0

    @property
    def enabled(self) -> bool:
        return self._amplitude_px > 0.0

    def reset(self) -> None:
        """Clear accumulated tremor offset."""
        self._offset_x = 0.0
        self._offset_y = 0.0

    def sample(self) -> Tuple[float, float]:
        """
        Return the next smoothed tremor offset in pixels.

        Returns
        -------
        tuple of float
            ``(dx, dy)`` added to the target cursor position.
        """
        if not self.enabled:
            return (0.0, 0.0)

        amp = self._amplitude_px
        self._offset_x = self._offset_x * 0.62 + random.gauss(0.0, amp * 0.38)
        self._offset_y = self._offset_y * 0.62 + random.gauss(0.0, amp * 0.38)
        limit = amp * 1.6
        self._offset_x = max(-limit, min(limit, self._offset_x))
        self._offset_y = max(-limit, min(limit, self._offset_y))
        return (self._offset_x, self._offset_y)


def _pacing_from_delay(seconds: float, *, turbo_plus: bool) -> DrawPacing:
    """
    Build a pacing profile from the configured point delay.

    Parameters
    ----------
    seconds : float
        Requested per-point delay; ``0`` selects turbo pacing.
    turbo_plus : bool
        When ``True`` and ``seconds`` is ``0``, use the faster turbo-plus tier.

    Returns
    -------
    DrawPacing
        Resolved pacing constants.
    """
    if seconds <= 0.0:
        return TURBO_PLUS_PACING if turbo_plus else TURBO_PACING

    if seconds < NORMAL_BAND_MAX_S:
        return NORMAL_PACING

    return DrawPacing(
        point_delay_s=seconds,
        stroke_delay_s=max(0.03, seconds * 12),
        segment_px=MIN_SEGMENT_PX,
        press_settle_s=0.0,
        release_settle_s=0.0,
    )


class DrawWorker(QThread):
    """Background thread that executes a spell plan with the system mouse."""

    progress = pyqtSignal(str)
    draw_progress = pyqtSignal(int)
    finished_ok = pyqtSignal()
    finished_cancelled = pyqtSignal()
    error = pyqtSignal(str)

    def __init__(self, plan: SpellPlan, parent: Optional[QObject] = None) -> None:
        """
        Initialize the draw worker.

        Parameters
        ----------
        plan : SpellPlan
            Ordered strokes to execute.
        parent : QObject, optional
            Qt parent object.
        """
        super().__init__(parent)
        self._plan = plan
        self._mouse = Controller()
        self._cancelled = False
        self._pacing = NORMAL_PACING
        self._configured_point_delay = DEFAULT_POINT_DELAY_S
        self._turbo_plus = False
        self._tremor = HandTremor(0.0)
        self._total_draw_steps = 0
        self._completed_draw_steps = 0
        self.dry_run = False
        self.cast_countdown = True
        self.set_point_delay(DEFAULT_POINT_DELAY_S)

    def cancel(self) -> None:
        """
        Request cancellation of the current draw sequence.

        Returns
        -------
        None
        """
        self._cancelled = True

    def set_point_delay(self, seconds: float) -> None:
        """
        Configure per-point delay and derived stroke pacing.

        Parameters
        ----------
        seconds : float
            Delay between points in seconds; ``0`` enables turbo pacing.

        Returns
        -------
        None
        """
        self._configured_point_delay = max(0.0, min(1.0, seconds))
        self._apply_timing()

    def set_shake_amplitude(self, amplitude_px: float) -> None:
        """
        Enable hand-tremor jitter during drawing.

        Parameters
        ----------
        amplitude_px : float
            Peak tremor radius in pixels; ``0`` disables shake.

        Returns
        -------
        None
        """
        self._tremor = HandTremor(amplitude_px)

    def set_pacing(self, pacing: DrawPacing) -> None:
        """
        Apply an explicit pacing profile (used by calibration tools).

        Parameters
        ----------
        pacing : DrawPacing
            Full timing profile for the next draw run.

        Returns
        -------
        None
        """
        self._pacing = pacing

    def set_turbo_plus(self, enabled: bool) -> None:
        """
        Enable experimental turbo-plus pacing when point delay is ``0``.

        Faster than turbo but still keeps short per-point delays so the game
        can sample mouse movement.

        Parameters
        ----------
        enabled : bool
            When ``True``, use the turbo-plus pacing tier.

        Returns
        -------
        None
        """
        self._turbo_plus = enabled
        self._apply_timing()

    def _apply_timing(self) -> None:
        """
        Derive pacing from configured point delay and turbo-plus flag.

        Returns
        -------
        None
        """
        self._pacing = _pacing_from_delay(
            self._configured_point_delay,
            turbo_plus=self._turbo_plus,
        )

    def run(self) -> None:
        """
        Execute the spell plan: countdown then each stroke in order.

        Returns
        -------
        None
        """
        listener: Optional[keyboard.Listener] = None
        try:
            listener = keyboard.Listener(on_press=self._on_global_key)
            listener.start()

            if self.cast_countdown:
                for remaining in range(COUNTDOWN_SECONDS, 0, -1):
                    if self._cancelled:
                        self.finished_cancelled.emit()
                        return
                    self.progress.emit(f"Starting in {remaining}s… (Esc to cancel)")
                    self._sleep_interruptible(1.0)
            elif self._cancelled:
                self.finished_cancelled.emit()
                return

            self._prepare_draw_progress()
            self.draw_progress.emit(0)

            for idx, stroke in enumerate(self._plan.strokes):
                if self._cancelled:
                    self._release_mouse()
                    self.finished_cancelled.emit()
                    return

                label = self._stroke_label(idx)
                self.progress.emit(f"Drawing: {label} (Esc to cancel)")
                self._draw_stroke(stroke)
                self._sleep_interruptible(self._pacing.stroke_delay_s)

            self._release_mouse()
            self.finished_ok.emit()
        except Exception as exc:
            self._release_mouse()
            self.error.emit(str(exc))
        finally:
            if listener is not None:
                listener.stop()

    def _on_global_key(self, key: keyboard.Key | keyboard.KeyCode) -> None:
        """
        Cancel the draw when Escape is pressed anywhere on the system.

        Parameters
        ----------
        key : keyboard.Key or keyboard.KeyCode
            Key event from the global listener.

        Returns
        -------
        None
        """
        if key == keyboard.Key.esc:
            self._cancelled = True

    def _sleep_interruptible(self, seconds: float, step: float = 0.05) -> None:
        """
        Sleep in short slices so cancellation stays responsive.

        Parameters
        ----------
        seconds : float
            Total sleep duration.
        step : float, optional
            Maximum slice length in seconds, by default ``0.05``.

        Returns
        -------
        None
        """
        if seconds <= 0:
            return
        end = time.monotonic() + seconds
        while time.monotonic() < end:
            if self._cancelled:
                return
            time.sleep(min(step, end - time.monotonic()))

    def _prepare_draw_progress(self) -> None:
        """
        Count interpolated draw steps for the progress bar.

        Returns
        -------
        None
        """
        total = 0
        for stroke in self._plan.strokes:
            points = _interpolate_stroke(stroke, min_step=self._pacing.segment_px)
            if len(points) >= 2:
                total += len(points) - 1
        self._total_draw_steps = max(1, total)
        self._completed_draw_steps = 0

    def _advance_draw_progress(self) -> None:
        """
        Emit draw progress as a 0–100 percentage.

        Returns
        -------
        None
        """
        self._completed_draw_steps += 1
        percent = int(
            round(100.0 * self._completed_draw_steps / self._total_draw_steps)
        )
        self.draw_progress.emit(min(100, percent))

    def _cursor_position(self, x: float, y: float) -> Tuple[int, int]:
        """
        Apply tremor offset and return integer screen coordinates.

        Parameters
        ----------
        x : float
            Target X in screen coordinates.
        y : float
            Target Y in screen coordinates.

        Returns
        -------
        tuple of int
            Rounded cursor position after tremor.
        """
        dx, dy = self._tremor.sample()
        return (int(round(x + dx)), int(round(y + dy)))

    def _stroke_label(self, idx: int) -> str:
        """
        Human-readable label for a stroke index.

        Parameters
        ----------
        idx : int
            Stroke index in the plan.

        Returns
        -------
        str
            Short description for progress messages.
        """
        if idx == self._plan.circle_main_index:
            return "circle (main)"
        if idx == self._plan.circle_closure_index:
            return "circle (closure)"
        if self._plan.circle_main_index is not None and idx < self._plan.circle_main_index:
            if idx == 0:
                return "sigil"
            return f"sign {idx}"
        return f"stroke {idx + 1}"

    def _draw_stroke(self, stroke: Stroke) -> None:
        """
        Draw a single stroke with mouse down, move, and mouse up.

        Parameters
        ----------
        stroke : Stroke
            Screen-coordinate polyline.

        Returns
        -------
        None
        """
        pacing = self._pacing
        points = _interpolate_stroke(stroke, min_step=pacing.segment_px)
        if len(points) < 2:
            return

        self._tremor.reset()

        if not self.dry_run:
            self._mouse.position = self._cursor_position(points[0][0], points[0][1])
            self._mouse.press(Button.left)
            self._sleep_interruptible(pacing.press_settle_s)

        for x, y in points[1:]:
            if self._cancelled:
                return
            if not self.dry_run:
                self._mouse.position = self._cursor_position(x, y)
            self._advance_draw_progress()
            self._sleep_interruptible(pacing.point_delay_s)

        self._sleep_interruptible(pacing.release_settle_s)
        if not self.dry_run:
            self._mouse.release(Button.left)

    def _release_mouse(self) -> None:
        """
        Ensure the left mouse button is released after cancel or error.

        Returns
        -------
        None
        """
        if not self.dry_run:
            try:
                self._mouse.release(Button.left)
            except Exception:
                pass
