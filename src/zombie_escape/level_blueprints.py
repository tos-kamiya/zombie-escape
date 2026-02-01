# Blueprint generator for randomized layouts.

from collections import deque

from .level_constants import (
    DEFAULT_GRID_WIRE_WALL_LINES,
    DEFAULT_SPARSE_WALL_DENSITY,
    DEFAULT_STEEL_BEAM_CHANCE,
    DEFAULT_WALL_LINES,
)
from .rng import get_rng, seed_rng

EXITS_PER_SIDE = 1  # currently fixed to 1 per side (can be tuned)
WALL_MIN_LEN = 3
WALL_MAX_LEN = 10
SPAWN_MARGIN = 3  # keep spawns away from walls/edges
SPAWN_ZOMBIES = 3

RNG = get_rng()


class MapGenerationError(Exception):
    """Raised when a valid map cannot be generated after several attempts."""


def validate_car_connectivity(grid: list[str]) -> set[tuple[int, int]] | None:
    """Check if the Car can reach at least one exit (4-way BFS).
    Returns the set of reachable tiles if valid, otherwise None.
    """
    rows = len(grid)
    cols = len(grid[0])

    start_pos = None
    passable_tiles = set()
    exit_tiles = set()

    for y in range(rows):
        for x in range(cols):
            ch = grid[y][x]
            if ch == "C":
                start_pos = (x, y)
            if ch not in ("x", "B"):
                passable_tiles.add((x, y))
                if ch == "E":
                    exit_tiles.add((x, y))

    if start_pos is None:
        # If no car candidate, we can't validate car pathing.
        return passable_tiles

    reachable = {start_pos}
    queue = deque([start_pos])
    while queue:
        x, y = queue.popleft()
        for dx, dy in ((0, 1), (0, -1), (1, 0), (-1, 0)):
            nx, ny = x + dx, y + dy
            if (nx, ny) in passable_tiles and (nx, ny) not in reachable:
                reachable.add((nx, ny))
                queue.append((nx, ny))

    # Car must reach at least one exit
    if exit_tiles and not any(e in reachable for e in exit_tiles):
        return None
    return reachable


def validate_humanoid_connectivity(grid: list[str]) -> bool:
    """Check if all floor tiles are reachable by Humans (8-way BFS with jumps)."""
    rows = len(grid)
    cols = len(grid[0])

    start_pos = None
    passable_tiles = set()

    for y in range(rows):
        for x in range(cols):
            ch = grid[y][x]
            if ch == "P":
                start_pos = (x, y)
            if ch not in ("x", "B"):
                passable_tiles.add((x, y))

    if start_pos is None:
        return False

    reachable = {start_pos}
    queue = deque([start_pos])
    while queue:
        x, y = queue.popleft()
        for dx, dy in ((0, 1), (0, -1), (1, 0), (-1, 0), (1, 1), (1, -1), (-1, 1), (-1, -1)):
            nx, ny = x + dx, y + dy
            if (nx, ny) in passable_tiles and (nx, ny) not in reachable:
                reachable.add((nx, ny))
                queue.append((nx, ny))

    return len(passable_tiles) == len(reachable)


def validate_connectivity(grid: list[str]) -> set[tuple[int, int]] | None:
    """Validate both car and humanoid movement conditions.
    Returns car reachable tiles if both pass, otherwise None.
    """
    car_reachable = validate_car_connectivity(grid)
    if car_reachable is None:
        return None
    if not validate_humanoid_connectivity(grid):
        return None
    return car_reachable


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


def _place_walls_default(
    grid: list[list[str]],
    *,
    line_count: int = DEFAULT_WALL_LINES,
    forbidden_cells: set[tuple[int, int]] | None = None,
) -> None:
    cols, rows = len(grid[0]), len(grid)
    rng = RNG.randint
    # Avoid placing walls adjacent to exits and on reserved cells.
    forbidden = _collect_exit_adjacent_cells(grid)
    if forbidden_cells:
        forbidden |= forbidden_cells

    for _ in range(line_count):
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


