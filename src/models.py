"""Core data types for spell configuration and drawing plans."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import List, Tuple

Point = Tuple[float, float]
Stroke = List[Point]


class SignDirection(str, Enum):
    """Orientation of a sign relative to the spell circle."""

    INWARD = "inward"
    OUTWARD = "outward"


@dataclass
class SignSlot:
    """One sign placement on the spell ring.

    Attributes
    ----------
    sign_type : str
        Asset name (e.g. ``Column``, ``Crosshair``).
    direction : SignDirection
        Whether the sign faces toward or away from the center.
    rotation_deg : float
        Extra rotation in degrees, from -90 to 90 (0 = default orientation).
    scale_pct : float
        Size multiplier in percent, from 10 to 200 (100 = default size).
    """

    sign_type: str = "Column"
    direction: SignDirection = SignDirection.INWARD
    rotation_deg: float = 0.0
    scale_pct: float = 100.0


@dataclass
class SpellConfig:
    """User-facing spell parameters and overlay geometry.

    Attributes
    ----------
    sigil : str
        Central sigil asset name.
    sign_count : int
        Number of signs evenly spaced on the ring.
    signs : list of SignSlot
        Per-slot sign type and direction.
    circle_diameter_px : int
        Outer circle diameter in screen pixels.
    overlay_center : Point
        Screen coordinates of the spell center.
    overlay_rotation_deg : float
        Rotation of the whole spell around ``overlay_center``.
    sigil_scale_pct : float
        Sigil size multiplier in percent, from 10 to 200 (100 = default size).
    draw_sigil : bool
        Include the central sigil in the draw plan.
    draw_signs : bool
        Include sign strokes in the draw plan.
    draw_circle : bool
        Include the outer circle in the draw plan.
    close_circle : bool
        When drawing the circle, also draw the final closure segment.
    cast_countdown : bool
        When ``True``, wait 3 seconds after cast before drawing starts.
    """

    sigil: str = "Fire"
    sign_count: int = 4
    signs: List[SignSlot] = field(default_factory=list)
    circle_diameter_px: int = 300
    overlay_center: Point = (400, 400)
    overlay_rotation_deg: float = 0.0
    sigil_scale_pct: float = 100.0
    draw_sigil: bool = True
    draw_signs: bool = True
    draw_circle: bool = True
    close_circle: bool = True
    cast_countdown: bool = True

    def ensure_signs(self) -> None:
        """
        Pad or trim ``signs`` so its length matches ``sign_count``.

        Returns
        -------
        None
        """
        while len(self.signs) < self.sign_count:
            self.signs.append(SignSlot())
        if len(self.signs) > self.sign_count:
            self.signs = self.signs[: self.sign_count]


@dataclass
class SpellPlan:
    """Ordered drawing plan with circle split for confirmation.

    Attributes
    ----------
    strokes : list of Stroke
        Screen-coordinate polylines in draw order.
    circle_main_index : int or None
        Index of the main circle arc stroke.
    circle_closure_index : int or None
        Index of the final circle closure stroke.
    """

    strokes: List[Stroke] = field(default_factory=list)
    circle_main_index: int | None = None
    circle_closure_index: int | None = None
