"""Point graphs: vertices, edges, and conversion to drawing strokes."""

from __future__ import annotations

import math
from collections import defaultdict
from dataclasses import dataclass
from enum import Enum
from typing import Dict, List, Sequence, Tuple

from .models import Point, Stroke

Branch = Stroke
Edge = Tuple[int, int]


@dataclass
class PointGraph:
    """Explicit vertices and undirected edges for connect-the-dots drawing.

    Attributes
    ----------
    vertices : list of Point
        Node positions (normalized or screen space).
    edges : list of tuple of int
        Vertex index pairs defining links.
    """

    vertices: List[Point]
    edges: List[Edge]


class PointConnectMode(str, Enum):
    """Strategy for turning edges into mouse strokes."""

    BRANCHES = "branches"
    SEGMENTS = "segments"
    NEAREST = "nearest"


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


def _centroid(points: List[Point]) -> Point:
    """
    Compute the arithmetic mean of a point set.

    Parameters
    ----------
    points : list of Point
        Input vertices.

    Returns
    -------
    Point
        Centroid, or ``(0, 0)`` when ``points`` is empty.
    """
    if not points:
        return (0.0, 0.0)
    sx = sum(p[0] for p in points)
    sy = sum(p[1] for p in points)
    n = len(points)
    return (sx / n, sy / n)


def _nearest_neighbor_chain(points: List[Point]) -> Stroke:
    """
    Build a greedy nearest-neighbor tour through all points.

    Parameters
    ----------
    points : list of Point
        Vertices to visit.

    Returns
    -------
    Stroke
        Ordered polyline visiting each point once.
    """
    if not points:
        return []
    if len(points) == 1:
        return [points[0], points[0]]

    remaining = list(points)
    chain = [remaining.pop(0)]
    while remaining:
        last = chain[-1]
        nearest_idx = min(range(len(remaining)), key=lambda i: _dist(last, remaining[i]))
        chain.append(remaining.pop(nearest_idx))
    return chain


def _edge_key(a: int, b: int) -> Edge:
    """
    Canonical undirected edge key with sorted indices.

    Parameters
    ----------
    a, b : int
        Vertex indices.

    Returns
    -------
    tuple of int
        ``(min(a, b), max(a, b))``.
    """
    return (a, b) if a <= b else (b, a)


def line_segments_to_graph(
    segments: Sequence[Stroke],
    merge_dist: float,
) -> PointGraph:
    """
    Convert line segments into a merged vertex/edge graph.

    Parameters
    ----------
    segments : sequence of Stroke
        Each stroke contributes an edge between its endpoints.
    merge_dist : float
        Grid size for merging nearby endpoints.

    Returns
    -------
    PointGraph
        Deduplicated vertices and edges.
    """
    vertices: List[Point] = []
    index_map: Dict[Tuple[int, int], int] = {}
    grid = max(0.5, merge_dist)
    edges: List[Edge] = []
    edge_set: set[Edge] = set()

    def vertex_index(point: Point) -> int:
        """Return the vertex index for ``point``, merging by grid cell."""
        key = (int(round(point[0] / grid)), int(round(point[1] / grid)))
        if key not in index_map:
            index_map[key] = len(vertices)
            vertices.append(point)
        return index_map[key]

    for segment in segments:
        if len(segment) < 2:
            continue
        start, end = segment[0], segment[-1]
        if _dist(start, end) < grid * 0.25:
            continue
        ia, ib = vertex_index(start), vertex_index(end)
        if ia == ib:
            continue
        ek = _edge_key(ia, ib)
        if ek not in edge_set:
            edge_set.add(ek)
            edges.append(ek)

    return PointGraph(vertices=vertices, edges=edges)


def branches_to_point_graph(
    branches: Sequence[Branch],
    merge_dist: float = 0.5,
) -> PointGraph:
    """
    Convert legacy branch polylines to a point graph (endpoints only).

    Parameters
    ----------
    branches : sequence of Branch
        Ordered vertex chains from legacy SVG.
    merge_dist : float, optional
        Merge radius for shared endpoints, by default 0.5.

    Returns
    -------
    PointGraph
        Graph with one edge per branch.
    """
    segments = [[branch[0], branch[-1]] for branch in branches if len(branch) >= 2]
    return line_segments_to_graph(segments, merge_dist)


