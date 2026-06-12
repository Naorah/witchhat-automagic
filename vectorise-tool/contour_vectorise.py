"""Contour-based raster to SVG vectorisation."""

from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, List, Sequence, Tuple

import cv2
import numpy as np
from PIL import Image

from src.webp_to_path import SUPPORTED_INPUT, _clean_mask, _composite_grayscale, _image_scale

Point = Tuple[float, float]
Contour = List[Point]

VIEWBOX_SIZE = 100.0
VIEWBOX_PADDING = 5.0
DEFAULT_EPSILON_RATIO = 0.006
DEFAULT_SMOOTH = 0.5
MAX_SMOOTH_ITERATIONS = 4
MIN_AREA_RATIO = 0.0001
MIN_PERIMETER_RATIO = 0.01


def smooth_degree_to_iterations(degree: float) -> int:
    """
    Map a smoothing degree in ``[0, 1]`` to Chaikin iteration count.

    Parameters
    ----------
    degree : float
        Smoothing intensity from 0 (none) to 1 (maximum).

    Returns
    -------
    int
        Number of Chaikin passes to apply.
    """
    clamped = max(0.0, min(1.0, degree))
    return int(round(clamped * MAX_SMOOTH_ITERATIONS))


@dataclass
class VectoriseResult:
    """
    Summary of a contour vectorisation run.

    Attributes
    ----------
    source : Path
        Input raster file.
    output : Path
        Written SVG path.
    contour_count : int
        Number of closed contours in the output.
    point_count : int
        Total number of vertices across all contours.
    """

    source: Path
    output: Path
    contour_count: int
    point_count: int


def load_rgba(image_path: Path) -> np.ndarray:
    """
    Load a raster image as an RGBA numpy array.

    Parameters
    ----------
    image_path : Path
        Path to a supported image file.

    Returns
    -------
    np.ndarray
        RGBA image array.
    """
    return np.array(Image.open(image_path).convert("RGBA"))


def binarize(rgba: np.ndarray, threshold: float) -> np.ndarray:
    """
    Build a cleaned binary foreground mask from an RGBA image.

    Dark pixels below ``threshold`` (0–1) become foreground.

    Parameters
    ----------
    rgba : np.ndarray
        RGBA image array.
    threshold : float
        Grayscale cutoff in ``[0, 1]``.

    Returns
    -------
    np.ndarray
        Binary mask with foreground at 255.
    """
    gray = _composite_grayscale(rgba)
    level = int(max(0.0, min(1.0, threshold)) * 255)
    mask = np.where(gray < level, 255, 0).astype(np.uint8)
    return _clean_mask(mask)


def find_contours(mask: np.ndarray) -> List[np.ndarray]:
    """
    Detect closed contours in a binary mask.

    Parameters
    ----------
    mask : np.ndarray
        Binary foreground mask.

    Returns
    -------
    list of np.ndarray
        OpenCV contours above minimum area and perimeter thresholds.
    """
    contours, _hierarchy = cv2.findContours(mask, cv2.RETR_TREE, cv2.CHAIN_APPROX_NONE)
    scale = _image_scale(mask)
    min_area = (scale * scale) * MIN_AREA_RATIO
    min_perim = scale * MIN_PERIMETER_RATIO

    kept: List[np.ndarray] = []
    for contour in contours:
        area = cv2.contourArea(contour)
        perim = cv2.arcLength(contour, True)
        if area < min_area and perim < min_perim:
            continue
        kept.append(contour)
    return kept


def rdp_simplify(contour: np.ndarray, epsilon: float) -> Contour:
    """
    Simplify a closed contour with Ramer-Douglas-Peucker.

    Parameters
    ----------
    contour : np.ndarray
        OpenCV contour points.
    epsilon : float
        Maximum deviation allowed for simplified points.

    Returns
    -------
    Contour
        Simplified closed polyline with at least three points when possible.
    """
    if len(contour) < 3:
        return [(float(p[0][0]), float(p[0][1])) for p in contour]
    approx = cv2.approxPolyDP(contour, epsilon, True)
    points = [(float(p[0][0]), float(p[0][1])) for p in approx]
    return points if len(points) >= 3 else [(float(p[0][0]), float(p[0][1])) for p in contour]


def _interior_angle_deg(points: Contour, index: int) -> float:
    """
    Measure the interior angle at a polygon vertex in degrees.

    Parameters
    ----------
    points : Contour
        Closed polygon vertices.
    index : int
        Vertex index to measure.

    Returns
    -------
    float
        Interior angle in ``(0, 180]`` degrees.
    """
    n = len(points)
    prev = points[(index - 1) % n]
    curr = points[index]
    nxt = points[(index + 1) % n]
    v1 = (prev[0] - curr[0], prev[1] - curr[1])
    v2 = (nxt[0] - curr[0], nxt[1] - curr[1])
    len1 = math.hypot(v1[0], v1[1])
    len2 = math.hypot(v2[0], v2[1])
    if len1 < 1e-9 or len2 < 1e-9:
        return 180.0
    dot = (v1[0] * v2[0] + v1[1] * v2[1]) / (len1 * len2)
    dot = max(-1.0, min(1.0, dot))
    return math.degrees(math.acos(dot))


