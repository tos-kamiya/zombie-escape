# Rubble Relief Table

`RubbleWall` decoration (polygon points, per-edge border widths, and rotation scale)
is generated ahead of time and stored as constants.

- Generator script: `scripts/generate_rubble_relief_table.py`
- Generated file: `src/zombie_escape/render_assets/rubble_relief_table.py`

## Regenerate

Run from repository root:

```bash
uv run -p .venv/bin/python scripts/generate_rubble_relief_table.py
```

## Notes

- Do not hand-edit `rubble_relief_table.py`; regenerate it from the script.
- When changing rubble relief formulas or variant seeds, rerun the script and commit both:
  - `scripts/generate_rubble_relief_table.py`
  - `src/zombie_escape/render_assets/rubble_relief_table.py`
