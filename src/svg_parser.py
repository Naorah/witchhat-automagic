"""SVG parsing, normalization, and coordinate transforms for spell assets."""

from __future__ import annotations

import math
import re
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Iterable, List, Tuple

from svgpathtools import Path, parse_path

from .models import Point, Stroke
from .point_graph import PointGraph

SVG_NS = "http://www.w3.org/2000/svg"
SAMPLE_STEP = 2.0


def _parse_transform(transform: str | None) -> Tuple[float, float, float, float, float, float]:
    """
    Parse an SVG ``transform`` attribute into a 2D affine matrix.

    Parameters
    ----------
    transform : str or None
        SVG transform string (``matrix``, ``translate``, ``scale``, ``rotate``).

    Returns
    -------
    tuple of float
        ``(a, b, c, d, e, f)`` for ``x' = a*x + c*y + e``, ``y' = b*x + d*y + f``.
    """
    if not transform:
        return (1.0, 0.0, 0.0, 1.0, 0.0, 0.0)

    matrix = (1.0, 0.0, 0.0, 1.0, 0.0, 0.0)

    def mul(
        m1: Tuple[float, float, float, float, float, float],
        m2: Tuple[float, float, float, float, float, float],
    ) -> Tuple[float, float, float, float, float, float]:
        """Multiply two affine matrices ``m1 * m2``."""
        a1, b1, c1, d1, e1, f1 = m1
        a2, b2, c2, d2, e2, f2 = m2
        return (
            a1 * a2 + c1 * b2,
            b1 * a2 + d1 * b2,
            a1 * c2 + c1 * d2,
            b1 * c2 + d1 * d2,
            a1 * e2 + c1 * f2 + e1,
            b1 * e2 + d1 * f2 + f1,
        )

    for match in re.finditer(
        r"(matrix|translate|scale|rotate)\s*\(([^)]*)\)",
        transform,
    ):
        kind = match.group(1)
        parts = [float(v) for v in re.split(r"[\s,]+", match.group(2).strip()) if v]

        if kind == "matrix":
            a, b, c, d, e, f = parts[:6]
            t = (a, b, c, d, e, f)
        elif kind == "translate":
            tx = parts[0]
            ty = parts[1] if len(parts) > 1 else 0.0
            t = (1.0, 0.0, 0.0, 1.0, tx, ty)
        elif kind == "scale":
            sx = parts[0]
            sy = parts[1] if len(parts) > 1 else sx
            t = (sx, 0.0, 0.0, sy, 0.0, 0.0)
        elif kind == "rotate":
            angle = math.radians(parts[0])
            cos_a, sin_a = math.cos(angle), math.sin(angle)
            if len(parts) > 2:
                cx, cy = parts[1], parts[2]
                t = mul(
                    (1.0, 0.0, 0.0, 1.0, cx, cy),
                    (cos_a, sin_a, -sin_a, cos_a, 0.0, 0.0),
                )
                t = mul(t, (1.0, 0.0, 0.0, 1.0, -cx, -cy))
            else:
                t = (cos_a, sin_a, -sin_a, cos_a, 0.0, 0.0)
        else:
            continue

        matrix = mul(matrix, t)

    return matrix


def _apply_matrix(
    x: float, y: float, m: Tuple[float, float, float, float, float, float]
) -> Point:
    """
    Apply an affine matrix to a point.

    Parameters
    ----------
    x, y : float
        Input coordinates.
    m : tuple of float
        Affine matrix ``(a, b, c, d, e, f)``.

    Returns
    -------
    Point
        Transformed ``(x', y')``.
    """
    a, b, c, d, e, f = m
    return (a * x + c * y + e, b * x + d * y + f)


def _combine_matrix(
    parent: Tuple[float, float, float, float, float, float],
    child: Tuple[float, float, float, float, float, float],
) -> Tuple[float, float, float, float, float, float]:
    """
    Multiply parent and child SVG transform matrices.

    Parameters
    ----------
    parent : tuple of float
        Accumulated parent matrix.
    child : tuple of float
        Local element matrix.

    Returns
    -------
    tuple of float
        Combined matrix ``parent * child``.
    """
    a1, b1, c1, d1, e1, f1 = parent
    a2, b2, c2, d2, e2, f2 = child
    return (
        a1 * a2 + c1 * b2,
        b1 * a2 + d1 * b2,
        a1 * c2 + c1 * d2,
        b1 * c2 + d1 * d2,
        a1 * e2 + c1 * f2 + e1,
        b1 * e2 + d1 * f2 + f1,
    )