def chaikin_smooth(
    points: Contour,
    iterations: int,
    *,
    sharp_angle_deg: float = 150.0,
) -> Contour:
    """
    Smooth polygon corners with Chaikin's corner-cutting algorithm.

    Sharp vertices (interior angle below ``sharp_angle_deg``) are preserved so
    arrow tips and other acute points are not rounded away.

    Parameters
    ----------
    points : Contour
        Closed polygon vertices.
    iterations : int
        Number of subdivision passes (0 disables smoothing).
    sharp_angle_deg : float, optional
        Angles below this threshold are kept sharp.

    Returns
    -------
    Contour
        Smoothed closed polygon.
    """
    if len(points) < 3 or iterations <= 0:
        return list(points)

    result = list(points)
    for _ in range(iterations):
        n = len(result)
        subdivided: Contour = []
        for i in range(n):
            x0, y0 = result[i]
            x1, y1 = result[(i + 1) % n]
            sharp0 = _interior_angle_deg(result, i) < sharp_angle_deg
            sharp1 = _interior_angle_deg(result, (i + 1) % n) < sharp_angle_deg

            if sharp0:
                subdivided.append((x0, y0))
            else:
                subdivided.append((0.75 * x0 + 0.25 * x1, 0.75 * y0 + 0.25 * y1))

            if sharp1:
                subdivided.append((x1, y1))
            else:
                subdivided.append((0.25 * x0 + 0.75 * x1, 0.25 * y0 + 0.75 * y1))

        result = subdivided
    return result


def _dedupe_consecutive_points(points: Contour, min_dist: float = 0.01) -> Contour:
    """
    Remove consecutive duplicate or near-duplicate vertices.

    Parameters
    ----------
    points : Contour
        Input polyline.
    min_dist : float, optional
        Minimum distance between retained points.

    Returns
    -------
    Contour
        Deduplicated polyline.
    """
    if not points:
        return []
    kept: Contour = [points[0]]
    for point in points[1:]:
        if math.hypot(point[0] - kept[-1][0], point[1] - kept[-1][1]) > min_dist:
            kept.append(point)
    return kept


def optimize_contour(
    contour: np.ndarray,
    scale: float,
    *,
    epsilon_ratio: float = DEFAULT_EPSILON_RATIO,
    smooth_iterations: int = 2,
) -> Contour:
    """
    Run RDP simplification and Chaikin smoothing on one contour.

    Parameters
    ----------
    contour : np.ndarray
        Raw OpenCV contour.
    scale : float
        Characteristic image scale in pixels.
    epsilon_ratio : float, optional
        RDP epsilon as a fraction of ``scale``.
    smooth_iterations : int, optional
        Chaikin passes applied after RDP.

    Returns
    -------
    Contour
        Optimised closed contour.
    """
    epsilon = max(0.8, scale * epsilon_ratio)
    simplified = rdp_simplify(contour, epsilon)
    smoothed = chaikin_smooth(simplified, smooth_iterations)
    return _dedupe_consecutive_points(smoothed)


def normalize_contours(
    contours: Sequence[Contour],
    image_size: Tuple[int, int],
) -> List[Contour]:
    """
    Scale and center contours into the standard SVG viewBox.

    Uses the full raster canvas (width × height), not the contour bounding box,
    so glyphs keep the same margins as in the source image and sharp tips near
    the canvas edge are not pushed against the viewBox border.

    Parameters
    ----------
    contours : sequence of Contour
        Contours in image pixel coordinates.
    image_size : tuple of (int, int)
        Source image ``(width, height)`` in pixels.

    Returns
    -------
    list of Contour
        Contours mapped into ``[0, VIEWBOX_SIZE]`` with padding.
    """
    if not contours:
        return []

    width, height = image_size
    cx = width / 2
    cy = height / 2
    size = max(width, height) or 1.0

    usable = VIEWBOX_SIZE - 2 * VIEWBOX_PADDING
    scale = usable / size
    offset = VIEWBOX_SIZE / 2

    normalized: List[Contour] = []
    for contour in contours:
        normalized.append(
            [
                (offset + (x - cx) * scale, offset + (y - cy) * scale)
                for x, y in contour
            ]
        )
    return normalized


def _format_point(x: float, y: float) -> str:
    return f"{x:.2f},{y:.2f}"


def _contour_to_subpath(contour: Contour) -> str:
    if len(contour) < 3:
        return ""
    parts = [f"M{_format_point(contour[0][0], contour[0][1])}"]
    for x, y in contour[1:]:
        parts.append(f"L{_format_point(x, y)}")
    parts.append("Z")
    return " ".join(parts)


