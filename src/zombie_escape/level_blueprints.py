# Blueprint generator for randomized layouts.

from .rng import get_rng

EXITS_PER_SIDE = 1  # currently fixed to 1 per side (can be tuned)
NUM_WALL_LINES = 80  # reduced density (roughly 1/5 of previous 450)
WALL_MIN_LEN = 3
WALL_MAX_LEN = 10
SPARSE_WALL_DENSITY = 0.10
SPAWN_MARGIN = 3  # keep spawns away from walls/edges
SPAWN_ZOMBIES = 3

RNG = get_rng()
STEEL_BEAM_CHANCE = 0.02

# Legend:
# O: outside area (win when car reaches)
# B: outer wall band (solid)
# E: exit tile (opening in outer wall)
# 1: internal wall
# .: empty floor
# P: player spawn candidate
# C: car spawn candidate
# Z: zombie spawn candidate


def _collect_exit_adjacent_cells(grid: list[list[str]]) -> set[tuple[int, int]]:
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


def _init_grid(cols: int, rows: int) -> list[list[str]]:
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


def _place_exits(grid: list[list[str]], exits_per_side: int) -> None:
    cols, rows = len(grid[0]), len(grid)
    rng = RNG.randint
    used = set()

    def _pick_pos(side: str) -> tuple[int, int]:
        if side in ("top", "bottom"):
            x = rng(2, cols - 3)
            y = 1 if side == "top" else rows - 2
        else:
            y = rng(2, rows - 3)
            x = 1 if side == "left" else cols - 2
        return x, y

    for side in ("top", "bottom", "left", "right"):
        for _ in range(exits_per_side):
            x, y = _pick_pos(side)
            # avoid duplicates; retry a few times
            for _ in range(10):
                if (x, y) not in used:
                    break
                x, y = _pick_pos(side)
            used.add((x, y))
            grid[y][x] = "E"


def _place_walls_default(grid: list[list[str]]) -> None:
    cols, rows = len(grid[0]), len(grid)
    rng = RNG.randint
    # Avoid placing walls adjacent to exits: collect forbidden cells (exits + neighbors)
    forbidden = _collect_exit_adjacent_cells(grid)

    for _ in range(NUM_WALL_LINES):
        length = rng(WALL_MIN_LEN, WALL_MAX_LEN)
        horizontal = RNG.choice([True, False])
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


def _place_walls_empty(grid: list[list[str]]) -> None:
    """Place no internal walls (open floor plan)."""
    pass


def _place_walls_grid_wire(grid: list[list[str]]) -> None:
    """
    Place walls using a 2-pass approach with independent layers.
    Vertical and horizontal walls are generated on separate grids to ensure
    one orientation doesn't block the other during generation.
    Finally, they are merged.
    Strictly forbids parallel adjacency within the same orientation layer.
    """
    cols, rows = len(grid[0]), len(grid)
    rng = RNG.randint
    forbidden = _collect_exit_adjacent_cells(grid)

    # Temporary grids for independent generation
    # They only track the internal walls ("1").
    grid_v = [["." for _ in range(cols)] for _ in range(rows)]
    grid_h = [["." for _ in range(cols)] for _ in range(rows)]

    # Use a similar density to default.
    lines_per_pass = int(NUM_WALL_LINES * 0.7)

    # --- Pass 1: Vertical Walls (on grid_v) ---
    for _ in range(lines_per_pass):
        length = rng(WALL_MIN_LEN, WALL_MAX_LEN)
        x = rng(2, cols - 3)
        y = rng(2, rows - 2 - length)

        can_place = True
        for i in range(length):
            cy = y + i
            # 1. Global forbidden check (exits, outer walls in main grid)
            if (x, cy) in forbidden:
                can_place = False
                break
            if grid[cy][x] not in (".",):
                can_place = False
                break
            # 2. Local self-overlap check
            if grid_v[cy][x] != ".":
                can_place = False
                break
            # 3. Parallel adjacency check (only against other vertical walls)
            if grid_v[cy][x - 1] == "1" or grid_v[cy][x + 1] == "1":
                can_place = False
                break

        if can_place:
            for i in range(length):
                grid_v[y + i][x] = "1"

    # --- Pass 2: Horizontal Walls (on grid_h) ---
    for _ in range(lines_per_pass):
        length = rng(WALL_MIN_LEN, WALL_MAX_LEN)
        x = rng(2, cols - 2 - length)
        y = rng(2, rows - 3)

        can_place = True
        for i in range(length):
            cx = x + i
            # 1. Global forbidden check
            if (cx, y) in forbidden:
                can_place = False
                break
            if grid[y][cx] not in (".",):
                can_place = False
                break
            # 2. Local self-overlap check
            if grid_h[y][cx] != ".":
                can_place = False
                break
            # 3. Parallel adjacency check (only against other horizontal walls)
            if grid_h[y - 1][cx] == "1" or grid_h[y + 1][cx] == "1":
                can_place = False
                break

        if can_place:
            for i in range(length):
                grid_h[y][x + i] = "1"

    # --- Merge Phase ---
    for y in range(rows):
        for x in range(cols):
            # If either layer has a wall, and the main grid is empty, place it.
            if (grid_v[y][x] == "1" or grid_h[y][x] == "1") and grid[y][x] == ".":
                grid[y][x] = "1"