def _merge_index_chains(chains: List[List[int]]) -> List[List[int]]:
    """
    Join chains when one's tip meets another's start.

    Parameters
    ----------
    chains : list of list of int
        Vertex index polylines.

    Returns
    -------
    list of list of int
        Merged chains where endpoints connect.
    """
    if len(chains) <= 1:
        return chains

    result = [list(chain) for chain in chains]
    merged = True
    while merged:
        merged = False
        for i in range(len(result)):
            for j in range(len(result)):
                if i == j:
                    continue
                head, tail = result[i], result[j]
                if head[-1] == tail[0]:
                    result[i] = head + tail[1:]
                    del result[j]
                    merged = True
                    break
                if tail[-1] == head[0]:
                    result[i] = tail + head[1:]
                    del result[j]
                    merged = True
                    break
            if merged:
                break
    return result


def _extend_chain_from_tail(
    chain: List[int],
    edge_list: Sequence[Edge],
    visited: set[Edge],
) -> List[int]:
    """
    Extend ``chain`` from its last vertex using unvisited edges in list order.

    Parameters
    ----------
    chain : list of int
        Vertex index polyline built so far.
    edge_list : sequence of Edge
        Annotation-ordered edges.
    visited : set of Edge
        Canonical edges already consumed.

    Returns
    -------
    list of int
        Extended vertex index chain.
    """
    while True:
        tail = chain[-1]
        extended = False
        for a, b in edge_list:
            ek = _edge_key(a, b)
            if ek in visited:
                continue
            if tail == a:
                visited.add(ek)
                chain.append(b)
                extended = True
                break
            if tail == b:
                visited.add(ek)
                chain.append(a)
                extended = True
                break
        if not extended:
            break
    return chain


def _edges_to_chains(graph: PointGraph) -> List[Stroke]:
    """
    Walk edges into continuous polylines following annotation order.

    Each new edge starts a chain when it cannot continue the current tail.
    Continuation always moves from the current tip to the next linked vertex
    (e.g. 1 → 2 → 3, never 3 → 2 when 2 → 3 is intended).

    Parameters
    ----------
    graph : PointGraph
        Input graph.

    Returns
    -------
    list of Stroke
        Coordinate polylines following chained edges.
    """
    if not graph.edges:
        return []

    edge_list = list(graph.edges)
    visited: set[Edge] = set()
    index_chains: List[List[int]] = []

    for a, b in edge_list:
        ek = _edge_key(a, b)
        if ek in visited:
            continue
        visited.add(ek)
        index_chains.append(_extend_chain_from_tail([a, b], edge_list, visited))

    index_chains = _merge_index_chains(index_chains)

    return [
        [graph.vertices[i] for i in chain]
        for chain in index_chains
        if len(chain) >= 2
    ]


def graph_to_drawing_strokes(
    graph: PointGraph,
    mode: PointConnectMode,
) -> List[Stroke]:
    """
    Convert a point graph to mouse-ready strokes.

    Parameters
    ----------
    graph : PointGraph
        Vertices and edges.
    mode : PointConnectMode
        ``BRANCHES`` chains edges; ``SEGMENTS`` draws each edge separately;
        ``NEAREST`` ignores edges and uses a greedy tour.

    Returns
    -------
    list of Stroke
        Polylines in the graph's coordinate space.
    """
    if len(graph.vertices) < 2 or not graph.edges:
        return []

    if mode == PointConnectMode.SEGMENTS:
        return [
            [graph.vertices[a], graph.vertices[b]]
            for a, b in graph.edges
        ]

    if mode == PointConnectMode.BRANCHES:
        return _edges_to_chains(graph)

    if mode == PointConnectMode.NEAREST:
        return [_nearest_neighbor_chain(list(graph.vertices))]

    return _edges_to_chains(graph)


def branches_to_drawing_strokes(
    branches: List[Branch],
    mode: PointConnectMode,
) -> List[Stroke]:
    """
    Convert legacy branches to drawing strokes via an intermediate graph.

    Parameters
    ----------
    branches : list of Branch
        Legacy branch polylines.
    mode : PointConnectMode
        Edge chaining strategy.

    Returns
    -------
    list of Stroke
        Mouse-ready polylines.
    """
    return graph_to_drawing_strokes(branches_to_point_graph(branches), mode)
