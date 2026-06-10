# Fast Sample Maker

Quick interface to test a single **sigil** or **sign**: overlay targeting, rotation/size controls, and immediate drawing on cast.

## Launch

From the project root (with the virtual environment activated):

```bash
go-sample.bat
```

Or:

```bash
python fast-sample-maker/main.py
```

## Usage

1. Browse the combined **Sigils** then **Signs** list (separated by a divider).
2. Set **rotation** (-180° to +180°) or check **Random rotation** (0° to 360° on each cast).
3. Set **size** (100% to 500%) or check **Random size** (200% to 400% on each cast).
4. **Show overlay** (or press `P`) — semi-transparent preview of where the draw will land; **drag it** onto the game area.
5. Click a thumbnail to select an asset.
6. **Speed ++ (experimental)** — accelerated turbo (~0.7 ms/point) above base turbo (~1 ms).
7. Optionally enable **Shake (hand tremor)** with fixed or **Random shake** intensity.
8. **Cast** (button or `C`, including from numeric fields) — starts drawing at the overlay position.
9. **Cancel** — interrupts a draw in progress.
10. **Esc** — hides the overlay or cancels an active draw.

## Files

| File | Role |
|------|------|
| `main.py` | Entry point |
| `panel.py` | Main control panel |
| `asset_grid.py` | Clickable thumbnail grid |
| `asset_preview.py` | SVG/WebP thumbnail generation |
| `composer.py` | Single-asset stroke composition |
| `overlay.py` | Draggable targeting overlay |

Reuses parent modules: `src/assets`, `src/svg_parser`, `src/spell_composer`, `src/mouse_drawer`, `src/ui/theme`.
