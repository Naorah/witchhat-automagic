"""Thumbnails for sigil and sign asset pickers."""

from __future__ import annotations

from pathlib import Path
from typing import Dict, Optional

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QPainter, QPixmap
from PyQt6.QtSvg import QSvgRenderer

from src.assets import (
    WEBP_SIGILS_DIR,
    WEBP_SIGNS_DIR,
    list_sigils,
    list_signs,
    sigil_path,
    sign_path,
)

GRID_PREVIEW_SIZE = 72
_CACHE: Dict[str, QPixmap] = {}


def _scaled_pixmap(source: QPixmap, size: int) -> QPixmap:
    return source.scaled(
        size,
        size,
        Qt.AspectRatioMode.KeepAspectRatio,
        Qt.TransformationMode.SmoothTransformation,
    )


def _pixmap_from_svg(path: Path, size: int) -> Optional[QPixmap]:
    renderer = QSvgRenderer(str(path))
    if not renderer.isValid():
        return None
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    renderer.render(painter)
    painter.end()
    return pixmap


def _webp_path(webp_dir: Path, name: str, svg_resolver) -> Path:
    normalized_svg = svg_resolver(name)
    candidate = webp_dir / f"{normalized_svg.stem}.webp"
    if candidate.is_file():
        return candidate
    return webp_dir / f"{name}.webp"


def asset_preview_pixmap(
    kind: str,
    name: str,
    size: int = GRID_PREVIEW_SIZE,
) -> Optional[QPixmap]:
    """
    Build a cached thumbnail for a sigil or sign.

    Parameters
    ----------
    kind : str
        ``"sigil"`` or ``"sign"``.
    name : str
        Asset name.
    size : int, optional
        Square thumbnail size in pixels.

    Returns
    -------
    QPixmap or None
        Thumbnail when a WebP or SVG source exists.
    """
    cache_key = f"{kind}:{name}:{size}"
    cached = _CACHE.get(cache_key)
    if cached is not None and not cached.isNull():
        return cached

    if kind == "sigil":
        webp_dir = WEBP_SIGILS_DIR
        svg_path = sigil_path(name)
    else:
        webp_dir = WEBP_SIGNS_DIR
        svg_path = sign_path(name)

    webp_path = _webp_path(webp_dir, name, sigil_path if kind == "sigil" else sign_path)
    if webp_path.is_file():
        loaded = QPixmap(str(webp_path))
        if not loaded.isNull():
            pixmap = _scaled_pixmap(loaded, size)
            _CACHE[cache_key] = pixmap
            return pixmap

    if svg_path.is_file():
        pixmap = _pixmap_from_svg(svg_path, size)
        if pixmap is not None and not pixmap.isNull():
            _CACHE[cache_key] = pixmap
            return pixmap

    return None


def list_assets(kind: str) -> list[str]:
    """Return sorted asset names for ``kind``."""
    if kind == "sigil":
        return list_sigils()
    return list_signs()
