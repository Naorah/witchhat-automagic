"""Asset path resolution and catalogue listing for sigils and signs."""

from __future__ import annotations

import re
from pathlib import Path
from typing import List

PROJECT_ROOT = Path(__file__).resolve().parent.parent

WEBP_DIR = PROJECT_ROOT / "images" / "webp"
WEBP_SIGILS_DIR = WEBP_DIR / "sigils"
WEBP_SIGNS_DIR = WEBP_DIR / "signs"

PATH_SIGILS_DIR = PROJECT_ROOT / "path" / "sigils"
PATH_SIGNS_DIR = PROJECT_ROOT / "path" / "signs"

# Legacy Inkscape sources (bootstrap / reference)
SIGILS_DIR = PROJECT_ROOT / "images" / "sigils"
SIGNS_DIR = PROJECT_ROOT / "images" / "signs"


def normalize_asset_name(stem: str) -> str:
    """
    Normalize a file stem to PascalCase (e.g. ``column`` → ``Column``).

    Parameters
    ----------
    stem : str
        Raw filename stem, optionally prefixed with ``sigil_`` or ``sign_``.

    Returns
    -------
    str
        Normalized asset name.
    """
    cleaned = stem.strip()
    if cleaned.startswith("sigil_"):
        cleaned = cleaned[len("sigil_") :]
    elif cleaned.startswith("sign_"):
        cleaned = cleaned[len("sign_") :]
    parts = re.split(r"[_\-\s]+", cleaned)
    return "".join(p[:1].upper() + p[1:].lower() for p in parts if p)


def _resolve_asset(directory: Path, name: str) -> Path:
    """
    Resolve an asset name to an SVG path under ``directory``.

    Parameters
    ----------
    directory : Path
        Folder containing ``.svg`` files.
    name : str
        Logical asset name.

    Returns
    -------
    Path
        Best-matching SVG path (may not exist).
    """
    normalized = normalize_asset_name(name)
    exact = directory / f"{normalized}.svg"
    if exact.is_file():
        return exact
    lowered = name.lower()
    for candidate in directory.glob("*.svg"):
        if candidate.stem.lower() == lowered:
            return candidate
    return exact


def _active_dir(kind: str) -> Path:
    """
    Return the preferred SVG directory for sigils or signs.

    Parameters
    ----------
    kind : str
        Either ``"sigil"`` or ``"sign"``.

    Returns
    -------
    Path
        ``path/`` folder when populated, otherwise legacy ``images/``.
    """
    if kind == "sigil":
        if PATH_SIGILS_DIR.is_dir() and any(PATH_SIGILS_DIR.glob("*.svg")):
            return PATH_SIGILS_DIR
        return SIGILS_DIR
    if PATH_SIGNS_DIR.is_dir() and any(PATH_SIGNS_DIR.glob("*.svg")):
        return PATH_SIGNS_DIR
    return SIGNS_DIR


def list_sigils() -> List[str]:
    """
    List available sigil asset names.

    Returns
    -------
    list of str
        Sorted normalized sigil names.
    """
    return sorted(
        normalize_asset_name(p.stem) for p in _active_dir("sigil").glob("*.svg")
    )


def list_signs() -> List[str]:
    """
    List available sign asset names.

    Returns
    -------
    list of str
        Sorted normalized sign names.
    """
    return sorted(
        normalize_asset_name(p.stem) for p in _active_dir("sign").glob("*.svg")
    )


def sigil_path(name: str) -> Path:
    """
    Resolve a sigil name to its SVG file path.

    Parameters
    ----------
    name : str
        Sigil asset name.

    Returns
    -------
    Path
        Path to the sigil SVG.
    """
    return _resolve_asset(_active_dir("sigil"), name)


def sign_path(name: str) -> Path:
    """
    Resolve a sign name to its SVG file path.

    Parameters
    ----------
    name : str
        Sign asset name.

    Returns
    -------
    Path
        Path to the sign SVG.
    """
    return _resolve_asset(_active_dir("sign"), name)


def sign_webp_path(name: str) -> Path:
    """
    Resolve a sign name to its WebP preview image path.

    Parameters
    ----------
    name : str
        Sign asset name.

    Returns
    -------
    Path
        Path to the sign WebP raster.
    """
    return _resolve_asset(WEBP_SIGNS_DIR, name).with_suffix(".webp")
