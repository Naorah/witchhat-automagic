"""Test stroke patterns for cast speed calibration."""

from __future__ import annotations

import math

from src.models import Point, SpellPlan, Stroke

PatternName = str


def _line(cx: float, cy: float, half_len: float) -> Stroke:
    return [(cx - half_len, cy), (cx + half_len, cy)]


def _vertical(cx: float, cy: float, half_len: float) -> Stroke:
    return [(cx, cy - half_len), (cx, cy + half_len)]


def _arc(cx: float, cy: float, radius: float, points: int = 48) -> Stroke:
    stroke: Stroke = []
    for i in range(points + 1):
        angle = math.radians(-90 + (270.0 * i / points))
        stroke.append((cx + radius * math.cos(angle), cy + radius * math.sin(angle)))
    return stroke


def build_test_plan(
    center: Point,
    diameter_px: int,
    pattern: PatternName,
) -> SpellPlan:
    """
    Build a short draw plan for speed calibration.

    Parameters
    ----------
    center : Point
        Screen center of the test shape.
    diameter_px : int
        Overall test size in pixels.
    pattern : str
        ``line``, ``cross``, or ``arc``.

    Returns
    -------
    SpellPlan
        One or two strokes exercising detection.
    """
    cx, cy = center
    half = diameter_px / 2.0

    if pattern == "cross":
        return SpellPlan(strokes=[_line(cx, cy, half), _vertical(cx, cy, half)])

    if pattern == "arc":
        return SpellPlan(strokes=[_arc(cx, cy, half * 0.85)])

    return SpellPlan(strokes=[_line(cx, cy, half)])