def _sample_subpath(subpath: Path, step: float = SAMPLE_STEP) -> Stroke:
    """
    Sample an ``svgpathtools`` subpath into a polyline.

    Parameters
    ----------
    subpath : Path
        Continuous SVG subpath.
    step : float, optional
        Approximate distance between samples, by default ``SAMPLE_STEP``.

    Returns
    -------
    Stroke
        Sampled points along the subpath.
    """
    if len(subpath) == 0:
        return []

    length = subpath.length()
    if length <= 0:
        pt = subpath.point(0)
        return [(pt.real, pt.imag)]

    points: Stroke = []
    dist = 0.0
    while dist <= length:
        t = subpath.ilength(min(dist, length))
        pt = subpath.point(t)
        points.append((pt.real, pt.imag))
        dist += step

    end = subpath.point(1.0)
    end_pt = (end.real, end.imag)
    if not points or _dist(points[-1], end_pt) > 0.5:
        points.append(end_pt)

    return points


def _dist(a: Point, b: Point) -> float:
    """
    Euclidean distance between two points.

    Parameters
    ----------
    a, b : Point
        Input coordinates.

    Returns
    -------
    float
        Distance in the same units as the points.
    """
    return math.hypot(a[0] - b[0], a[1] - b[1])


def _path_to_strokes(path_data: str, matrix: Tuple[float, float, float, float, float, float]) -> List[Stroke]:
    """
    Convert SVG path ``d`` data to transformed polylines.

    Parameters
    ----------
    path_data : str
        SVG path ``d`` attribute.
    matrix : tuple of float
        Cumulative transform to apply.

    Returns
    -------
    list of Stroke
        One stroke per continuous subpath.
    """
    parsed = parse_path(path_data)
    strokes: List[Stroke] = []

    for subpath in parsed.continuous_subpaths():
        raw = _sample_subpath(subpath)
        if len(raw) < 2:
            continue
        transformed = [_apply_matrix(x, y, matrix) for x, y in raw]
        strokes.append(transformed)

    return strokes


def _collect_paths(
    element: ET.Element,
    parent_matrix: Tuple[float, float, float, float, float, float],
    strokes: List[Stroke],
) -> None:
    """
    Recursively collect drawable strokes from an SVG element tree.

    Parameters
    ----------
    element : xml.etree.ElementTree.Element
        Current SVG element.
    parent_matrix : tuple of float
        Accumulated transform from ancestors.
    strokes : list of Stroke
        Output list mutated in place.

    Returns
    -------
    None
    """
    local = _parse_transform(element.get("transform"))
    matrix = _combine_matrix(parent_matrix, local)
    tag = element.tag.split("}")[-1]

    if tag == "path" and element.get("d"):
        strokes.extend(_path_to_strokes(element.get("d", ""), matrix))
    elif tag in ("polyline", "polygon"):
        role = element.get("data-role")
        if role in ("vertices", "edges"):
            pass
        elif role in (None, "stroke", "branch"):
            pts = element.get("points", "").strip()
            coords = [float(v) for v in re.split(r"[\s,]+", pts) if v]
            if len(coords) >= 4:
                raw: Stroke = [
                    (coords[i], coords[i + 1]) for i in range(0, len(coords) - 1, 2)
                ]
                if tag == "polygon" and raw and raw[0] != raw[-1]:
                    raw.append(raw[0])
                strokes.append([_apply_matrix(x, y, matrix) for x, y in raw])
    elif tag == "line":
        x1 = float(element.get("x1", 0))
        y1 = float(element.get("y1", 0))
        x2 = float(element.get("x2", 0))
        y2 = float(element.get("y2", 0))
        strokes.append(
            [
                _apply_matrix(x1, y1, matrix),
                _apply_matrix(x2, y2, matrix),
            ]
        )

    for child in element:
        _collect_paths(child, matrix, strokes)


def _bbox(strokes: Iterable[Stroke]) -> Tuple[float, float, float, float]:
    """
    Compute the axis-aligned bounding box of all stroke points.

    Parameters
    ----------
    strokes : iterable of Stroke
        Polylines to measure.

    Returns
    -------
    tuple of float
        ``(min_x, min_y, max_x, max_y)``; defaults to ``(0, 0, 1, 1)`` when empty.
    """
    xs: List[float] = []
    ys: List[float] = []
    for stroke in strokes:
        for x, y in stroke:
            xs.append(x)
            ys.append(y)
    if not xs:
        return (0.0, 0.0, 1.0, 1.0)
    return (min(xs), min(ys), max(xs), max(ys))


