"""Raster-to-SVG conversion via grayscale, binarization, and skeletonization."""

from __future__ import annotations

import json
import math
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, List, Sequence, Tuple

import cv2
import numpy as np
from PIL import Image

from .assets import (
    PATH_SIGILS_DIR,
    PATH_SIGNS_DIR,
    WEBP_DIR,
    WEBP_SIGILS_DIR,
    WEBP_SIGNS_DIR,
    normalize_asset_name,
)
from .models import Stroke
from .svg_parser import load_svg_strokes

Point = Tuple[float, float]
VIEWBOX_SIZE = 100.0
VIEWBOX_PADDING = 5.0
MIN_STROKE_LENGTH_RATIO = 0.015
RDP_EPSILON_RATIO = 0.006
PARALLEL_DEDUPE_RATIO = 0.014
MAX_POINTS_PER_STROKE = 48
MIN_BRANCH_LENGTH_RATIO = 0.006
RESAMPLE_STEP = 2.0
DEBUG_DIR = WEBP_DIR / "_debug"

SUPPORTED_INPUT = {".webp", ".png", ".jpg", ".jpeg"}

_NEIGHBORS_8 = (
    (-1, -1),
    (0, -1),
    (1, -1),
    (-1, 0),
    (1, 0),
    (-1, 1),
    (0, 1),
    (1, 1),
)


@dataclass
class ConversionResult:
    """
    Summary of a raster or SVG-to-stroke conversion.

    Attributes
    ----------
    source : Path
        Input file that was converted.
    output : Path
        Path to the written stroke SVG.
    stroke_count : int
        Number of polylines (strokes) in the output.
    vertex_count : int
        Total number of points across all strokes.
    branch_count : int
        Number of skeleton branches retained (same as stroke_count).
    mode : str
        Drawing mode tag stored in the output SVG.
    """

    source: Path
    output: Path
    stroke_count: int
    vertex_count: int = 0
    branch_count: int = 0
    mode: str = "skeleton-strokes"


def _ensure_dirs() -> None:
    """
    Create output directories for sigils and signs if they do not exist.

    Returns
    -------
    None
    """
    for d in (WEBP_SIGILS_DIR, WEBP_SIGNS_DIR, PATH_SIGILS_DIR, PATH_SIGNS_DIR):
        d.mkdir(parents=True, exist_ok=True)


def _composite_grayscale(rgba: np.ndarray) -> np.ndarray:
    """
    Alpha-composite an RGBA image on white, then convert to grayscale.

    Stabilizes thresholding for images with transparency.

    Parameters
    ----------
    rgba : np.ndarray
        RGBA image array with shape ``(height, width, 4)``.

    Returns
    -------
    np.ndarray
        Single-channel grayscale image.
    """
    alpha = rgba[:, :, 3].astype(np.float32) / 255.0
    rgb = rgba[:, :, :3].astype(np.float32)
    background = np.full_like(rgb, 255.0)
    composited = rgb * alpha[..., None] + background * (1.0 - alpha[..., None])
    gray = cv2.cvtColor(composited.astype(np.uint8), cv2.COLOR_RGB2GRAY)
    return gray


def _image_scale(mask: np.ndarray) -> float:
    """
    Compute a characteristic scale for an image mask.

    Parameters
    ----------
    mask : np.ndarray
        Binary or grayscale mask.

    Returns
    -------
    float
        Diagonal length of the mask bounding box in pixels.
    """
    h, w = mask.shape[:2]
    return math.hypot(w, h)


def _clean_mask(mask: np.ndarray) -> np.ndarray:
    """
    Smooth mask morphology without destroying thin strokes.

    Parameters
    ----------
    mask : np.ndarray
        Binary foreground mask.

    Returns
    -------
    np.ndarray
        Morphologically cleaned binary mask.
    """
    if not np.any(mask):
        return mask
    small = cv2.getStructuringElement(cv2.MORPH_CROSS, (3, 3))
    fg_ratio = float(np.count_nonzero(mask)) / mask.size

    if fg_ratio < 0.025:
        closed = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, small, iterations=1)
        return cv2.dilate(closed, small, iterations=1)

    scale = _image_scale(mask)
    k = max(3, min(9, int(scale * 0.010) | 1))
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (k, k))
    closed = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel, iterations=1)
    return cv2.dilate(closed, small, iterations=1)


def _score_mask(mask: np.ndarray) -> float:
    """
    Score a binary mask for suitability in stroke extraction.

    Parameters
    ----------
    mask : np.ndarray
        Binary foreground mask.

    Returns
    -------
    float
        Score in ``[0, 1]`` for usable masks, or ``-1.0`` for unusable masks.
    """
    total = mask.size
    fg = int(np.count_nonzero(mask))
    if fg == 0 or fg == total:
        return -1.0
    ratio = fg / total
    if ratio < 0.0002 or ratio > 0.85:
        return -1.0
    # Thin strokes (crosshair): small ratio; filled icons: larger ratio
    ideal = 0.12 if ratio > 0.02 else 0.008
    return 1.0 - min(abs(ratio - ideal), 1.0)


