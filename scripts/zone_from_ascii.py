#!/usr/bin/env python3
"""Generate stage zone settings from ASCII art."""

from __future__ import annotations

import argparse
import sys
import unicodedata

# Keep ASCII markers aligned with docs/design/level-generation.md
# (Blueprint Legend) as much as possible.
MOVING_FLOOR_MAP = {
    "^": "up",
    "v": "down",
    "<": "left",
    ">": "right",
}

PITFALL_CHAR = "x"
REINFORCED_WALL_CHAR = "R"
FALL_SPAWN_CHAR = "?"
SPIKY_PLANT_CHAR = "h"
PUDDLE_CHAR = "w"


def _read_ascii(path: str | None) -> list[str]:
    if path:
        with open(path, encoding="utf-8") as handle:
            lines = handle.read().splitlines()
    else:
        lines = sys.stdin.read().splitlines()
    lines = [unicodedata.normalize("NFKC", line) for line in lines]
    if not lines:
        raise ValueError("No ASCII input provided.")
    max_width = max(len(line) for line in lines)
    padded = [line.ljust(max_width, ".") for line in lines]
    return padded


def _normalize_line(line: str) -> str:
    return "".join("." if ch in {" ", "\t"} else ch for ch in line)


def _compress_rectangles(
    grid: list[str], target: str
) -> list[tuple[int, int, int, int]]:
    rows = len(grid)
    cols = len(grid[0]) if rows else 0
    seen: set[tuple[int, int]] = set()
    rects: list[tuple[int, int, int, int]] = []
    for y in range(rows):
        for x in range(cols):
            if (x, y) in seen or grid[y][x] != target:
                continue
            width = 0
            while (
                x + width < cols
                and grid[y][x + width] == target
                and (x + width, y) not in seen
            ):
                width += 1
            height = 1
            while y + height < rows:
                can_extend = True
                for dx in range(width):
                    cell = (x + dx, y + height)
                    if cell in seen or grid[y + height][x + dx] != target:
                        can_extend = False
                        break
                if not can_extend:
                    break
                height += 1
            for dy in range(height):
                for dx in range(width):
                    seen.add((x + dx, y + dy))
            rects.append((x, y, width, height))
    return rects


def _collect_zone_letters(grid: list[str]) -> list[str]:
    letters = sorted(
        {
            ch
            for row in grid
            for ch in row
            if "A" <= ch <= "Z" and ch != REINFORCED_WALL_CHAR
        }
    )
    return letters


def _validate_grid(grid: list[str]) -> None:
    allowed = set(MOVING_FLOOR_MAP) | {
        PITFALL_CHAR,
        REINFORCED_WALL_CHAR,
        FALL_SPAWN_CHAR,
        SPIKY_PLANT_CHAR,
        PUDDLE_CHAR,
        ".",
    }
    allowed |= {chr(code) for code in range(ord("A"), ord("Z") + 1)}
    for y, row in enumerate(grid):
        for x, ch in enumerate(row):
            if ch not in allowed:
                raise ValueError(f"Unknown character '{ch}' at ({x}, {y}).")


def generate_zone_data(lines: list[str]) -> dict[str, object]:
    grid = [_normalize_line(line) for line in lines]
    _validate_grid(grid)

    output: dict[str, object] = {}

    moving_floor_zones: dict[str, list[list[int]]] = {
        "up": _compress_rectangles(grid, "^"),
        "down": _compress_rectangles(grid, "v"),
        "left": _compress_rectangles(grid, "<"),
        "right": _compress_rectangles(grid, ">"),
    }
    output["moving_floor_zones"] = moving_floor_zones
    output["pitfall_zones"] = _compress_rectangles(grid, PITFALL_CHAR)
    output["reinforced_wall_zones"] = _compress_rectangles(grid, REINFORCED_WALL_CHAR)
    output["fall_spawn_zones"] = _compress_rectangles(grid, FALL_SPAWN_CHAR)
    output["spiky_plant_zones"] = _compress_rectangles(grid, SPIKY_PLANT_CHAR)
    output["puddle_zones"] = _compress_rectangles(grid, PUDDLE_CHAR)

    for letter in _collect_zone_letters(grid):
        key = f"zone_{letter.lower()}"
        output[key] = _compress_rectangles(grid, letter)

    return output


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Generate stage zone settings JSON from ASCII art."
    )
    parser.add_argument(
        "path",
        nargs="?",
        help="ASCII art input file (reads stdin if omitted).",
    )
    args = parser.parse_args()

    try:
        lines = _read_ascii(args.path)
        payload = generate_zone_data(lines)
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    sys.stdout.write(f"{payload}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