def _parse_points_attr(
    points_attr: str,
    matrix: Tuple[float, float, float, float, float, float],
) -> Stroke:
    """
    Parse a SVG ``points`` attribute and apply a transform.

    Parameters
    ----------
    points_attr : str
        Space- or comma-separated coordinate pairs.
    matrix : tuple of float
        Affine matrix to apply.

    Returns
    -------
    Stroke
        Transformed points; empty when fewer than two vertices.
    """
    pts = points_attr.strip()
    coords = [float(v) for v in re.split(r"[\s,]+", pts) if v]
    if len(coords) < 4:
        return []
    raw: Stroke = [(coords[i], coords[i + 1]) for i in range(0, len(coords) - 1, 2)]
    return [_apply_matrix(x, y, matrix) for x, y in raw]


def is_points_svg(path: Path) -> bool:
    """
    Return whether an SVG uses point/branch or point-graph conventions.

    Parameters
    ----------
    path : Path
        SVG file path.

    Returns
    -------
    bool
        ``True`` when ``data-draw-mode`` or ``data-role`` indicates point data.
    """
    tree = ET.parse(path)
    root = tree.getroot()
    mode = root.get("data-draw-mode")
    if mode in ("points", "point-graph"):
        return True
    for element in root.iter():
        role = element.get("data-role")
        if role in ("branch", "vertices", "edges"):
            return True
    return False


def is_point_graph_svg(path: Path) -> bool:
    """
    Return whether an SVG stores an explicit vertex/edge point graph.

    Parameters
    ----------
    path : Path
        SVG file path.

    Returns
    -------
    bool
        ``True`` for ``data-draw-mode="point-graph"`` or vertices/edges roles.
    """
    tree = ET.parse(path)
    root = tree.getroot()
    if root.get("data-draw-mode") == "point-graph":
        return True
    for element in root.iter():
        if element.get("data-role") in ("vertices", "edges"):
            return True
    return False


def _collect_branches(
    element: ET.Element,
    parent_matrix: Tuple[float, float, float, float, float, float],
    branches: List[Stroke],
) -> None:
    """
    Recursively collect legacy ``data-role="branch"`` polylines.

    Parameters
    ----------
    element : xml.etree.ElementTree.Element
        Current SVG element.
    parent_matrix : tuple of float
        Accumulated transform.
    branches : list of Stroke
        Output list mutated in place.

    Returns
    -------
    None
    """
    local = _parse_transform(element.get("transform"))
    matrix = _combine_matrix(parent_matrix, local)
    tag = element.tag.split("}")[-1]

    if tag == "polyline" and element.get("data-role") == "branch":
        branch = _parse_points_attr(element.get("points", ""), matrix)
        if len(branch) >= 2:
            branches.append(branch)

    for child in element:
        _collect_branches(child, matrix, branches)


def load_svg_point_branches(path: Path) -> List[Stroke]:
    """
    Load legacy branch polylines from an SVG file.

    Parameters
    ----------
    path : Path
        SVG file path.

    Returns
    -------
    list of Stroke
        Branch polylines with transforms applied.
    """
    tree = ET.parse(path)
    root = tree.getroot()
    branches: List[Stroke] = []
    _collect_branches(root, (1.0, 0.0, 0.0, 1.0, 0.0, 0.0), branches)
    return branches


def _collect_point_graph(
    element: ET.Element,
    parent_matrix: Tuple[float, float, float, float, float, float],
    vertices: List[Point],
    edges: List[Tuple[int, int]],
) -> None:
    """
    Recursively collect vertices and edge index pairs from an SVG tree.

    Parameters
    ----------
    element : xml.etree.ElementTree.Element
        Current SVG element.
    parent_matrix : tuple of float
        Accumulated transform.
    vertices : list of Point
        Output vertex list mutated in place.
    edges : list of tuple of int
        Output edge list mutated in place.

    Returns
    -------
    None
    """
    local = _parse_transform(element.get("transform"))
    matrix = _combine_matrix(parent_matrix, local)
    tag = element.tag.split("}")[-1]
    role = element.get("data-role")

    if tag == "polyline" and role == "vertices":
        verts = _parse_points_attr(element.get("points", ""), matrix)
        vertices.extend(verts)
    elif tag == "polyline" and role == "edges":
        pts = element.get("points", "").strip()
        coords = [int(float(v)) for v in re.split(r"[\s,]+", pts) if v]
        for i in range(0, len(coords) - 1, 2):
            edges.append((coords[i], coords[i + 1]))

    for child in element:
        _collect_point_graph(child, matrix, vertices, edges)


