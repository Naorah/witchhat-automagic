"""Binary search state machine for cast speed limits."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional, Tuple

from src.mouse_drawer import DrawPacing, NORMAL_PACING, TURBO_PACING

TrialResult = Tuple[float, float, bool]  # delay_s, segment_px, success

DELAY_FLOOR_S = 0.00005  # 0.05 ms — lower search bound


@dataclass
class Calibrator:
    """
    Find the fastest reliable pacing via user-confirmed trials.

    Phase 1 searches ``point_delay_s`` with a fixed segment step.
    Phase 2 optionally pushes ``segment_px`` at the best delay found.

    Attributes
    ----------
    delay_lo_s : float
        Lower bound of the delay search range in seconds.
    delay_hi_s : float
        Upper bound of the delay search range in seconds.
    segment_lo_px : float
        Lower bound of the segment-step search range in pixels.
    segment_hi_px : float
        Upper bound of the segment-step search range in pixels.
    fixed_segment_px : float
        Segment step held fixed during phase 1.
    phase : str
        Active phase: ``delay``, ``segment``, or ``done``.
    history : list of tuple
        Recorded trials as ``(delay_s, segment_px, success)``.
    best_pacing : DrawPacing or None
        Best reliable pacing found so far.
    """

    delay_lo_s: float = DELAY_FLOOR_S
    delay_hi_s: float = NORMAL_PACING.point_delay_s
    segment_lo_px: float = 3.0
    segment_hi_px: float = 10.0
    fixed_segment_px: float = TURBO_PACING.segment_px
    phase: str = "delay"
    history: List[TrialResult] = field(default_factory=list)
    best_pacing: Optional[DrawPacing] = None
    _current_delay_s: float = field(default=0.0, init=False)
    _current_segment_px: float = field(default=0.0, init=False)

    def __post_init__(self) -> None:
        """Propose the first trial after initialization."""
        self._propose_next()

    def reset(self) -> None:
        """
        Restart calibration from scratch.

        Returns
        -------
        None
        """
        self.delay_lo_s = DELAY_FLOOR_S
        self.delay_hi_s = NORMAL_PACING.point_delay_s
        self.segment_lo_px = 3.0
        self.segment_hi_px = 10.0
        self.fixed_segment_px = TURBO_PACING.segment_px
        self.phase = "delay"
        self.history.clear()
        self.best_pacing = None
        self._propose_next()

    def set_fixed_segment(self, segment_px: float) -> None:
        """
        Update the segment step used during the delay-search phase.

        Parameters
        ----------
        segment_px : float
            Interpolation step in pixels, clamped to 2–16.

        Returns
        -------
        None
        """
        self.fixed_segment_px = max(2.0, min(16.0, segment_px))
        if self.phase == "delay":
            self._propose_next()

    def current_trial(self) -> Tuple[float, float]:
        """
        Return the active trial parameters.

        Returns
        -------
        tuple of float
            ``(point_delay_s, segment_px)`` for the current trial.
        """
        return self._current_delay_s, self._current_segment_px

    def current_pacing(self) -> DrawPacing:
        """
        Build a full pacing profile for the active trial.

        Returns
        -------
        DrawPacing
            Pacing profile scaled from the current delay and segment.
        """
        delay, segment = self.current_trial()
        ratio = delay / NORMAL_PACING.point_delay_s
        return DrawPacing(
            point_delay_s=delay,
            stroke_delay_s=max(0.002, 0.004 * ratio),
            segment_px=segment,
            press_settle_s=max(0.002, NORMAL_PACING.press_settle_s * ratio),
            release_settle_s=max(0.001, NORMAL_PACING.release_settle_s * ratio),
        )

    def record(self, success: bool) -> str:
        """
        Record the latest trial and advance the search.

        Parameters
        ----------
        success : bool
            Whether the game detected the stroke correctly.

        Returns
        -------
        str
            Short status message for the UI.
        """
        delay, segment = self.current_trial()
        self.history.append((delay, segment, success))

        if self.phase == "delay":
            if success:
                self.delay_hi_s = delay
                self.best_pacing = self.current_pacing()
            else:
                self.delay_lo_s = delay

            if self._delay_converged():
                if self.best_pacing is None:
                    return (
                        "No reliable delay found — widen the upper bound "
                        "or confirm a successful trial."
                    )
                self.phase = "segment"
                self.segment_lo_px = self.best_pacing.segment_px
                self.segment_hi_px = min(16.0, self.best_pacing.segment_px + 6.0)
                self._propose_segment_trial()
                return (
                    f"Delay limit ≈ {self.best_pacing.point_delay_s * 1000:.2f} ms/pt. "
                    "Phase 2: segment."
                )

            self._propose_delay_trial()
            return "Next trial (delay)."

        if success:
            self.segment_lo_px = segment
            self.best_pacing = self.current_pacing()
        else:
            self.segment_hi_px = segment

        if self._segment_converged():
            return "Calibration complete."

        self._propose_segment_trial()
        return "Next trial (segment)."

    def push_faster(self) -> str:
        """
        Resume delay search below the current best profile.

        Returns
        -------
        str
            Status message for the UI.
        """
        if not self.best_pacing:
            return "No baseline profile — confirm a successful trial first."

        floor = min(self.delay_lo_s, DELAY_FLOOR_S)
        self.phase = "delay"
        self.delay_lo_s = floor
        self.delay_hi_s = self.best_pacing.point_delay_s
        self.fixed_segment_px = self.best_pacing.segment_px
        self._propose_delay_trial()
        return (
            f"Searching below {self.delay_hi_s * 1000:.3f} ms/pt "
            f"(floor {floor * 1000:.3f} ms)…"
        )

    def is_done(self) -> bool:
        """
        Return whether both search phases have converged.

        Returns
        -------
        bool
            ``True`` when phase is ``done``.
        """
        return self.phase == "done"

    def summary(self) -> str:
        """
        Build a human-readable recommendation and ``TURBO_PACING`` snippet.

        Returns
        -------
        str
            Summary text for the result panel and clipboard.
        """
        if not self.best_pacing:
            return (
                "No reliable profile yet. Run trials and confirm successes."
            )

        p = self.best_pacing
        extra = ""
        if self.phase == "done":
            extra = (
                "\n\nThink you can go faster? "
                "Use \"Push faster\" to search below this delay."
            )
        return (
            f"Reliable limit: {p.point_delay_s * 1000:.3f} ms/pt, "
            f"step {p.segment_px:.1f} px"
            f"{extra}\n\n"
            f"TURBO_PACING = DrawPacing(\n"
            f"    point_delay_s={p.point_delay_s:.4f},\n"
            f"    stroke_delay_s={p.stroke_delay_s:.4f},\n"
            f"    segment_px={p.segment_px:.1f},\n"
            f"    press_settle_s={p.press_settle_s:.4f},\n"
            f"    release_settle_s={p.release_settle_s:.4f},\n"
            f")"
        )

    def _delay_converged(self) -> bool:
        """Return whether the delay search interval is narrow enough."""
        span = self.delay_hi_s - self.delay_lo_s
        if self.delay_hi_s < 0.0005:
            return span < 0.00003
        return span < 0.00008

    def _segment_converged(self) -> bool:
        """Return whether the segment search has finished."""
        if (self.segment_hi_px - self.segment_lo_px) < 0.6:
            self.phase = "done"
            return True
        return False

    def _propose_next(self) -> None:
        """Propose the next trial for the active phase."""
        if self.phase == "delay":
            self._propose_delay_trial()
        elif self.phase == "segment":
            self._propose_segment_trial()
        else:
            self._current_delay_s = self.best_pacing.point_delay_s if self.best_pacing else 0.0
            self._current_segment_px = self.best_pacing.segment_px if self.best_pacing else 0.0

    def _propose_delay_trial(self) -> None:
        """Set the midpoint of the current delay search range."""
        self._current_delay_s = (self.delay_lo_s + self.delay_hi_s) / 2.0
        self._current_segment_px = self.fixed_segment_px

    def _propose_segment_trial(self) -> None:
        """Set the midpoint of the segment search at the best delay."""
        assert self.best_pacing is not None
        self._current_delay_s = self.best_pacing.point_delay_s
        self._current_segment_px = (self.segment_lo_px + self.segment_hi_px) / 2.0
