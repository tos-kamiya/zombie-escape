# Fog Cache CLI

This project ships fog overlay cache files as bundled resources in
`src/zombie_escape/assets/fog_cache/`.

## Build Command

Generate fog cache files for all available stage cell sizes and all fog
profiles (`DARK0`, `DARK1`, `DARK2`):

```bash
uv run -p .venv/bin/python -m zombie_escape --build-fog-cache
```

## Output

- Output directory: `src/zombie_escape/assets/fog_cache/`
- Output format: PNG files (`hard` and `combined` layers saved separately)
- Filename rule: `fog_<profile>_cell<cell_size>_<layer>.v<format>.png`
  - Example: `fog_dark0_cell16_hard.v1.png`
  - Example: `fog_dark0_cell16_combined.v1.png`

## Bundled Fog Asset Format (PNG + Filename Version)

Bundled fog files are now PNG release assets (not runtime-generated cache
files).

- Target output directory: `src/zombie_escape/assets/fog_cache/`
- Target format: 8-bit grayscale PNG alpha-mask images
- Layer split: one file per layer (`hard`, `combined`)
- Versioning rule: embed format version in filename
  - Example: `fog_dark0_cell16_hard.v1.png`
  - Example: `fog_dark0_cell16_combined.v1.png`
- Runtime policy: load bundled files only; do not regenerate at user runtime
- Validation policy: on mismatch/missing assets, fail startup with explicit error

Notes:
- Bundled fog files are treated as release assets, not runtime-generated cache.

## Runtime Behavior

- Startup check requires fog cache files to be readable before entering title.
- Normal gameplay startup does not generate fog overlays; it consumes loaded
  cache files.
