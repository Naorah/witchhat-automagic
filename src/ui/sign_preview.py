"""Sign thumbnails for combo box items."""

from __future__ import annotations

from pathlib import Path
from typing import Dict, Optional

from PyQt6.QtCore import Qt, QSize
from PyQt6.QtGui import QIcon, QPainter, QPixmap
from PyQt6.QtSvg import QSvgRenderer
from PyQt6.QtWidgets import QComboBox

from ..assets import list_signs, sign_path, sign_webp_path

PREVIEW_SIZE = 22
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


def sign_preview_pixmap(name: str, size: int = PREVIEW_SIZE) -> Optional[QPixmap]:
    """
    Build a cached thumbnail for a sign asset name.

    Parameters
    ----------
    name : str
        Sign asset name.
    size : int, optional
        Square thumbnail size in pixels, by default ``PREVIEW_SIZE``.

    Returns
    -------
    QPixmap or None
        Thumbnail when a WebP or SVG source exists.
    """
    cache_key = f"{name}:{size}"
    cached = _CACHE.get(cache_key)
    if cached is not None and not cached.isNull():
        return cached

    webp_path = sign_webp_path(name)
    if webp_path.is_file():
        loaded = QPixmap(str(webp_path))
        if not loaded.isNull():
            pixmap = _scaled_pixmap(loaded, size)
            _CACHE[cache_key] = pixmap
            return pixmap

    svg_path = sign_path(name)
    if svg_path.is_file():
        pixmap = _pixmap_from_svg(svg_path, size)
        if pixmap is not None and not pixmap.isNull():
            _CACHE[cache_key] = pixmap
            return pixmap

    return None


def sign_preview_icon(name: str, size: int = PREVIEW_SIZE) -> QIcon:
    """
    Build a ``QIcon`` thumbnail for a sign asset name.

    Parameters
    ----------
    name : str
        Sign asset name.
    size : int, optional
        Square thumbnail size in pixels, by default ``PREVIEW_SIZE``.

    Returns
    -------
    QIcon
        Icon when a source exists, otherwise an empty icon.
    """
    pixmap = sign_preview_pixmap(name, size)
    if pixmap is None:
        return QIcon()
    return QIcon(pixmap)


def populate_sign_combo(combo: QComboBox, size: int = PREVIEW_SIZE) -> None:
    """
    Fill a combo box with all signs and their preview icons.

    Parameters
    ----------
    combo : QComboBox
        Target combo box.
    size : int, optional
        Square thumbnail size in pixels, by default ``PREVIEW_SIZE``.

    Returns
    -------
    None
    """
    combo.clear()
    combo.setIconSize(QSize(size, size))
    for name in list_signs():
        combo.addItem(sign_preview_icon(name, size), name, name)