def load_svg_point_graph(path: Path) -> PointGraph:
    """
    Load a point graph from an SVG file.

    Parameters
    ----------
    path : Path
        SVG file path.

    Returns
    -------
    PointGraph
        Vertices and edges; falls back to branch conversion when needed.
    """
    tree = ET.parse(path)
    root = tree.getroot()
    vertices: List[Point] = []
    edges: List[Tuple[int, int]] = []
    _collect_point_graph(root, (1.0, 0.0, 0.0, 1.0, 0.0, 0.0), vertices, edges)
    if vertices and edges:
        return PointGraph(vertices=vertices, edges=edges)

    branches = load_svg_point_branches(path)
    from .point_graph import branches_to_point_graph

    return branches_to_point_graph(branches)


def normalize_point_graph(graph: PointGraph) -> PointGraph:
    """
    Normalize point-graph vertices to a unit bounding box centered on the origin.

    Parameters
    ----------
    graph : PointGraph
        Input graph in arbitrary coordinates.

    Returns
    -------
    PointGraph
        Graph with normalized vertex positions; edges unchanged.
    """
    if not graph.vertices:
        return graph
    normalized = normalize_strokes([graph.vertices])[0]
    return PointGraph(vertices=normalized, edges=list(graph.edges))


def transform_point_graph(
    graph: PointGraph,
    scale: float,
    rotation_deg: float,
    tx: float,
    ty: float,
) -> PointGraph:
    """
    Apply scale, rotation, and translation to graph vertices.

    Parameters
    ----------
    graph : PointGraph
        Input graph.
    scale : float
        Uniform scale factor.
    rotation_deg : float
        Rotation in degrees.
    tx, ty : float
        Translation after rotation.

    Returns
    -------
    PointGraph
        Transformed graph; edges unchanged.
    """
    if not graph.vertices:
        return graph
    transformed = transform_strokes([graph.vertices], scale, rotation_deg, tx, ty)[0]
    return PointGraph(vertices=transformed, edges=list(graph.edges))


def load_svg_strokes(path: Path) -> List[Stroke]:
    """
    Load drawable strokes from an SVG file.

    Parameters
    ----------
    path : Path
        SVG file path.

    Returns
    -------
    list of Stroke
        Path/polygon strokes, or legacy branches when no paths are found.
    """
    tree = ET.parse(path)
    root = tree.getroot()
    strokes: List[Stroke] = []
    _collect_paths(root, (1.0, 0.0, 0.0, 1.0, 0.0, 0.0), strokes)
    if strokes:
        return [s for s in strokes if len(s) >= 2]

    if is_points_svg(path):
        branches = load_svg_point_branches(path)
        return [b for b in branches if len(b) >= 2]

    return []


def normalize_strokes(strokes: List[Stroke]) -> List[Stroke]:
    """
    Center strokes on the origin and scale to a unit bounding box.

    Parameters
    ----------
    strokes : list of Stroke
        Input polylines in arbitrary coordinates.

    Returns
    -------
    list of Stroke
        Normalized polylines (max side length = 1).
    """
    if not strokes:
        return []

    min_x, min_y, max_x, max_y = _bbox(strokes)
    cx = (min_x + max_x) / 2
    cy = (min_y + max_y) / 2
    size = max(max_x - min_x, max_y - min_y) or 1.0

    normalized: List[Stroke] = []
    for stroke in strokes:
        normalized.append(
            [((x - cx) / size, (y - cy) / size) for x, y in stroke]
        )
    return normalized


def transform_strokes(
    strokes: List[Stroke],
    scale: float,
    rotation_deg: float,
    tx: float,
    ty: float,
) -> List[Stroke]:
    """
    Apply scale, rotation, and translation to every stroke.

    Parameters
    ----------
    strokes : list of Stroke
        Input polylines (typically normalized).
    scale : float
        Uniform scale factor applied before rotation.
    rotation_deg : float
        Rotation in degrees counter-clockwise.
    tx, ty : float
        Translation applied after rotation.

    Returns
    -------
    list of Stroke
        Transformed polylines in screen or layout space.
    """
    angle = math.radians(rotation_deg)
    cos_a, sin_a = math.cos(angle), math.sin(angle)
    result: List[Stroke] = []

    for stroke in strokes:
        transformed: Stroke = []
        for x, y in stroke:
            sx, sy = x * scale, y * scale
            rx = sx * cos_a - sy * sin_a + tx
            ry = sx * sin_a + sy * cos_a + ty
            transformed.append((rx, ry))
        result.append(transformed)

    return result
