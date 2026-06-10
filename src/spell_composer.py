"""Compose sigil, signs, and circle strokes into a screen-space spell plan."""

from __future__ import annotations

import math
from pathlib import Path
from typing import List

from .assets import sigil_path, sign_path
from .models import SignDirection, SpellConfig, SpellPlan, Stroke
from .point_graph import PointConnectMode, graph_to_drawing_strokes
from .svg_parser import (
    is_point_graph_svg,
    load_svg_point_graph,
    load_svg_strokes,
    normalize_point_graph,
    normalize_strokes,
    transform_strokes,
)

SIGIL_SCALE_RATIO = 0.35
SIGN_SCALE_RATIO = 0.15
SIGN_RING_RATIO = 0.70
CIRCLE_POINTS = 360
CIRCLE_MAIN_FRACTION = 0.97


def _load_normalized_strokes(path: Path) -> List[Stroke]:
    """
    Load strokes from an SVG asset in unit-normalized space.

    Parameters
    ----------
    path : Path
        Sigil or sign SVG path.

    Returns
    -------
    list of Stroke
        Normalized strokes ready for ``transform_strokes``.
    """
    if is_point_graph_svg(path):
        graph = normalize_point_graph(load_svg_point_graph(path))
        return graph_to_drawing_strokes(graph, PointConnectMode.BRANCHES)
    return normalize_strokes(load_svg_strokes(path))


def _circle_strokes(cx: float, cy: float, radius: float) -> Stroke:
    """
    Build a closed circle polyline starting at the top, clockwise.

    Parameters
    ----------
    cx, cy : float
        Circle center in screen coordinates.
    radius : float
        Circle radius in pixels.

    Returns
    -------
    Stroke
        Sampled circle points (``CIRCLE_POINTS + 1`` vertices).
    """
    points: Stroke = []
    for i in range(CIRCLE_POINTS + 1):
        angle = math.radians(-90 + (360.0 * i / CIRCLE_POINTS))
        points.append((cx + radius * math.cos(angle), cy + radius * math.sin(angle)))
    return points


def _rotate_strokes(
    strokes: List[Stroke],
    cx: float,
    cy: float,
    rotation_deg: float,
) -> List[Stroke]:
    """
    Rotate every stroke around ``(cx, cy)`` by ``rotation_deg``.

    Parameters
    ----------
    strokes : list of Stroke
        Screen-coordinate polylines.
    cx, cy : float
        Rotation center.
    rotation_deg : float
        Clockwise rotation in degrees.

    Returns
    -------
    list of Stroke
        Rotated polylines.
    """
    if rotation_deg == 0.0:
        return strokes

    rad = math.radians(rotation_deg)
    cos_a = math.cos(rad)
    sin_a = math.sin(rad)
    rotated: List[Stroke] = []
    for stroke in strokes:
        new_stroke: Stroke = []
        for x, y in stroke:
            dx = x - cx
            dy = y - cy
            new_stroke.append(
                (cx + dx * cos_a - dy * sin_a, cy + dx * sin_a + dy * cos_a)
            )
        rotated.append(new_stroke)
    return rotated


def _split_circle(circle: Stroke) -> tuple[Stroke, Stroke]:
    """
    Split a circle into a main arc and a short closure segment.

    Parameters
    ----------
    circle : Stroke
        Full circle polyline.

    Returns
    -------
    main : Stroke
        Approximately ``CIRCLE_MAIN_FRACTION`` of the circumference.
    closure : Stroke
        Remaining segment used for spell completion.
    """
    total = len(circle) - 1
    main_count = max(2, int(total * CIRCLE_MAIN_FRACTION))
    main = circle[: main_count + 1]
    closure = circle[main_count:]
    if len(closure) < 2:
        closure = [main[-1], circle[-1]]
    return main, closure


def compose_spell(config: SpellConfig) -> SpellPlan:
    """
    Build the spell draw plan in screen coordinates.

    Parameters
    ----------
    config : SpellConfig
        Sigil, signs, circle size, overlay center, and draw toggles.

    Returns
    -------
    SpellPlan
        Ordered strokes respecting ``draw_sigil``, ``draw_signs``,
        ``draw_circle``, and ``close_circle``.
    """
    config.ensure_signs()
    cx, cy = config.overlay_center
    radius = config.circle_diameter_px / 2.0

    plan = SpellPlan()
    strokes: List[Stroke] = []

    if config.draw_sigil:
        sigil_scale = (
            config.circle_diameter_px
            * SIGIL_SCALE_RATIO
            * (config.sigil_scale_pct / 100.0)
        )
        strokes.extend(
            transform_strokes(
                _load_normalized_strokes(sigil_path(config.sigil)),
                sigil_scale,
                0.0,
                cx,
                cy,
            )
        )

    if config.draw_signs:
        sign_scale_base = config.circle_diameter_px * SIGN_SCALE_RATIO
        for i, slot in enumerate(config.signs):
            sign_scale = sign_scale_base * (slot.scale_pct / 100.0)
            angle = -90.0 + (360.0 * i / config.sign_count)
            ring_r = radius * SIGN_RING_RATIO
            rad = math.radians(angle)
            sx = cx + ring_r * math.cos(rad)
            sy = cy + ring_r * math.sin(rad)

            rotation = angle + 90.0 + slot.rotation_deg
            if slot.direction == SignDirection.INWARD:
                rotation += 180.0

            strokes.extend(
                transform_strokes(
                    _load_normalized_strokes(sign_path(slot.sign_type)),
                    sign_scale,
                    rotation,
                    sx,
                    sy,
                )
            )

    if config.draw_circle:
        circle = _circle_strokes(cx, cy, radius)
        circle_main, circle_closure = _split_circle(circle)
        plan.circle_main_index = len(strokes)
        strokes.append(circle_main)
        if config.close_circle:
            plan.circle_closure_index = len(strokes)
            strokes.append(circle_closure)

    if config.overlay_rotation_deg:
        strokes = _rotate_strokes(strokes, cx, cy, config.overlay_rotation_deg)

    plan.strokes = strokes
    return plan
