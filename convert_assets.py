"""Convert WebP/PNG raster assets to traced SVG files (path/sigils, path/signs)."""

from __future__ import annotations

import argparse
import sys

from src.webp_to_path import convert_all


def main() -> int:
    """
    CLI entry point for batch asset conversion.

    Returns
    -------
    int
        Process exit code (``0`` on success).
    """
    parser = argparse.ArgumentParser(
        description="Convert images/webp to path/sigils and path/signs."
    )
    parser.add_argument(
        "--bootstrap-svg",
        action="store_true",
        help="Migrate images/sigils and images/signs to path/ when no WebP is found.",
    )
    parser.add_argument("-q", "--quiet", action="store_true")
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Save B&W masks to images/webp/_debug/.",
    )
    args = parser.parse_args()

    results = convert_all(
        include_bootstrap_svg=args.bootstrap_svg,
        verbose=not args.quiet,
        debug=args.debug,
    )

    if not results:
        print(
            "No files converted.\n"
            "Place images in images/webp/sigils/ and images/webp/signs/\n"
            "or define images/webp/manifest.json for a flat folder.\n"
            "Use --bootstrap-svg to migrate existing Inkscape SVG files.",
            file=sys.stderr,
        )
        return 1

    if not args.quiet:
        print(f"\n{len(results)} file(s) converted.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
