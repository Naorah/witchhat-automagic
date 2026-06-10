"""Read and write point-graph SVG files for manual annotation."""

from __future__ import annotations

import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Optional

from .models import Point
from .point_graph import PointGraph
from .svg_parser import load_svg_point_graph

VIEWBOX_SIZE = 100.0


def write_point_graph_svg(
    output_path: Path,
    name: str,
    graph: PointGraph,
) -> None:
    """
    Write a point-graph SVG (vertices + edge indices).

    Parameters
    ----------
    output_path : Path
        Destination ``.svg`` file.
    name : str
        Human-readable title stored in the SVG.
    graph : PointGraph
        Vertices in viewBox coordinates and undirected edge pairs.

    Returns
    -------
    None
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)

    root = ET.Element(
        "svg",
        {
            "xmlns": "http://www.w3.org/2000/svg",
            "viewBox": f"0 0 {VIEWBOX_SIZE:g} {VIEWBOX_SIZE:g}",
            "data-draw-mode": "point-graph",
            "role": "img",
            "focusable": "false",
        },
    )
    title = ET.SubElement(root, "title")
    title.text = name

    group = ET.SubElement(root, "g", {"id": "graph"})
    if graph.vertices:
        vert_str = " ".join(f"{x:.2f},{y:.2f}" for x, y in graph.vertices)
        ET.SubElement(
            group,
            "polyline",
            {
                "data-role": "vertices",
                "points": vert_str,
                "fill": "none",
                "stroke": "none",
            },
        )
    if graph.edges:
        edge_str = " ".join(f"{a},{b}" for a, b in graph.edges)
        ET.SubElement(
            group,
            "polyline",
            {
                "data-role": "edges",
                "points": edge_str,
                "fill": "none",
                "stroke": "none",
            },
        )

    output_path.write_text(
        '<?xml version="1.0" encoding="UTF-8"?>\n' + ET.tostring(root, encoding="unicode"),
        encoding="utf-8",
    )


def try_load_point_graph(path: Path) -> Optional[PointGraph]:
    """
    Load a point graph from disk if the file exists and is valid.

    Parameters
    ----------
    path : Path
        SVG file path.

    Returns
    -------
    PointGraph or None
        Parsed graph, or ``None`` if missing or invalid.
    """
    if not path.is_file():
        return None
    try:
        graph = load_svg_point_graph(path)
    except (ET.ParseError, ValueError):
        return None
    if graph.vertices and graph.edges:
        return graph
    return None


def merge_nearby_vertices(
    graph: PointGraph,
    threshold: float = 1.5,
) -> PointGraph:
    """
    Merge vertices closer than ``threshold`` (duplicate clicks).

    Parameters
    ----------
    graph : PointGraph
        Input graph.
    threshold : float, optional
        Maximum Euclidean distance for merging, by default 1.5 viewBox units.

    Returns
    -------
    PointGraph
        Graph with merged vertices and remapped edges.
    """
    if not graph.vertices:
        return graph

    vertices: list[Point] = []
    remap: dict[int, int] = {}

    for idx, point in enumerate(graph.vertices):
        merged = False
        for new_idx, existing in enumerate(vertices):
            dx = point[0] - existing[0]
            dy = point[1] - existing[1]
            if dx * dx + dy * dy <= threshold * threshold:
                remap[idx] = new_idx
                merged = True
                break
        if not merged:
            remap[idx] = len(vertices)
            vertices.append(point)

    edges: list[tuple[int, int]] = []
    seen: set[tuple[int, int]] = set()
    for a, b in graph.edges:
        na, nb = remap.get(a, a), remap.get(b, b)
        if na == nb:
            continue
        key = (na, nb) if na <= nb else (nb, na)
        if key not in seen:
            seen.add(key)
            edges.append(key)

    return PointGraph(vertices=vertices, edges=edges)
