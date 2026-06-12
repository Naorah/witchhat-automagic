# Vectorise Tool

CLI batch tool that converts raster images to compact filled-contour SVG files.

Unlike `convert_assets.py` (skeleton centreline strokes), this tool traces the **outer boundary** of ink blobs using contour detection, RDP simplification, and Chaikin corner smoothing.

## Usage

```bash
python vectorise-tool/vectorise.py --folder images/webp/signs --output output/ --threshold 0.450 --smooth 0.5
```

Or with the launcher:

```bash
go-vectorise.bat --folder images/webp/signs --output output/ --threshold 0.450 --smooth 0.75
```

## Options

| Option | Default | Description |
|--------|---------|-------------|
| `--folder` | *(required)* | Source folder of raster images |
| `--output` | *(required)* | Output folder for SVG files |
| `--threshold` | `0.450` | Binarisation cutoff in `[0, 1]` (dark ink below threshold) |
| `--smooth` | `0.5` | Corner smoothing degree in `[0, 1]` (0 = none, 1 = max) |
| `--epsilon-ratio` | `0.006` | RDP simplification factor relative to image scale |
| `--debug` | off | Save binary masks to `output/_debug/` |
| `-q` / `--quiet` | off | Reduce console output |

Supported input formats: `.webp`, `.png`, `.jpg`, `.jpeg`.

## Output format

Each SVG is a single filled path in a `0 0 100 100` viewBox:

```xml
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100">
  <title>Example</title>
  <path fill="#000" fill-rule="evenodd" d="M12.34,56.78 L... Z"/>
</svg>
```

Holes (e.g. ring shapes) are handled via `fill-rule="evenodd"`.

## Limitation

On thin line-art glyphs, contour vectorisation produces **closed loops around the ink silhouette**, not a single centreline. For mouse-drawn spell strokes, prefer `convert_assets.py` (skeleton pipeline).
