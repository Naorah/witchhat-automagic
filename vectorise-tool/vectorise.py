#!/usr/bin/env python3
"""Batch contour vectorisation CLI for raster images."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

TOOL_DIR = Path(__file__).resolve().parent
if str(TOOL_DIR) not in sys.path:
    sys.path.insert(0, str(TOOL_DIR))

from contour_vectorise import (  # noqa: E402
    DEFAULT_EPSILON_RATIO,
    DEFAULT_SMOOTH,
    VectoriseResult,
    iter_raster_files,
    vectorise_file,
)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Vectorise raster images to compact filled-contour SVG files."
    )
    parser.add_argument(
        "--folder",
        type=Path,
        required=True,
        help="Source folder containing raster images.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        required=True,
        help="Output folder for SVG files.",
    )
    parser.add_argument(
        "--threshold",
        type=float,
        default=0.450,
        help="Binarisation threshold in [0, 1] (default: 0.450).",
    )
    parser.add_argument(
        "--smooth",
        type=float,
        default=DEFAULT_SMOOTH,
        metavar="[0-1]",
        help="Corner smoothing degree from 0 (none) to 1 (max). Default: 0.5.",
    )
    parser.add_argument(
        "--epsilon-ratio",
        type=float,
        default=DEFAULT_EPSILON_RATIO,
        help=f"RDP epsilon factor relative to image scale (default: {DEFAULT_EPSILON_RATIO}).",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Save binary masks to output/_debug/.",
    )
    parser.add_argument("-q", "--quiet", action="store_true")
    return parser.parse_args()


def main() -> int:
    """
    Run batch contour vectorisation over a folder of raster images.

    Returns
    -------
    int
        Process exit code (``0`` on success, ``1`` if nothing was converted).
    """
    args = _parse_args()
    if not 0.0 <= args.smooth <= 1.0:
        print("--smooth must be between 0 and 1.", file=sys.stderr)
        return 1

    folder = args.folder.resolve()
    output_dir = args.output.resolve()
    debug_dir = output_dir / "_debug" if args.debug else None

    if not folder.is_dir():
        print(f"Folder not found: {folder}", file=sys.stderr)
        return 1

    sources = list(iter_raster_files(folder))
    if not sources:
        print(f"No supported images in {folder}", file=sys.stderr)
        return 1

    results: list[VectoriseResult] = []
    failures: list[tuple[Path, str]] = []

    for source in sources:
        target = output_dir / f"{source.stem}.svg"
        try:
            result = vectorise_file(
                source,
                target,
                threshold=args.threshold,
                epsilon_ratio=args.epsilon_ratio,
                smooth=args.smooth,
                debug=args.debug,
                debug_dir=debug_dir,
            )
            results.append(result)
            if not args.quiet:
                print(
                    f"{source.name} -> {target.name} "
                    f"({result.contour_count} contour(s), {result.point_count} point(s))"
                )
        except ValueError as exc:
            failures.append((source, str(exc)))
            if not args.quiet:
                print(f"SKIP {source.name}: {exc}", file=sys.stderr)

    if not results:
        print("No files converted.", file=sys.stderr)
        return 1

    if not args.quiet:
        print(f"\n{len(results)} file(s) converted.", end="")
        if failures:
            print(f" {len(failures)} skipped.", end="")
        print()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
