# Zone From ASCII Tool

This tool converts an ASCII map into a Python literal (dicts/lists) that can be
passed to `Stage` arguments like `moving_floor_zones`, `pitfall_zones`, and
`fall_spawn_zones`.

## Usage

```bash
# Read from a file
uv run -p .venv/bin/python scripts/zone_from_ascii.py path/to/map.txt

# Read from stdin
cat path/to/map.txt | uv run -p .venv/bin/python scripts/zone_from_ascii.py

# Pipe into a formatter (example: ruff format)
uv run scripts/zone_from_ascii.py tmp.txt \
  | uv run ruff format --stdin-filename hoge.py -
```

Example formatted output:

```python
{
    "moving_floor_zones": {
        "up": [(14, 11, 2, 7)],
        "down": [(14, 0, 2, 7)],
        "left": [(18, 8, 12, 2)],
        "right": [(0, 8, 12, 2)],
    },
    "pitfall_zones": [],
    "fall_spawn_zones": [],
}
```

## Input Characters

The tool recognizes the following characters. Short lines are padded with `.`,
and spaces/tabs are treated as `.`.

- `.` empty floor
- `^` moving floor (up)
- `v` moving floor (down)
- `<` moving floor (left)
- `>` moving floor (right)
- `x` pitfall
- `?` fall spawn zone
- `A`-`Z` custom zones (emitted as `zone_a`, `zone_b`, ...)

## Output (Python Literal)

The output is intended to be dropped into a `Stage` definition:

```python
{
  "moving_floor_zones": {
    "up": [(x, y, w, h)],
    "down": [(x, y, w, h)],
    "left": [(x, y, w, h)],
    "right": [(x, y, w, h)]
  },
  "pitfall_zones": [(x, y, w, h)],
  "fall_spawn_zones": [(x, y, w, h)],
  "zone_a": [(x, y, w, h)],
  "zone_b": [(x, y, w, h)]
}
```

## Compression Behavior

Cells are compressed into rectangles using a simple heuristic:

1. Find the next unassigned cell (scan left-to-right, top-to-bottom).
2. Extend right as far as possible.
3. Extend downward as far as possible with that width.
4. Mark that rectangle as consumed and continue.

This is not an optimal tiling but is intended to keep output readable.