def _generate_binary_masks(rgba: np.ndarray) -> List[np.ndarray]:
    """
    Generate and rank candidate binary masks from an RGBA raster.

    Parameters
    ----------
    rgba : np.ndarray
        RGBA image array.

    Returns
    -------
    list of np.ndarray
        Unique binary masks sorted by quality score (best first).
    """
    gray = _composite_grayscale(rgba)
    masks: List[np.ndarray] = []

    alpha = rgba[:, :, 3]
    if alpha.min() < 250:
        alpha_mask = np.where(alpha > 32, 255, 0).astype(np.uint8)
        masks.append(_clean_mask(alpha_mask))

    dark_ink = np.where(gray < 200, 255, 0).astype(np.uint8)
    masks.append(_clean_mask(dark_ink))

    # Light ink on composited white background (e.g. pale gray strokes)
    pale_ink = np.where(gray < 250, 255, 0).astype(np.uint8)
    masks.append(_clean_mask(pale_ink))

    _, otsu_inv = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    masks.append(_clean_mask(otsu_inv))

    _, otsu = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    masks.append(_clean_mask(otsu))

    adaptive = cv2.adaptiveThreshold(
        gray,
        255,
        cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
        cv2.THRESH_BINARY_INV,
        11,
        2,
    )
    masks.append(_clean_mask(adaptive))

    unique: List[np.ndarray] = []
    seen: set[bytes] = set()
    scored = sorted(
        ((_score_mask(m), m) for m in masks),
        key=lambda item: item[0],
        reverse=True,
    )
    for _score, mask in scored:
        digest = mask.tobytes()
        if digest in seen:
            continue
        seen.add(digest)
        if _score >= 0 or not unique:
            unique.append(mask)
    return unique


def _morphological_skeleton(mask: np.ndarray) -> np.ndarray:
    """
    Compute a morphological skeleton of a binary mask.

    Parameters
    ----------
    mask : np.ndarray
        Binary foreground mask.

    Returns
    -------
    np.ndarray
        Single-pixel-wide skeleton mask.
    """
    binary = (mask > 0).astype(np.uint8) * 255
    skeleton = np.zeros(binary.shape, np.uint8)
    element = cv2.getStructuringElement(cv2.MORPH_CROSS, (3, 3))
    temp = binary.copy()
    while True:
        eroded = cv2.erode(temp, element)
        opened = cv2.morphologyEx(eroded, cv2.MORPH_OPEN, element)
        subset = cv2.subtract(eroded, opened)
        skeleton = cv2.bitwise_or(skeleton, subset)
        temp = eroded
        if cv2.countNonZero(temp) == 0:
            break
    return skeleton


def _skeleton_degree(y: int, x: int, skel: np.ndarray) -> int:
    """
    Count foreground neighbors of a skeleton pixel.

    Parameters
    ----------
    y : int
        Row index of the pixel.
    x : int
        Column index of the pixel.
    skel : np.ndarray
        Binary skeleton image.

    Returns
    -------
    int
        Number of 8-connected foreground neighbors.
    """
    h, w = skel.shape
    count = 0
    for dx, dy in _NEIGHBORS_8:
        nx, ny = x + dx, y + dy
        if 0 <= nx < w and 0 <= ny < h and skel[ny, nx]:
            count += 1
    return count


def _skeleton_neighbors(skel: np.ndarray, x: int, y: int) -> List[Tuple[int, int]]:
    """
    List 8-connected foreground neighbors of a skeleton pixel.

    Parameters
    ----------
    skel : np.ndarray
        Binary skeleton image.
    x : int
        Column index of the pixel.
    y : int
        Row index of the pixel.

    Returns
    -------
    list of tuple of (int, int)
        Neighbor coordinates as ``(x, y)`` pairs.
    """
    h, w = skel.shape
    result: List[Tuple[int, int]] = []
    for dx, dy in _NEIGHBORS_8:
        nx, ny = x + dx, y + dy
        if 0 <= nx < w and 0 <= ny < h and skel[ny, nx]:
            result.append((nx, ny))
    return result


def _edge_key(a: Tuple[int, int], b: Tuple[int, int]) -> Tuple[Tuple[int, int], Tuple[int, int]]:
    """
    Build a canonical undirected edge key from two pixel coordinates.

    Parameters
    ----------
    a : tuple of (int, int)
        First endpoint ``(x, y)``.
    b : tuple of (int, int)
        Second endpoint ``(x, y)``.

    Returns
    -------
    tuple of (tuple of (int, int), tuple of (int, int))
        Ordered pair of endpoints for set membership.
    """
    return (a, b) if a <= b else (b, a)