def _place_walls_empty(
    grid: list[list[str]],
    *,
    forbidden_cells: set[tuple[int, int]] | None = None,
) -> None:
    """Place no internal walls (open floor plan)."""
    _ = (grid, forbidden_cells)


def _place_walls_grid_wire(
    grid: list[list[str]],
    *,
    line_count: int = DEFAULT_GRID_WIRE_WALL_LINES,
    forbidden_cells: set[tuple[int, int]] | None = None,
) -> None:
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
    if forbidden_cells:
        forbidden |= forbidden_cells

    # Temporary grids for independent generation
    # They only track the internal walls ("1").
    grid_v = [["." for _ in range(cols)] for _ in range(rows)]
    grid_h = [["." for _ in range(cols)] for _ in range(rows)]

    lines_per_pass = line_count

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


def _place_walls_sparse_moore(
    grid: list[list[str]],
    *,
    density: float = DEFAULT_SPARSE_WALL_DENSITY,
    forbidden_cells: set[tuple[int, int]] | None = None,
) -> None:
    """Place isolated wall tiles at a low density, avoiding adjacency."""
    cols, rows = len(grid[0]), len(grid)
    forbidden = _collect_exit_adjacent_cells(grid)
    if forbidden_cells:
        forbidden |= forbidden_cells
    for y in range(2, rows - 2):
        for x in range(2, cols - 2):
            if (x, y) in forbidden:
                continue
            if grid[y][x] != ".":
                continue
            if RNG.random() >= density:
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


def _place_walls_sparse_ortho(
    grid: list[list[str]],
    *,
    density: float = DEFAULT_SPARSE_WALL_DENSITY,
    forbidden_cells: set[tuple[int, int]] | None = None,
) -> None:
    """Place isolated wall tiles at a low density, avoiding orthogonal adjacency."""
    cols, rows = len(grid[0]), len(grid)
    forbidden = _collect_exit_adjacent_cells(grid)
    if forbidden_cells:
        forbidden |= forbidden_cells
    for y in range(2, rows - 2):
        for x in range(2, cols - 2):
            if (x, y) in forbidden:
                continue
            if grid[y][x] != ".":
                continue
            if RNG.random() >= density:
                continue
            if grid[y - 1][x] == "1" or grid[y + 1][x] == "1" or grid[y][x - 1] == "1" or grid[y][x + 1] == "1":
                continue
            grid[y][x] = "1"


WALL_ALGORITHMS = {
    "default": _place_walls_default,
    "empty": _place_walls_empty,
    "grid_wire": _place_walls_grid_wire,
    "sparse_moore": _place_walls_sparse_moore,
    "sparse_ortho": _place_walls_sparse_ortho,
}


def _place_steel_beams(
    grid: list[list[str]],
    *,
    chance: float = DEFAULT_STEEL_BEAM_CHANCE,
    forbidden_cells: set[tuple[int, int]] | None = None,
) -> set[tuple[int, int]]:
    """Pick individual cells for steel beams, avoiding exits and their neighbors."""
    cols, rows = len(grid[0]), len(grid)
    forbidden = _collect_exit_adjacent_cells(grid)
    if forbidden_cells:
        forbidden |= forbidden_cells
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


def _place_pitfalls(
    grid: list[list[str]],
    *,
    density: float,
    pitfall_zones: list[tuple[int, int, int, int]] | None = None,
    forbidden_cells: set[tuple[int, int]] | None = None,
) -> None:
    """Replace empty floor tiles with pitfalls based on density."""
    cols, rows = len(grid[0]), len(grid)
    forbidden = _collect_exit_adjacent_cells(grid)
    if forbidden_cells:
        forbidden |= forbidden_cells

    if pitfall_zones:
        for col, row, width, height in pitfall_zones:
            if width <= 0 or height <= 0:
                continue
            start_x = max(0, col)
            start_y = max(0, row)
            end_x = min(cols, col + width)
            end_y = min(rows, row + height)
            for y in range(start_y, end_y):
                for x in range(start_x, end_x):
                    if (x, y) in forbidden:
                        continue
                    if grid[y][x] == ".":
                        grid[y][x] = "x"

    if density <= 0.0:
        return
    for y in range(1, rows - 1):
        for x in range(1, cols - 1):
            if (x, y) in forbidden:
                continue
            if grid[y][x] != ".":
                continue
            if RNG.random() < density:
                grid[y][x] = "x"


