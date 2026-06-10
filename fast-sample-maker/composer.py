"""Compose a single sigil or sign into screen-space strokes."""

from __future__ import annotations

from dataclasses import dataclass
from typing import List

from src.assets import sigil_path, sign_path
from src.models import Point, SpellPlan, Stroke
from src.spell_composer import (
    SIGIL_SCALE_RATIO,
    SIGN_SCALE_RATIO,
    _load_normalized_strokes,
)
from src.svg_parser import transform_strokes


@dataclass
class SampleConfig:
    """Parameters for drawing one sigil or sign sample."""

    kind: str = "sigil"
    name: str = "Fire"
    rotation_deg: float = 0.0
    scale_pct: float = 100.0
    overlay_center: Point = (400, 400)
    base_diameter_px: int = 300


def compose_sample(config: SampleConfig) -> SpellPlan:
    """
    Build a draw plan for a single centered asset.

    Parameters
    ----------
    config : SampleConfig
        Asset kind, name, rotation, scale, and screen center.

    Returns
    -------
    SpellPlan
        Strokes ready for preview or mouse drawing.
    """
    cx, cy = config.overlay_center
    if config.kind == "sigil":
        scale = (
            config.base_diameter_px
            * SIGIL_SCALE_RATIO
            * (config.scale_pct / 100.0)
        )
        path = sigil_path(config.name)
    else:
        scale = (
            config.base_diameter_px
            * SIGN_SCALE_RATIO
            * (config.scale_pct / 100.0)
        )
        path = sign_path(config.name)

    strokes: List[Stroke] = transform_strokes(
        _load_normalized_strokes(path),
        scale,
        config.rotation_deg,
        cx,
        cy,
    )
    return SpellPlan(strokes=strokes)