def _skeleton_to_strokes(skeleton: np.ndarray) -> List[Stroke]:
    """
    Decompose a skeleton into ordered stroke branches.

    Handles junctions, loops, and endpoints by walking edges between
    keypoints (degree != 2).

    Parameters
    ----------
    skeleton : np.ndarray
        Binary skeleton image.

    Returns
    -------
    list of Stroke
        Ordered point sequences along skeleton branches.
    """
    skel = (skeleton > 0).astype(np.uint8)
    if not np.any(skel):
        return []

    h, w = skel.shape
    visited_edges: set[Tuple[Tuple[int, int], Tuple[int, int]]] = set()
    strokes: List[Stroke] = []

    def walk_branch(ax: int, ay: int, bx: int, by: int) -> Stroke:
        """
        Walk a skeleton branch from one edge until a junction or endpoint.

        Parameters
        ----------
        ax : int
            Column of the starting endpoint.
        ay : int
            Row of the starting endpoint.
        bx : int
            Column of the second point on the branch.
        by : int
            Row of the second point on the branch.

        Returns
        -------
        Stroke
            Ordered points along the walked branch.
        """
        path: Stroke = [(float(ax), float(ay)), (float(bx), float(by))]
        visited_edges.add(_edge_key((ax, ay), (bx, by)))
        cx, cy = ax, ay
        x, y = bx, by

        while _skeleton_degree(y, x, skel) == 2:
            nbrs = [n for n in _skeleton_neighbors(skel, x, y) if n != (cx, cy)]
            if not nbrs:
                break
            nx, ny = nbrs[0]
            ek = _edge_key((x, y), (nx, ny))
            if ek in visited_edges:
                break
            visited_edges.add(ek)
            path.append((float(nx), float(ny)))
            cx, cy = x, y
            x, y = nx, ny

        return path

    keypoints = [
        (x, y)
        for y in range(h)
        for x in range(w)
        if skel[y, x] and _skeleton_degree(y, x, skel) != 2
    ]

    seeds = keypoints if keypoints else [(x, y) for y in range(h) for x in range(w) if skel[y, x]]

    for x, y in seeds:
        for nx, ny in _skeleton_neighbors(skel, x, y):
            ek = _edge_key((x, y), (nx, ny))
            if ek in visited_edges:
                continue
            path = walk_branch(x, y, nx, ny)
            if len(path) >= 2:
                strokes.append(path)

    return strokes


def _min_stroke_length(scale: float) -> float:
    """
    Minimum retained stroke length for a given image scale.

    Parameters
    ----------
    scale : float
        Characteristic image scale in pixels.

    Returns
    -------
    float
        Minimum stroke length threshold.
    """
    return max(3.0, scale * MIN_STROKE_LENGTH_RATIO)


def _filter_strokes(strokes: List[Stroke], scale: float) -> List[Stroke]:
    """
    Remove strokes shorter than the scale-dependent minimum length.

    Parameters
    ----------
    strokes : list of Stroke
        Input strokes.
    scale : float
        Characteristic image scale in pixels.

    Returns
    -------
    list of Stroke
        Strokes meeting the minimum length requirement.
    """
    min_len = _min_stroke_length(scale)
    return [s for s in strokes if _stroke_length(s) >= min_len]


def _stroke_length(stroke: Stroke) -> float:
    """
    Compute the polyline length of a stroke.

    Parameters
    ----------
    stroke : Stroke
        Ordered sequence of points.

    Returns
    -------
    float
        Sum of segment lengths along the stroke.
    """
    return sum(_dist(stroke[i], stroke[i + 1]) for i in range(len(stroke) - 1))


def _rdp_simplify(stroke: Stroke, epsilon: float) -> Stroke:
    """
    Simplify a stroke with the Ramer-Douglas-Peucker algorithm.

    Parameters
    ----------
    stroke : Stroke
        Input polyline.
    epsilon : float
        Maximum deviation allowed for simplified points.

    Returns
    -------
    Stroke
        Simplified polyline with at least two points.
    """
    if len(stroke) < 3:
        return list(stroke)
    arr = np.array(stroke, dtype=np.float32).reshape(-1, 1, 2)
    approx = cv2.approxPolyDP(arr, epsilon, False)
    simplified = [(float(p[0][0]), float(p[0][1])) for p in approx]
    return simplified if len(simplified) >= 2 else list(stroke[:2])


def _angle_diff(a: float, b: float) -> float:
    """
    Smallest angular difference between two directions in radians.

    Parameters
    ----------
    a : float
        First angle in radians.
    b : float
        Second angle in radians.

    Returns
    -------
    float
        Absolute difference in ``[0, pi/2]``.
    """
    d = abs(a - b) % math.pi
    return min(d, math.pi - d)


def _point_line_distance(p: Point, a: Point, b: Point) -> float:
    """
    Perpendicular distance from a point to the line through two points.

    Parameters
    ----------
    p : Point
        Query point.
    a : Point
        First point defining the line.
    b : Point
        Second point defining the line.

    Returns
    -------
    float
        Perpendicular distance from ``p`` to line ``ab``.
    """
    ax, ay = a
    bx, by = b
    px, py = p
    seg = math.hypot(bx - ax, by - ay)
    if seg < 1e-6:
        return math.hypot(px - ax, py - ay)
    return abs((by - ay) * px - (bx - ax) * py + bx * ay - by * ax) / seg


def _stroke_direction(stroke: Stroke) -> float:
    """
    Direction angle from the first to the last point of a stroke.

    Parameters
    ----------
    stroke : Stroke
        Ordered sequence of points.

    Returns
    -------
    float
        Angle in radians, or ``0.0`` for degenerate strokes.
    """
    if len(stroke) < 2:
        return 0.0
    x0, y0 = stroke[0]
    x1, y1 = stroke[-1]
    return math.atan2(y1 - y0, x1 - x0)


