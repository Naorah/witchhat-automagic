# Witchhat Automagic

Auto-drawer for Witch Hat spells (or any application that accepts mouse drawing).

A spell is composed of:

1. **A sigil** at the center
2. **Signs** distributed evenly around the circle (configurable types and directions)
3. **A circle** drawn last — optionally closed to complete the spell

## Features

- Targeting overlay with drag and resize
- Configurable draw speed (normal and turbo pacing)
- Optional hand tremor (shake) for more natural strokes
- Manual asset annotation and raster-to-SVG conversion pipeline
- **Fast Sample Maker** — test one sigil or sign in isolation
- **Speed Calibrator** — find the fastest reliable cast pacing for your setup

## Requirements

- Python 3.10+
- Windows (tested with mouse simulation via `pynput`)

## Installation

```bash
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
```

## Tools

| Tool | Launcher | Entry point |
|------|----------|-------------|
| Spell caster | `go_cast.bat` | `main.py` |
| Asset annotator | `go_annotation.bat` | `annotate_assets.py` |
| Fast sample maker | `go-sample.bat` | `fast-sample-maker/main.py` |
| Speed calibrator | `go-calibrate.bat` | `speed-calibrator/main.py` |

With the virtual environment activated you can also run:

```bash
python main.py
python annotate_assets.py
python fast-sample-maker/main.py
python speed-calibrator/main.py
```

See also:

- [fast-sample-maker/README.md](fast-sample-maker/README.md)
- [speed-calibrator/README.md](speed-calibrator/README.md)

## Spell caster usage

1. Choose the **sigil**, **number of signs**, their **type**, and **direction** (inward or outward).
2. Set **draw speed** with the slider (`0` = turbo ~1 ms/pt, `0.01` = normal ~6 ms/pt).
3. Optionally enable **Shake** and set tremor intensity.
4. Enable **Targeting overlay** to show or hide the gray preview (transparent center).
5. **Drag the overlay** to position it and **resize the circle** by pulling the border (white handle at the top).
6. Toggle **Close circle (complete spell)** to include or skip the final closure segment.
7. Click **Cast spell** (or press `C`): the overlay hides during drawing; a 3-second countdown runs, then automatic drawing (sigil → signs → circle).

### Keyboard shortcuts

| Key | Action |
|-----|--------|
| `C` | Cast spell (works from spinboxes too) |
| `P` | Toggle targeting overlay |
| `Esc` | Cancel draw or hide overlay |

### Debug mode

Check **Debug mode (no mouse)** to test the sequence without moving the cursor.

## Fast sample maker

Quick tool to cast a single sigil or sign at an overlay position. Supports random rotation, size, and shake, plus experimental **Speed ++** turbo pacing.

```bash
go-sample.bat
```

## Speed calibrator

Binary-search tool to find the fastest draw pacing still detected by the game. Produces a `TURBO_PACING` snippet ready to paste into `src/mouse_drawer.py`.

```bash
go-calibrate.bat
```

## Manual annotation

To define points and links by hand (recommended for accurate strokes):

```bash
python annotate_assets.py
```

Keyboard: `P` points, `L` links, `M` move, `D` delete point, `Enter` validate.

## Asset pipeline

### 1. Raster sources (WebP / PNG)

Place source images in:

- `images/webp/sigils/` — sigils (`.webp`, `.png`, `.jpg`)
- `images/webp/signs/` — signs

For a flat `images/webp/` folder, list files in `images/webp/manifest.json`:

```json
{
  "sigils": ["fire", "water"],
  "signs": ["column", "levitation"]
}
```

### 2. Convert to SVG paths

```bash
python convert_assets.py
```

To debug a difficult image (binary masks written to disk):

```bash
python convert_assets.py --debug
```

Debug previews are written to `images/webp/_debug/`.

Output SVG files (skeleton strokes or manually annotated point graphs) go to:

- `path/sigils/`
- `path/signs/`

Each file uses a normalized viewBox `0 0 100 100`.

Migrate from legacy Inkscape SVG (`images/sigils/`, `images/signs/`):

```bash
python convert_assets.py --bootstrap-svg
```

The app uses `path/` automatically when it contains SVG files; otherwise it falls back to legacy sources.

## Project structure

```
main.py                 # Spell caster entry point
annotate_assets.py      # Manual point/link editor
convert_assets.py       # WebP/PNG → path/sigils|signs
go_cast.bat             # Launch spell caster
go_annotation.bat       # Launch annotator
go-sample.bat           # Launch fast sample maker
go-calibrate.bat        # Launch speed calibrator
fast-sample-maker/      # Single-asset cast tool
speed-calibrator/       # Pacing calibration tool
src/
  models.py             # Spell configuration
  assets.py             # SVG catalogue
  svg_parser.py         # SVG parsing and path sampling
  webp_to_path.py       # Raster vectorization → SVG polylines
  point_graph.py        # Vertices + edges → drawing strokes
  point_graph_io.py     # Read/write point-graph SVG
  spell_composer.py     # Compose sigil + signs + circle
  overlay_window.py     # Targeting overlay
  control_panel.py      # Configuration UI
  mouse_drawer.py       # Mouse execution
  ui/                   # Shared theme and shell widgets
images/
  webp/sigils/          # Raster sigil sources
  webp/signs/           # Raster sign sources
  sigils/               # Legacy Inkscape (optional)
  signs/
path/
  sigils/               # SVG paths for auto-drawer
  signs/
```

## Draw order

1. Sigil (center)
2. Signs (clockwise from the top)
3. Main circle arc (~97% of the full turn)
4. Circle closure (final segment, when **Close circle** is enabled)

## Disclaimer

This is a third-party automation tool. Use it at your own risk. It is not affiliated with or endorsed by the Witch Hat game or its developers.
