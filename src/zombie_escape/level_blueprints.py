# Blueprint generator for randomized layouts.

import random
from typing import List, Tuple

GRID_COLS = 48
GRID_ROWS = 30
TILE_SIZE = 50  # world units per cell; adjust to scale the whole map

EXITS_PER_SIDE = 1  # currently fixed to 1 per side (can be tuned)
NUM_WALL_LINES = 80  # reduced density (roughly 1/5 of previous 450)
WALL_MIN_LEN = 3
WALL_MAX_LEN = 10
SPAWN_MARGIN = 3  # keep spawns away from walls/edges
SPAWN_ZOMBIES = 3
STEEL_BEAM_CHANCE = 0.05

# Legend:
# O: outside area (win when car reaches)
# B: outer wall band (solid)
# E: exit tile (opening in outer wall)
# 1: internal wall
# .: empty floor
# P: player spawn candidate
# C: car spawn candidate
# Z: zombie spawn candidate

def _collect_exit_adjacent_cells(grid: List[List[str]]) -> set[Tuple[int, int]]:
    """Return a set of cells that touch any exit (including diagonals)."""
    cols, rows = len(grid[0]), len(grid)
    forbidden = set()
    for y in range(rows):
        for x in range(cols):
            if grid[y][x] == "E":
                for dy in (-1, 0, 1):
                    for dx in (-1, 0, 1):
                        nx, ny = x + dx, y + dy
                        if 0 <= nx < cols and 0 <= ny < rows:
                            forbidden.add((nx, ny))
    return forbidden


def _init_grid(cols: int, rows: int) -> List[List[str]]:
    grid = [["." for _ in range(cols)] for _ in range(rows)]
    # Outside band
    for x in range(cols):
        grid[0][x] = "O"
        grid[rows - 1][x] = "O"
    for y in range(rows):
        grid[y][0] = "O"
        grid[y][cols - 1] = "O"
    # Outer wall band just inside outside
    for x in range(1, cols - 1):
        grid[1][x] = "B"
        grid[rows - 2][x] = "B"
    for y in range(1, rows - 1):
        grid[y][1] = "B"
        grid[y][cols - 2] = "B"
    return grid


def _place_exits(grid: List[List[str]], exits_per_side: int) -> None:
    cols, rows = len(grid[0]), len(grid)
    rng = random.randint
    used = set()
    def pick_pos(side: str) -> Tuple[int, int]:
        if side in ("top", "bottom"):
            x = rng(2, cols - 3)
            y = 1 if side == "top" else rows - 2
        else:
            y = rng(2, rows - 3)
            x = 1 if side == "left" else cols - 2
        return x, y

    for side in ("top", "bottom", "left", "right"):
        for _ in range(exits_per_side):
            x, y = pick_pos(side)
            # avoid duplicates; retry a few times
            for _ in range(10):
                if (x, y) not in used:
                    break
                x, y = pick_pos(side)
            used.add((x, y))
            grid[y][x] = "E"


def _place_internal_walls(grid: List[List[str]]) -> None:
    cols, rows = len(grid[0]), len(grid)
    rng = random.randint
    # Avoid placing walls adjacent to exits: collect forbidden cells (exits + neighbors)
    forbidden = _collect_exit_adjacent_cells(grid)

    for _ in range(NUM_WALL_LINES):
        length = rng(WALL_MIN_LEN, WALL_MAX_LEN)
        horizontal = random.choice([True, False])
        if horizontal:
            y = rng(2, rows - 3)
            x = rng(2, cols - 2 - length)
            for i in range(length):
                if (x + i, y) in forbidden:
                    continue
                if grid[y][x + i] in (".", "Z"):
                    grid[y][x + i] = "1"
        else:
            x = rng(2, cols - 3)
            y = rng(2, rows - 2 - length)
            for i in range(length):
                if (x, y + i) in forbidden:
                    continue
                if grid[y + i][x] in (".", "Z"):
                    grid[y + i][x] = "1"


def _place_steel_beams(grid: List[List[str]], chance: float = STEEL_BEAM_CHANCE) -> set[Tuple[int, int]]:
    """Pick individual cells for steel beams, avoiding exits and their neighbors."""
    cols, rows = len(grid[0]), len(grid)
    forbidden = _collect_exit_adjacent_cells(grid)
    beams: set[Tuple[int, int]] = set()
    for y in range(2, rows - 2):
        for x in range(2, cols - 2):
            if (x, y) in forbidden:
                continue
            if grid[y][x] not in (".", "1"):
                continue
            if random.random() < chance:
                beams.add((x, y))
    return beams


def _pick_empty_cell(grid: List[List[str]], margin: int, forbidden: set[Tuple[int, int]] | None = None) -> Tuple[int, int]:
    cols, rows = len(grid[0]), len(grid)
    attempts = 0
    forbidden = forbidden or set()
    while attempts < 2000:
        attempts += 1
        x = random.randint(margin, cols - margin - 1)
        y = random.randint(margin, rows - margin - 1)
        if grid[y][x] == "." and (x, y) not in forbidden:
            return x, y
    # Fallback: scan for any acceptable cell
    for y in range(margin, rows - margin):
        for x in range(margin, cols - margin):
            if grid[y][x] == "." and (x, y) not in forbidden:
                return x, y
    return cols // 2, rows // 2


def generate_random_blueprint(steel_chance: float | None = None) -> dict:
    grid = _init_grid(GRID_COLS, GRID_ROWS)
    _place_exits(grid, EXITS_PER_SIDE)
    _place_internal_walls(grid)
    steel_beams = _place_steel_beams(grid, steel_chance if steel_chance is not None else STEEL_BEAM_CHANCE)

    # Spawns: player, car, zombies
    px, py = _pick_empty_cell(grid, SPAWN_MARGIN, forbidden=steel_beams)
    grid[py][px] = "P"
    cx, cy = _pick_empty_cell(grid, SPAWN_MARGIN, forbidden=steel_beams)
    grid[cy][cx] = "C"
    for _ in range(SPAWN_ZOMBIES):
        zx, zy = _pick_empty_cell(grid, SPAWN_MARGIN, forbidden=steel_beams)
        grid[zy][zx] = "Z"

    blueprint_rows = ["".join(row) for row in grid]
    return {"grid": blueprint_rows, "steel_cells": steel_beams}


def choose_blueprint(config: dict | None = None) -> dict:
    # Currently only random generation; hook for future variants.
    steel_conf = (config or {}).get("steel_beams", {})
    try:
        steel_chance = float(steel_conf.get("chance", STEEL_BEAM_CHANCE))
    except (TypeError, ValueError):
        steel_chance = STEEL_BEAM_CHANCE
    return generate_random_blueprint(steel_chance=steel_chance)