def _is_nearly_straight(stroke: Stroke, scale: float) -> bool:
    """
    Test whether a stroke deviates little from a straight line.

    Parameters
    ----------
    stroke : Stroke
        Ordered sequence of points.
    scale : float
        Characteristic image scale in pixels.

    Returns
    -------
    bool
        ``True`` if maximum deviation is within the scale-dependent tolerance.
    """
    if len(stroke) < 3:
        return True
    dev = max(_point_line_distance(p, stroke[0], stroke[-1]) for p in stroke)
    return dev <= max(1.5, scale * 0.01)


def _stroke_line_offset(stroke: Stroke) -> Tuple[float, float]:
    """
    Compute direction and perpendicular offset for collinear grouping.

    The offset is the signed distance of the stroke midpoint from the origin
    along the normal to the stroke direction.

    Parameters
    ----------
    stroke : Stroke
        Ordered sequence of points.

    Returns
    -------
    tuple of (float, float)
        ``(direction, offset)`` where direction is in radians.
    """
    direction = _stroke_direction(stroke)
    mid = stroke[len(stroke) // 2]
    offset = mid[0] * math.sin(direction) - mid[1] * math.cos(direction)
    return direction, offset


def _merge_collinear_strokes(strokes: List[Stroke], scale: float) -> List[Stroke]:
    """
    Merge collinear stroke fragments split at junctions.

    For example, rejoins arms of a crosshair separated at the center.

    Parameters
    ----------
    strokes : list of Stroke
        Input strokes.
    scale : float
        Characteristic image scale in pixels.

    Returns
    -------
    list of Stroke
        Strokes with collinear fragments merged where possible.
    """
    angle_thresh = math.radians(10)
    offset_thresh = max(2.0, scale * 0.008)
    gap_thresh = max(8.0, scale * 0.06)

    groups: List[List[Stroke]] = []
    for stroke in strokes:
        if len(stroke) < 2:
            continue
        direction, offset = _stroke_line_offset(stroke)
        placed = False
        for group in groups:
            ref_dir, ref_offset = _stroke_line_offset(group[0])
            if _angle_diff(direction, ref_dir) > angle_thresh:
                continue
            if abs(offset - ref_offset) > offset_thresh:
                continue
            group.append(stroke)
            placed = True
            break
        if not placed:
            groups.append([stroke])

    merged: List[Stroke] = []
    for group in groups:
        straight = [s for s in group if _is_nearly_straight(s, scale)]
        if len(straight) <= 1:
            merged.extend(group)
            continue

        ref = max(straight, key=_stroke_length)
        direction = _stroke_direction(ref)
        cos_a, sin_a = math.cos(direction), math.sin(direction)
        origin = ref[0]

        intervals: List[Tuple[float, float]] = []
        for stroke in straight:
            t_values = [
                (point[0] - origin[0]) * cos_a + (point[1] - origin[1]) * sin_a
                for point in (stroke[0], stroke[-1])
            ]
            intervals.append((min(t_values), max(t_values)))

        intervals.sort()
        combined: List[Tuple[float, float]] = [intervals[0]]
        for start, end in intervals[1:]:
            prev_start, prev_end = combined[-1]
            if start <= prev_end + gap_thresh:
                combined[-1] = (prev_start, max(prev_end, end))
            else:
                combined.append((start, end))

        for start, end in combined:
            merged.append(
                [
                    (origin[0] + start * cos_a, origin[1] + start * sin_a),
                    (origin[0] + end * cos_a, origin[1] + end * sin_a),
                ]
            )

        curved = [s for s in group if s not in straight]
        merged.extend(curved)

    return merged


def _perpendicular_line_distance(a: Stroke, b: Stroke) -> float:
    """
    Average perpendicular distance between the midpoints of two strokes.

    Parameters
    ----------
    a : Stroke
        First stroke.
    b : Stroke
        Second stroke.

    Returns
    -------
    float
        Mean distance from each midpoint to the other stroke's line.
    """
    mid_a = a[len(a) // 2]
    mid_b = b[len(b) // 2]
    return (_point_line_distance(mid_a, b[0], b[-1]) + _point_line_distance(mid_b, a[0], a[-1])) / 2.0


def _is_duplicate_stroke(a: Stroke, b: Stroke, dist_thresh: float) -> bool:
    """
    Test whether two strokes are parallel offset duplicates.

    Detects double skeleton borders, not merely collinear segments.

    Parameters
    ----------
    a : Stroke
        First stroke.
    b : Stroke
        Second stroke.
    dist_thresh : float
        Maximum perpendicular separation for duplicates.

    Returns
    -------
    bool
        ``True`` if the strokes are near-parallel duplicates within thresholds.
    """
    if not a or not b:
        return False
    if _angle_diff(_stroke_direction(a), _stroke_direction(b)) > math.radians(12):
        return False
    perp = _perpendicular_line_distance(a, b)
    if perp < max(1.0, dist_thresh * 0.15):
        return False
    if perp > dist_thresh:
        return False
    len_a, len_b = _stroke_length(a), _stroke_length(b)
    if len_a == 0 or len_b == 0:
        return False
    ratio = len_a / len_b if len_a >= len_b else len_b / len_a
    return ratio < 1.4


def _dedupe_parallel_strokes(strokes: List[Stroke], scale: float) -> List[Stroke]:
    """
    Remove parallel offset duplicate strokes, keeping the longest.

    Parameters
    ----------
    strokes : list of Stroke
        Input strokes.
    scale : float
        Characteristic image scale in pixels.

    Returns
    -------
    list of Stroke
        Deduplicated strokes.
    """
    dist_thresh = max(3.0, scale * PARALLEL_DEDUPE_RATIO)
    kept: List[Stroke] = []
    for stroke in sorted(strokes, key=_stroke_length, reverse=True):
        if any(_is_duplicate_stroke(stroke, existing, dist_thresh) for existing in kept):
            continue
        kept.append(stroke)
    return kept


def _resample_stroke(stroke: Stroke, step: float = RESAMPLE_STEP) -> Stroke:
    """
    Resample a stroke at approximately uniform arc-length spacing.

    Parameters
    ----------
    stroke : Stroke
        Input polyline.
    step : float, optional
        Target distance between consecutive points. Default is ``RESAMPLE_STEP``.

    Returns
    -------
    Stroke
        Resampled polyline.
    """
    if len(stroke) < 2:
        return stroke
    result: Stroke = [stroke[0]]
    for i in range(1, len(stroke)):
        x0, y0 = result[-1]
        x1, y1 = stroke[i]
        seg = math.hypot(x1 - x0, y1 - y0)
        if seg <= step:
            result.append((x1, y1))
            continue
        count = max(1, int(math.ceil(seg / step)))
        for j in range(1, count + 1):
            t = j / count
            result.append((x0 + (x1 - x0) * t, y0 + (y1 - y0) * t))
    return result


def _cap_points(stroke: Stroke, max_points: int = MAX_POINTS_PER_STROKE) -> Stroke:
    """
    Downsample a stroke to at most a fixed number of points.

    Parameters
    ----------
    stroke : Stroke
        Input polyline.
    max_points : int, optional
        Maximum number of points to retain. Default is ``MAX_POINTS_PER_STROKE``.

    Returns
    -------
    Stroke
        Subsampled polyline.
    """
    if len(stroke) <= max_points:
        return stroke
    step = (len(stroke) - 1) / (max_points - 1)
    indices = [int(round(i * step)) for i in range(max_points)]
    return [stroke[i] for i in indices]


def _optimize_strokes(raw: List[Stroke], scale: float) -> List[Stroke]:
    """
    Run the full stroke optimization pipeline.

    Skeleton branches are merged collinearly, simplified with RDP, filtered,
    and deduplicated in parallel.

    Parameters
    ----------
    raw : list of Stroke
        Raw skeleton strokes.
    scale : float
        Characteristic image scale in pixels.

    Returns
    -------
    list of Stroke
        Optimized strokes with at least two points each.
    """
    epsilon = max(0.8, scale * RDP_EPSILON_RATIO)
    merged = _merge_collinear_strokes(raw, scale)
    simplified = [_rdp_simplify(s, epsilon) for s in merged]
    curved = [s for s in simplified if len(s) > 2 and not _is_nearly_straight(s, scale)]
    for stroke in curved:
        idx = simplified.index(stroke)
        simplified[idx] = _cap_points(_resample_stroke(stroke), MAX_POINTS_PER_STROKE)
    simplified = _filter_strokes(simplified, scale)
    deduped = _dedupe_parallel_strokes(simplified, scale)
    return [s for s in deduped if len(s) >= 2]


def _skeleton_strokes_per_component(mask: np.ndarray) -> List[Stroke]:
    """
    Skeletonize each connected component separately.

    Ensures disconnected parts of the mask are all captured.

    Parameters
    ----------
    mask : np.ndarray
        Binary foreground mask.

    Returns
    -------
    list of Stroke
        Strokes extracted from all connected components.
    """
    labels_count, labels = cv2.connectedComponents((mask > 0).astype(np.uint8))
    strokes: List[Stroke] = []
    for label in range(1, labels_count):
        component = np.where(labels == label, 255, 0).astype(np.uint8)
        skeleton = _morphological_skeleton(component)
        strokes.extend(_skeleton_to_strokes(skeleton))
    return strokes


def _extract_strokes_from_mask(mask: np.ndarray) -> List[Stroke]:
    """
    Extract optimized strokes from a binary mask.

    Pipeline: grayscale mask -> skeleton -> ordered continuous segments ->
    filtering and optimization.

    Each segment is an ordered coordinate sequence along the centerline.

    Parameters
    ----------
    mask : np.ndarray
        Binary foreground mask.

    Returns
    -------
    list of Stroke
        Normalized-ready strokes in image coordinates.
    """
    scale = _image_scale(mask)
    raw = _skeleton_strokes_per_component(mask)
    if not raw:
        skeleton = _morphological_skeleton(mask)
        raw = _skeleton_to_strokes(skeleton)
    return _optimize_strokes(raw, scale)


def _score_stroke_set(strokes: List[Stroke], mask: np.ndarray) -> float:
    """
    Score a candidate stroke set for mask extraction quality.

    Parameters
    ----------
    strokes : list of Stroke
        Candidate strokes.
    mask : np.ndarray
        Binary mask the strokes were derived from.

    Returns
    -------
    float
        Quality score, or ``-1.0`` for unusable stroke sets.
    """
    if not strokes:
        return -1.0
    fg = float(np.count_nonzero(mask))
    total_len = sum(_stroke_length(s) for s in strokes)
    min_len = math.sqrt(fg) * 0.55
    if total_len < min_len:
        return -1.0
    if len(strokes) > 100:
        return -1.0
    point_count = sum(len(s) for s in strokes)
    return total_len - len(strokes) * 30.0 - point_count * 1.2


def _save_debug_image(image_path: Path, mask: np.ndarray, skeleton: np.ndarray) -> None:
    """
    Write binary mask and skeleton debug images to the debug directory.

    Parameters
    ----------
    image_path : Path
        Source image path used for output file naming.
    mask : np.ndarray
        Binary mask to save.
    skeleton : np.ndarray
        Skeleton image to save.

    Returns
    -------
    None
    """
    DEBUG_DIR.mkdir(parents=True, exist_ok=True)
    stem = image_path.stem
    cv2.imwrite(str(DEBUG_DIR / f"{stem}_binary.png"), mask)
    cv2.imwrite(str(DEBUG_DIR / f"{stem}_skeleton.png"), skeleton)


def _normalize_strokes_to_viewbox(strokes: List[Stroke]) -> List[Stroke]:
    """
    Scale and center strokes into the standard SVG viewBox.

    Parameters
    ----------
    strokes : list of Stroke
        Strokes in image pixel coordinates.

    Returns
    -------
    list of Stroke
        Strokes mapped into ``[0, VIEWBOX_SIZE]`` with padding.
    """
    xs: List[float] = []
    ys: List[float] = []
    for stroke in strokes:
        for x, y in stroke:
            xs.append(x)
            ys.append(y)
    if not xs:
        return []

    min_x, max_x = min(xs), max(xs)
    min_y, max_y = min(ys), max(ys)
    cx = (min_x + max_x) / 2
    cy = (min_y + max_y) / 2
    size = max(max_x - min_x, max_y - min_y) or 1.0

    usable = VIEWBOX_SIZE - 2 * VIEWBOX_PADDING
    scale = usable / size
    offset = VIEWBOX_SIZE / 2

    normalized: List[Stroke] = []
    for stroke in strokes:
        normalized.append(
            [
                ((x - cx) * scale + offset, (y - cy) * scale + offset)
                for x, y in stroke
            ]
        )
    return normalized


def _dist(a: Point, b: Point) -> float:
    """
    Euclidean distance between two points.

    Parameters
    ----------
    a : Point
        First point.
    b : Point
        Second point.

    Returns
    -------
    float
        Distance between ``a`` and ``b``.
    """
    return math.hypot(a[0] - b[0], a[1] - b[1])


def strokes_to_svg(strokes: Sequence[Stroke], name: str) -> str:
    """
    Serialize strokes to an SVG document string.

    Each skeleton stroke becomes one ordered polyline.

    Parameters
    ----------
    strokes : sequence of Stroke
        Strokes in viewBox coordinates.
    name : str
        Title text for the SVG.

    Returns
    -------
    str
        SVG markup as a Unicode string.
    """
    root = ET.Element(
        "svg",
        {
            "xmlns": "http://www.w3.org/2000/svg",
            "viewBox": f"0 0 {VIEWBOX_SIZE:g} {VIEWBOX_SIZE:g}",
            "data-draw-mode": "skeleton-strokes",
            "role": "img",
            "focusable": "false",
        },
    )
    title = ET.SubElement(root, "title")
    title.text = name

    group = ET.SubElement(root, "g", {"id": "strokes"})
    for idx, stroke in enumerate(strokes):
        if len(stroke) < 2:
            continue
        points_str = " ".join(f"{x:.2f},{y:.2f}" for x, y in stroke)
        ET.SubElement(
            group,
            "polyline",
            {
                "id": f"stroke-{idx}",
                "data-role": "stroke",
                "points": points_str,
                "fill": "none",
                "stroke": "#000000",
                "stroke-width": "1",
            },
        )

    return ET.tostring(root, encoding="unicode")


def write_stroke_svg(strokes: Sequence[Stroke], output_path: Path, name: str) -> None:
    """
    Write strokes to an SVG file on disk.

    Parameters
    ----------
    strokes : sequence of Stroke
        Strokes in viewBox coordinates.
    output_path : Path
        Destination file path.
    name : str
        Title text embedded in the SVG.

    Returns
    -------
    None
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(strokes_to_svg(strokes, name), encoding="utf-8")


def convert_raster_to_strokes(
    image_path: Path,
    *,
    debug: bool = False,
) -> List[Stroke]:
    """
    Convert a raster image file to normalized skeleton strokes.

    Parameters
    ----------
    image_path : Path
        Path to a supported raster image (WebP, PNG, JPEG).
    debug : bool, optional
        If ``True``, write binary and skeleton debug images. Default is ``False``.

    Returns
    -------
    list of Stroke
        Strokes normalized to the standard viewBox.
    """
    rgba = np.array(Image.open(image_path).convert("RGBA"))
    masks = _generate_binary_masks(rgba)

    best: List[Stroke] = []
    best_score = -1.0
    best_mask = masks[0] if masks else np.zeros(rgba.shape[:2], np.uint8)

    for mask in masks:
        strokes = _extract_strokes_from_mask(mask)
        score = _score_stroke_set(strokes, mask)
        if score > best_score:
            best_score = score
            best = strokes
            best_mask = mask

    if not best:
        for mask in masks:
            strokes = _extract_strokes_from_mask(mask)
            if strokes:
                best = strokes
                best_mask = mask
                break

    if debug:
        skeleton = _morphological_skeleton(best_mask)
        _save_debug_image(image_path, best_mask, skeleton)

    return _normalize_strokes_to_viewbox(best)


def convert_raster_file(
    image_path: Path,
    output_path: Path,
    *,
    debug: bool = False,
) -> ConversionResult:
    """
    Convert a raster image to a stroke SVG file.

    Parameters
    ----------
    image_path : Path
        Path to a supported raster image.
    output_path : Path
        Destination SVG path.
    debug : bool, optional
        If ``True``, write debug images during conversion. Default is ``False``.

    Returns
    -------
    ConversionResult
        Summary of the conversion.

    Raises
    ------
    ValueError
        If no strokes are detected in the input image.
    """
    strokes = convert_raster_to_strokes(image_path, debug=debug)
    if not strokes:
        raise ValueError(f"No stroke detected in {image_path.name}")

    write_stroke_svg(strokes, output_path, output_path.stem)
    points = sum(len(s) for s in strokes)
    return ConversionResult(
        image_path,
        output_path,
        len(strokes),
        vertex_count=points,
        branch_count=len(strokes),
        mode="skeleton-strokes",
    )


def convert_svg_file(svg_path: Path, output_path: Path) -> ConversionResult:
    """
    Optimize strokes from an existing SVG and write a stroke SVG.

    Parameters
    ----------
    svg_path : Path
        Source SVG file.
    output_path : Path
        Destination SVG path.

    Returns
    -------
    ConversionResult
        Summary of the conversion.

    Raises
    ------
    ValueError
        If no strokes are detected in the input SVG.
    """
    raw = load_svg_strokes(svg_path)
    xs = [x for stroke in raw for x, _y in stroke]
    ys = [y for stroke in raw for _x, y in stroke]
    scale = math.hypot(max(xs) - min(xs), max(ys) - min(ys)) if xs else 100.0

    strokes = _optimize_strokes(raw, scale or 100.0)
    strokes = _normalize_strokes_to_viewbox(strokes)
    if not strokes:
        raise ValueError(f"No stroke detected in {svg_path.name}")

    write_stroke_svg(strokes, output_path, output_path.stem)
    points = sum(len(s) for s in strokes)
    return ConversionResult(
        svg_path,
        output_path,
        len(strokes),
        vertex_count=points,
        branch_count=len(strokes),
        mode="skeleton-strokes",
    )


def _iter_raster_files(folder: Path) -> Iterable[Path]:
    """
    Iterate supported raster files in a directory.

    Parameters
    ----------
    folder : Path
        Directory to scan.

    Returns
    -------
    Iterable of Path
        Sorted paths to supported image files, or an empty list if not a directory.
    """
    if not folder.is_dir():
        return []
    return sorted(
        p for p in folder.iterdir() if p.is_file() and p.suffix.lower() in SUPPORTED_INPUT
    )


def _load_manifest() -> Tuple[List[str], List[str]]:
    """
    Load sigil and sign stems from the WebP manifest file.

    Returns
    -------
    tuple of (list of str, list of str)
        ``(sigil_stems, sign_stems)``, each empty if the manifest is missing.
    """
    manifest_path = WEBP_DIR / "manifest.json"
    if not manifest_path.is_file():
        return [], []

    data = json.loads(manifest_path.read_text(encoding="utf-8"))
    sigils = [Path(name).stem for name in data.get("sigils", [])]
    signs = [Path(name).stem for name in data.get("signs", [])]
    return sigils, signs


def _iter_flat_webp() -> List[Tuple[str, Path]]:
    """
    Resolve flat WebP sources listed in the manifest.

    Returns
    -------
    list of tuple of (str, Path)
        ``(kind, path)`` entries where kind is ``'sigil'`` or ``'sign'``.
    """
    sigil_names, sign_names = _load_manifest()
    if not sigil_names and not sign_names:
        return []

    entries: List[Tuple[str, Path]] = []
    for stem in sigil_names:
        path = _find_flat_source(stem)
        if path:
            entries.append(("sigil", path))
    for stem in sign_names:
        path = _find_flat_source(stem)
        if path:
            entries.append(("sign", path))
    return entries


def _find_flat_source(stem: str) -> Path | None:
    """
    Find a flat-layout raster file for a given asset stem.

    Parameters
    ----------
    stem : str
        Base filename without extension.

    Returns
    -------
    Path or None
        First matching supported file in ``WEBP_DIR``, or ``None``.
    """
    for ext in SUPPORTED_INPUT:
        candidate = WEBP_DIR / f"{stem}{ext}"
        if candidate.is_file():
            return candidate
    return None


def _iter_prefixed_flat_webp() -> List[Tuple[str, Path]]:
    """
    Scan flat WebP directory for ``sigil_`` and ``sign_`` prefixed files.

    Returns
    -------
    list of tuple of (str, Path)
        ``(kind, path)`` entries discovered in ``WEBP_DIR``.
    """
    if not WEBP_DIR.is_dir():
        return []

    entries: List[Tuple[str, Path]] = []
    for path in sorted(WEBP_DIR.iterdir()):
        if not path.is_file() or path.suffix.lower() not in SUPPORTED_INPUT:
            continue
        stem = path.stem
        if stem.startswith("sigil_"):
            entries.append(("sigil", path))
        elif stem.startswith("sign_"):
            entries.append(("sign", path))
    return entries


def discover_sources() -> List[Tuple[str, Path]]:
    """
    Discover raster source files for conversion.

    Checks categorized folders first, then manifest-based flat layout,
    then prefix-based flat layout.

    Returns
    -------
    list of tuple of (str, Path)
        ``(kind, path)`` where kind is ``'sigil'`` or ``'sign'``.
    """
    sources: List[Tuple[str, Path]] = []

    for path in _iter_raster_files(WEBP_SIGILS_DIR):
        sources.append(("sigil", path))
    for path in _iter_raster_files(WEBP_SIGNS_DIR):
        sources.append(("sign", path))

    if sources:
        return sources

    for kind, path in _iter_flat_webp():
        sources.append((kind, path))

    if sources:
        return sources

    for kind, path in _iter_prefixed_flat_webp():
        sources.append((kind, path))

    return sources


def _output_path(kind: str, stem: str) -> Path:
    """
    Build the output SVG path for a source asset.

    Parameters
    ----------
    kind : str
        Asset kind, ``'sigil'`` or ``'sign'``.
    stem : str
        Source filename stem.

    Returns
    -------
    Path
        Normalized output path under the appropriate sigils or signs directory.
    """
    name = normalize_asset_name(stem)
    if kind == "sigil":
        return PATH_SIGILS_DIR / f"{name}.svg"
    return PATH_SIGNS_DIR / f"{name}.svg"


def convert_all(
    *,
    include_bootstrap_svg: bool = False,
    verbose: bool = True,
    debug: bool = False,
) -> List[ConversionResult]:
    """
    Convert all discovered raster sources to stroke SVGs.

    Optionally bootstrap from legacy SVG assets when no rasters are found.

    Parameters
    ----------
    include_bootstrap_svg : bool, optional
        If ``True`` and no rasters exist, convert bootstrap SVGs. Default is ``False``.
    verbose : bool, optional
        If ``True``, print a line per conversion. Default is ``True``.
    debug : bool, optional
        If ``True``, write debug images during raster conversion. Default is ``False``.

    Returns
    -------
    list of ConversionResult
        One result per converted file.
    """
    _ensure_dirs()
    results: List[ConversionResult] = []

    sources = discover_sources()
    if not sources and include_bootstrap_svg:
        from .assets import SIGNS_DIR, SIGILS_DIR

        for svg in sorted(SIGILS_DIR.glob("*.svg")):
            out = PATH_SIGILS_DIR / f"{normalize_asset_name(svg.stem)}.svg"
            result = convert_svg_file(svg, out)
            results.append(result)
            if verbose:
                print(_format_result("[bootstrap]", svg.name, out, result))

        for svg in sorted(SIGNS_DIR.glob("*.svg")):
            out = PATH_SIGNS_DIR / f"{normalize_asset_name(svg.stem)}.svg"
            result = convert_svg_file(svg, out)
            results.append(result)
            if verbose:
                print(_format_result("[bootstrap]", svg.name, out, result))

        return results

    for kind, source in sources:
        out = _output_path(kind, source.stem)
        result = convert_raster_file(source, out, debug=debug)
        results.append(result)
        if verbose:
            print(_format_result(f"[{kind}]", source.name, out, result))

    return results


def _format_result(prefix: str, source_name: str, out: Path, result: ConversionResult) -> str:
    """
    Format a conversion result line for console output.

    Parameters
    ----------
    prefix : str
        Label prefix such as ``'[sigil]'`` or ``'[bootstrap]'``.
    source_name : str
        Source filename.
    out : Path
        Output file path.
    result : ConversionResult
        Conversion summary.

    Returns
    -------
    str
        Human-readable one-line summary.
    """
    return (
        f"{prefix} {source_name} -> {out} "
        f"({result.stroke_count} strokes, {result.vertex_count} points)"
    )
