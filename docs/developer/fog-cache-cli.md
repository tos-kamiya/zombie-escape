# Fog Cache CLI

This project ships fog overlay cache files as bundled resources in
`src/zombie_escape/assets/fog_cache/`.

## Build Command

Generate fog cache files for all available stage cell sizes and all fog
profiles (`DARK0`, `DARK1`, `DARK2`):

```bash
uv run -p .venv/bin/python -m zombie_escape --build-fog-cache
```

Backward-compatible alias:

```bash
uv run -p .venv/bin/python -m zombie_escape --build-fog-cache-dark0
```

The alias is deprecated and prints a warning.

## Output

- Output directory: `src/zombie_escape/assets/fog_cache/`
- Output format: compressed `npz` files containing `numpy.uint8` alpha planes
  for `hard` and `combined` fog layers.

## Runtime Behavior

- Startup check requires fog cache files to be readable before entering title.
- Normal gameplay startup does not generate fog overlays; it consumes loaded
  cache files.