def _place_walls_sparse(grid: list[list[str]]) -> None:
    """Place isolated wall tiles at a low density, avoiding adjacency."""
    cols, rows = len(grid[0]), len(grid)
    forbidden = _collect_exit_adjacent_cells(grid)
    for y in range(2, rows - 2):
        for x in range(2, cols - 2):
            if (x, y) in forbidden:
                continue
            if grid[y][x] != ".":
                continue
            if RNG.random() >= SPARSE_WALL_DENSITY:
                continue
            if (
                grid[y - 1][x] == "1"
                or grid[y + 1][x] == "1"
                or grid[y][x - 1] == "1"
                or grid[y][x + 1] == "1"
                or grid[y - 1][x - 1] == "1"
                or grid[y - 1][x + 1] == "1"
                or grid[y + 1][x - 1] == "1"
                or grid[y + 1][x + 1] == "1"
            ):
                continue
            grid[y][x] = "1"


WALL_ALGORITHMS = {
    "default": _place_walls_default,
    "empty": _place_walls_empty,
    "grid_wire": _place_walls_grid_wire,
    "sparse": _place_walls_sparse,
}


def _place_steel_beams(
    grid: list[list[str]], *, chance: float = STEEL_BEAM_CHANCE
) -> set[tuple[int, int]]:
    """Pick individual cells for steel beams, avoiding exits and their neighbors."""
    cols, rows = len(grid[0]), len(grid)
    forbidden = _collect_exit_adjacent_cells(grid)
    beams: set[tuple[int, int]] = set()
    for y in range(2, rows - 2):
        for x in range(2, cols - 2):
            if (x, y) in forbidden:
                continue
            if grid[y][x] not in (".", "1"):
                continue
            if RNG.random() < chance:
                beams.add((x, y))
    return beams


def _pick_empty_cell(
    grid: list[list[str]],
    margin: int,
    forbidden: set[tuple[int, int]],
) -> tuple[int, int]:
    cols, rows = len(grid[0]), len(grid)
    attempts = 0
    while attempts < 2000:
        attempts += 1
        x = RNG.randint(margin, cols - margin - 1)
        y = RNG.randint(margin, rows - margin - 1)
        if grid[y][x] == "." and (x, y) not in forbidden:
            return x, y
    # Fallback: scan for any acceptable cell
    for y in range(margin, rows - margin):
        for x in range(margin, cols - margin):
            if grid[y][x] == "." and (x, y) not in forbidden:
                return x, y
    return cols // 2, rows // 2


def _generate_random_blueprint(
    steel_chance: float, *, cols: int, rows: int, wall_algo: str = "default"
) -> dict:
    grid = _init_grid(cols, rows)
    _place_exits(grid, EXITS_PER_SIDE)

    # Select and run the wall placement algorithm
    if wall_algo not in WALL_ALGORITHMS:
        print(
            f"WARNING: Unknown wall algorithm '{wall_algo}'. Falling back to 'default'."
        )
        wall_algo = "default"

    algo_func = WALL_ALGORITHMS[wall_algo]
    algo_func(grid)

    steel_beams = _place_steel_beams(grid, chance=steel_chance)

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


def choose_blueprint(
    config: dict, *, cols: int, rows: int, wall_algo: str = "default"
) -> dict:
    # Currently only random generation; hook for future variants.
    steel_conf = config.get("steel_beams", {})
    try:
        steel_chance = float(steel_conf.get("chance", STEEL_BEAM_CHANCE))
    except (TypeError, ValueError):
        steel_chance = STEEL_BEAM_CHANCE
    return _generate_random_blueprint(
        steel_chance=steel_chance, cols=cols, rows=rows, wall_algo=wall_algo
    )