def contours_to_svg(contours: Sequence[Contour], name: str) -> str:
    """
    Serialize closed contours to a compact filled SVG document.

    Parameters
    ----------
    contours : sequence of Contour
        Normalised closed contours.
    name : str
        Title embedded in the SVG.

    Returns
    -------
    str
        SVG markup as a Unicode string.
    """
    subpaths = [_contour_to_subpath(c) for c in contours]
    d = " ".join(part for part in subpaths if part)
    if not d:
        raise ValueError("No drawable contours")

    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {VIEWBOX_SIZE:g} {VIEWBOX_SIZE:g}">'
        f"<title>{name}</title>"
        f'<path fill="#000" fill-rule="evenodd" d="{d}"/>'
        f"</svg>"
    )


def write_contour_svg(contours: Sequence[Contour], output_path: Path, name: str) -> None:
    """
    Write filled contour SVG to disk.

    Parameters
    ----------
    contours : sequence of Contour
        Normalised closed contours.
    output_path : Path
        Destination file path.
    name : str
        Title embedded in the SVG.

    Returns
    -------
    None
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(contours_to_svg(contours, name), encoding="utf-8")


def save_debug_mask(mask: np.ndarray, image_path: Path, debug_dir: Path) -> None:
    """
    Save a binary mask preview for debugging.

    Parameters
    ----------
    mask : np.ndarray
        Binary mask to save.
    image_path : Path
        Source image path (used for the output filename).
    debug_dir : Path
        Directory that receives ``<stem>_mask.png``.

    Returns
    -------
    None
    """
    debug_dir.mkdir(parents=True, exist_ok=True)
    out = debug_dir / f"{image_path.stem}_mask.png"
    cv2.imwrite(str(out), mask)


def vectorise_raster(
    rgba: np.ndarray,
    *,
    threshold: float = 0.450,
    epsilon_ratio: float = DEFAULT_EPSILON_RATIO,
    smooth: float = DEFAULT_SMOOTH,
) -> Tuple[List[Contour], np.ndarray]:
    """
    Convert an RGBA raster to optimised normalised contours.

    Parameters
    ----------
    rgba : np.ndarray
        RGBA image array.
    threshold : float, optional
        Binarisation cutoff in ``[0, 1]``.
    epsilon_ratio : float, optional
        RDP epsilon factor relative to image scale.
    smooth : float, optional
        Corner smoothing degree in ``[0, 1]`` (0 = none, 1 = maximum).

    Returns
    -------
    tuple of (list of Contour, np.ndarray)
        Normalised contours and the binary mask used for detection.
    """
    mask = binarize(rgba, threshold)
    scale = _image_scale(mask)
    smooth_iterations = smooth_degree_to_iterations(smooth)
    raw_contours = find_contours(mask)
    optimised = [
        optimize_contour(
            contour,
            scale,
            epsilon_ratio=epsilon_ratio,
            smooth_iterations=smooth_iterations,
        )
        for contour in raw_contours
    ]
    image_size = (rgba.shape[1], rgba.shape[0])
    return normalize_contours(optimised, image_size), mask


def vectorise_file(
    image_path: Path,
    output_path: Path,
    *,
    threshold: float = 0.450,
    epsilon_ratio: float = DEFAULT_EPSILON_RATIO,
    smooth: float = DEFAULT_SMOOTH,
    debug: bool = False,
    debug_dir: Path | None = None,
) -> VectoriseResult:
    """
    Vectorise one raster file to a filled contour SVG.

    Parameters
    ----------
    image_path : Path
        Source raster path.
    output_path : Path
        Destination SVG path.
    threshold : float, optional
        Binarisation cutoff in ``[0, 1]``.
    epsilon_ratio : float, optional
        RDP epsilon factor relative to image scale.
    smooth : float, optional
        Corner smoothing degree in ``[0, 1]`` (0 = none, 1 = maximum).
    debug : bool, optional
        If ``True``, write the binary mask used for contour detection.
    debug_dir : Path or None, optional
        Directory for debug images. Defaults to ``output_path.parent / "_debug"``.

    Returns
    -------
    VectoriseResult
        Summary of the conversion.

    Raises
    ------
    ValueError
        If no contours are detected in the input image.
    """
    rgba = load_rgba(image_path)
    contours, mask = vectorise_raster(
        rgba,
        threshold=threshold,
        epsilon_ratio=epsilon_ratio,
        smooth=smooth,
    )
    if not contours:
        raise ValueError(f"No contour detected in {image_path.name}")

    if debug:
        target = debug_dir if debug_dir is not None else output_path.parent / "_debug"
        save_debug_mask(mask, image_path, target)

    write_contour_svg(contours, output_path, output_path.stem)
    point_count = sum(len(c) for c in contours)
    return VectoriseResult(
        source=image_path,
        output=output_path,
        contour_count=len(contours),
        point_count=point_count,
    )


def iter_raster_files(folder: Path) -> Iterable[Path]:
    """
    Iterate supported raster files in a directory.

    Parameters
    ----------
    folder : Path
        Directory to scan.

    Returns
    -------
    Iterable of Path
        Sorted paths to supported image files.
    """
    if not folder.is_dir():
        return []
    return sorted(
        p for p in folder.iterdir() if p.is_file() and p.suffix.lower() in SUPPORTED_INPUT
    )
