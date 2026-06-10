#!/usr/bin/env python3
"""
Resize every image in this folder to square WebP files in ./output.

Usage (from project root):
    python images/TODO/resize.py
    python images/TODO/resize.py --size 128

Or from this folder:
    python resize.py --size 100
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from PIL import Image

DEFAULT_SIZE = 100
SUPPORTED = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".gif", ".tif", ".tiff"}

INPUT_DIR = Path(__file__).resolve().parent
OUTPUT_DIR = INPUT_DIR / "output"


def resize_to_square(image: Image.Image, size: int) -> Image.Image:
    """
    Stretch ``image`` to exactly ``size``×``size`` (no letterbox padding).

    Parameters
    ----------
    image : PIL.Image.Image
        Source raster.
    size : int
        Output width and height in pixels.

    Returns
    -------
    PIL.Image.Image
        RGBA image of exactly ``size``×``size``.
    """
    return image.convert("RGBA").resize((size, size), Image.Resampling.LANCZOS)


def convert_file(source: Path, destination: Path, size: int) -> None:
    """
    Load, resize, and save one image as WebP.

    Parameters
    ----------
    source : Path
        Input image path.
    destination : Path
        Output ``.webp`` path.
    size : int
        Output square side length in pixels.

    Returns
    -------
    None
    """
    with Image.open(source) as img:
        result = resize_to_square(img, size)
        destination.parent.mkdir(parents=True, exist_ok=True)
        result.save(destination, format="WEBP", quality=90, method=6)


def discover_sources() -> list[Path]:
    """
    List convertible image files in ``INPUT_DIR`` (not in ``output/``).

    Returns
    -------
    list of Path
        Sorted source file paths.
    """
    return sorted(
        path
        for path in INPUT_DIR.iterdir()
        if path.is_file()
        and path.suffix.lower() in SUPPORTED
        and path.name != Path(__file__).name
    )


def main() -> int:
    """
    Convert all source images to square WebP files in ``output/``.

    Returns
    -------
    int
        Process exit code.
    """
    parser = argparse.ArgumentParser(
        description="Resize images in this folder to square WebP files in ./output."
    )
    parser.add_argument(
        "--size",
        type=int,
        default=DEFAULT_SIZE,
        metavar="N",
        help=f"Output square side length in pixels (default: {DEFAULT_SIZE}).",
    )
    args = parser.parse_args()
    if args.size < 1:
        print("--size must be at least 1.", file=sys.stderr)
        return 1

    sources = discover_sources()
    if not sources:
        print(f"No images found in {INPUT_DIR}", file=sys.stderr)
        print(f"Supported extensions: {', '.join(sorted(SUPPORTED))}", file=sys.stderr)
        return 1

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    for source in sources:
        out_name = source.stem + ".webp"
        destination = OUTPUT_DIR / out_name
        convert_file(source, destination, args.size)
        print(f"{source.name} -> {destination.relative_to(INPUT_DIR)}")

    print(f"\n{len(sources)} image(s) written to {OUTPUT_DIR} ({args.size}×{args.size})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
