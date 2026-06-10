# Speed Calibrator

**Binary search** tool to find the maximum cast speed still detected by the game.

## Launch

```bash
go-calibrate.bat
```

Or:

```bash
python speed-calibrator/main.py
```

## Procedure (~8–12 trials)

1. **Overlay (P)** — place the zone where the game accepts drawing.
2. Choose a **pattern** (line, cross, arc) and a **size**.
3. **Run trial (C)** — draws with the proposed parameters.
4. In the game, check whether the stroke registered correctly:
   - **Detected ✓ (Y)** — the game recorded the draw
   - **Missed ✗ (N)** — stroke missing, cut off, or incorrect
5. Repeat until convergence.

## Phases

| Phase | Searches | Fixed |
|-------|----------|-------|
| 1 | Delay between points (ms/pt) | Interpolation step (px) |
| 2 | Interpolation step (px) | Best delay from phase 1 |

When complete, a copyable `TURBO_PACING` snippet for `src/mouse_drawer.py` is shown.

**Push faster** — restarts binary search **below** the best delay found (floor 0.05 ms/pt) without resetting everything.

## Shortcuts

| Key | Action |
|-----|--------|
| `P` | Overlay |
| `C` | Run trial |
| `Y` | Detected |
| `N` | Missed |