def _pick_empty_cell(
    grid: list[list[str]],
    margin: int,
) -> tuple[int, int]:
    cols, rows = len(grid[0]), len(grid)
    attempts = 0
    while attempts < 2000:
        attempts += 1
        x = RNG.randint(margin, cols - margin - 1)
        y = RNG.randint(margin, rows - margin - 1)
        if grid[y][x] == ".":
            return x, y
    # Fallback: scan for any acceptable cell
    for y in range(margin, rows - margin):
        for x in range(margin, cols - margin):
            if grid[y][x] == ".":
                return x, y
    return cols // 2, rows // 2


def _generate_random_blueprint(
    steel_chance: float,
    *,
    cols: int,
    rows: int,
    wall_algo: str = "default",
    pitfall_density: float = 0.0,
    pitfall_zones: list[tuple[int, int, int, int]] | None = None,
) -> dict:
    grid = _init_grid(cols, rows)
    _place_exits(grid, EXITS_PER_SIDE)

    # Spawns: player, car, zombies
    reserved_cells: set[tuple[int, int]] = set()
    px, py = _pick_empty_cell(grid, SPAWN_MARGIN)
    grid[py][px] = "P"
    reserved_cells.add((px, py))
    cx, cy = _pick_empty_cell(grid, SPAWN_MARGIN)
    grid[cy][cx] = "C"
    reserved_cells.add((cx, cy))
    for _ in range(SPAWN_ZOMBIES):
        zx, zy = _pick_empty_cell(grid, SPAWN_MARGIN)
        grid[zy][zx] = "Z"
        reserved_cells.add((zx, zy))

    # Items
    fx, fy = _pick_empty_cell(grid, SPAWN_MARGIN)
    grid[fy][fx] = "f"
    reserved_cells.add((fx, fy))

    for _ in range(2):
        lx, ly = _pick_empty_cell(grid, SPAWN_MARGIN)
        grid[ly][lx] = "l"
        reserved_cells.add((lx, ly))

    for _ in range(2):
        sx, sy = _pick_empty_cell(grid, SPAWN_MARGIN)
        grid[sy][sx] = "s"
        reserved_cells.add((sx, sy))

    # Select and run the wall placement algorithm (after reserving spawns)
    sparse_density = DEFAULT_SPARSE_WALL_DENSITY
    wall_line_count = DEFAULT_WALL_LINES
    original_wall_algo = wall_algo
    if wall_algo == "sparse":
        print("WARNING: 'sparse' is deprecated. Use 'sparse_moore' instead.")
        wall_algo = "sparse_moore"
    elif wall_algo.startswith("sparse."):
        print("WARNING: 'sparse.<int>%' is deprecated. Use 'sparse_moore.<int>%' instead.")
        suffix = wall_algo[len("sparse.") :]
        wall_algo = "sparse_moore"
        if suffix.endswith("%") and suffix[:-1].isdigit():
            percent = int(suffix[:-1])
            if 0 <= percent <= 100:
                sparse_density = percent / 100.0
            else:
                print(
                    "WARNING: Sparse wall density must be 0-100%. "
                    f"Got '{suffix}'. Falling back to default sparse density."
                )
        else:
            print(
                "WARNING: Invalid sparse wall format. Use "
                "'sparse_moore.<int>%' or 'sparse_ortho.<int>%'. "
                f"Got '{original_wall_algo}'. Falling back to default sparse density."
            )
    if wall_algo.startswith("default.") or wall_algo.startswith("grid_wire."):
        base, suffix = wall_algo.split(".", 1)
        base_line_count = DEFAULT_WALL_LINES if base == "default" else DEFAULT_GRID_WIRE_WALL_LINES
        if suffix.endswith("%") and suffix[:-1].isdigit():
            percent = int(suffix[:-1])
            if 0 <= percent <= 200:
                wall_line_count = int(base_line_count * (percent / 100.0))
                wall_algo = base
            else:
                print(
                    "WARNING: Wall line density must be 0-200%. "
                    f"Got '{suffix}'. Falling back to default line count."
                )
                wall_algo = base
        else:
            print(
                "WARNING: Invalid wall line format. Use "
                "'default.<int>%' or 'grid_wire.<int>%'. "
                f"Got '{wall_algo}'. Falling back to default line count."
            )
            wall_algo = base
    if wall_algo.startswith("sparse_moore.") or wall_algo.startswith("sparse_ortho."):
        base, suffix = wall_algo.split(".", 1)
        if suffix.endswith("%") and suffix[:-1].isdigit():
            percent = int(suffix[:-1])
            if 0 <= percent <= 200:
                sparse_density = percent / 100.0
                wall_algo = base
            else:
                print(
                    "WARNING: Sparse wall density must be 0-200%. "
                    f"Got '{suffix}'. Falling back to default sparse density."
                )
                wall_algo = base
        else:
            print(
                "WARNING: Invalid sparse wall format. Use "
                "'sparse_moore.<int>%' or 'sparse_ortho.<int>%'. "
                f"Got '{wall_algo}'. Falling back to default sparse density."
            )
            wall_algo = base

    if wall_algo not in WALL_ALGORITHMS:
        print(f"WARNING: Unknown wall algorithm '{wall_algo}'. Falling back to 'default'.")
        wall_algo = "default"

    # Place pitfalls BEFORE walls so walls avoid them (consistent with spawn reservation)
    _place_pitfalls(
        grid,
        density=pitfall_density,
        pitfall_zones=pitfall_zones,
        forbidden_cells=reserved_cells,
    )

    algo_func = WALL_ALGORITHMS[wall_algo]
    if wall_algo in {"sparse_moore", "sparse_ortho"}:
        algo_func(grid, density=sparse_density, forbidden_cells=reserved_cells)
    elif wall_algo in {"default", "grid_wire"}:
        algo_func(grid, line_count=wall_line_count, forbidden_cells=reserved_cells)
    else:
        algo_func(grid, forbidden_cells=reserved_cells)

    steel_beams = _place_steel_beams(grid, chance=steel_chance, forbidden_cells=reserved_cells)

    blueprint_rows = ["".join(row) for row in grid]
    return {"grid": blueprint_rows, "steel_cells": steel_beams}


def choose_blueprint(
    config: dict,
    *,
    cols: int,
    rows: int,
    wall_algo: str = "default",
    pitfall_density: float = 0.0,
    pitfall_zones: list[tuple[int, int, int, int]] | None = None,
    base_seed: int | None = None,
) -> dict:
    # Currently only random generation; hook for future variants.
    steel_conf = config.get("steel_beams", {})
    try:
        steel_chance = float(steel_conf.get("chance", DEFAULT_STEEL_BEAM_CHANCE))
    except (TypeError, ValueError):
        steel_chance = DEFAULT_STEEL_BEAM_CHANCE

    for attempt in range(20):
        if base_seed is not None:
            seed_rng(base_seed + attempt)

        blueprint = _generate_random_blueprint(
            steel_chance=steel_chance,
            cols=cols,
            rows=rows,
            wall_algo=wall_algo,
            pitfall_density=pitfall_density,
            pitfall_zones=pitfall_zones,
        )

        car_reachable = validate_connectivity(blueprint["grid"])
        if car_reachable is not None:
            blueprint["car_reachable_cells"] = car_reachable
            return blueprint

    raise MapGenerationError("Connectivity validation failed after 20 attempts")
