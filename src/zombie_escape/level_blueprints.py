# Blueprint generator for randomized layouts.

from collections import deque
from dataclasses import dataclass, field

from .level_constants import (
    DEFAULT_GRID_WIRE_WALL_LINES,
    DEFAULT_SPARSE_WALL_DENSITY,
    DEFAULT_STEEL_BEAM_CHANCE,
    DEFAULT_WALL_LINES,
)
from .rng import get_rng
from .entities_constants import MovingFloorDirection

EXITS_PER_SIDE = 1  # currently fixed to 1 per side (can be tuned)
WALL_MIN_LEN = 3
WALL_MAX_LEN = 10
SPAWN_MARGIN = 3  # keep spawns away from walls/edges

RNG = get_rng()


class MapGenerationError(Exception):
    """Raised when a valid map cannot be generated after several attempts."""


@dataclass
class Blueprint:
    grid: list[str]
    steel_cells: set[tuple[int, int]] = field(default_factory=set)
    car_reachable_cells: set[tuple[int, int]] = field(default_factory=set)


def validate_car_connectivity(grid: list[str]) -> set[tuple[int, int]] | None:
    """Check if the Car can reach at least one exit (4-way BFS).
    Returns the set of reachable cells if valid, otherwise None.
    """
    rows = len(grid)
    cols = len(grid[0])

    start_pos = None
    passable_cells = set()
    exit_cells = set()

    for y in range(rows):
        for x in range(cols):
            ch = grid[y][x]
            if ch == "C":
                start_pos = (x, y)
            if ch not in ("x", "B", "O", "^", "v", "<", ">"):
                passable_cells.add((x, y))
                if ch == "E":
                    exit_cells.add((x, y))

    if start_pos is None:
        # If no car candidate, we can't validate car pathing.
        return passable_cells

    reachable = {start_pos}
    queue = deque([start_pos])
    while queue:
        x, y = queue.popleft()
        for dx, dy in ((0, 1), (0, -1), (1, 0), (-1, 0)):
            nx, ny = x + dx, y + dy
            if (nx, ny) in passable_cells and (nx, ny) not in reachable:
                reachable.add((nx, ny))
                queue.append((nx, ny))

    # Car must reach at least one exit
    if exit_cells and not any(e in reachable for e in exit_cells):
        return None
    return reachable


def validate_humanoid_connectivity(grid: list[str]) -> bool:
    """Check if all floor cells are reachable by Humans (8-way BFS with jumps)."""
    rows = len(grid)
    cols = len(grid[0])

    start_pos = None
    passable_cells = set()
    for y in range(rows):
        for x in range(cols):
            ch = grid[y][x]
            if ch == "P":
                start_pos = (x, y)
            if ch not in ("x", "B"):
                passable_cells.add((x, y))

    if start_pos is None:
        return False

    reachable = _humanoid_reachable_cells(grid, start_pos, passable_cells=passable_cells)
    return len(passable_cells) == len(reachable)


def _humanoid_reachable_cells(
    grid: list[str],
    start_pos: tuple[int, int],
    *,
    passable_cells: set[tuple[int, int]] | None = None,
) -> set[tuple[int, int]]:
    rows = len(grid)
    cols = len(grid[0])
    if passable_cells is None:
        passable_cells = {
            (x, y)
            for y in range(rows)
            for x in range(cols)
            if grid[y][x] not in ("x", "B")
        }
    if start_pos not in passable_cells:
        return set()

    floor_blocked_offsets: dict[str, set[tuple[int, int]]] = {
        "^": {(0, 1), (-1, 1), (1, 1)},
        "v": {(0, -1), (-1, -1), (1, -1)},
        "<": {(1, 0), (1, -1), (1, 1)},
        ">": {(-1, 0), (-1, -1), (-1, 1)},
    }
    neighbor_offsets = (
        (0, 1),
        (0, -1),
        (1, 0),
        (-1, 0),
        (1, 1),
        (1, -1),
        (-1, 1),
        (-1, -1),
    )

    reachable = {start_pos}
    queue = deque([start_pos])
    while queue:
        x, y = queue.popleft()
        current_cell = grid[y][x]
        blocked_offsets = floor_blocked_offsets.get(current_cell, set())
        for dx, dy in neighbor_offsets:
            if (dx, dy) in blocked_offsets:
                continue
            nx, ny = x + dx, y + dy
            next_cell = (nx, ny)
            if next_cell in passable_cells and next_cell not in reachable:
                reachable.add(next_cell)
                queue.append(next_cell)
    return reachable


def validate_humanoid_objective_connectivity(
    grid: list[str],
    *,
    requires_fuel: bool,
) -> bool:
    """Check objective pathing for humans with moving-floor constraints.

    - requires_fuel=True: P -> any reachable f -> any C
    - requires_fuel=False: treat P as the fuel start, then P -> any C
    """
    rows = len(grid)
    cols = len(grid[0])
    passable_cells = {
        (x, y)
        for y in range(rows)
        for x in range(cols)
        if grid[y][x] not in ("x", "B")
    }
    player_cells = [
        (x, y) for y in range(rows) for x in range(cols) if grid[y][x] == "P"
    ]
    car_cells = {(x, y) for y in range(rows) for x in range(cols) if grid[y][x] == "C"}
    fuel_cells = {(x, y) for y in range(rows) for x in range(cols) if grid[y][x] == "f"}

    if len(player_cells) != 1 or not car_cells:
        return False
    player_start = player_cells[0]

    from_player = _humanoid_reachable_cells(
        grid,
        player_start,
        passable_cells=passable_cells,
    )
    if requires_fuel:
        if not fuel_cells:
            return False
        fuel_starts = [cell for cell in fuel_cells if cell in from_player]
        if not fuel_starts:
            return False
    else:
        fuel_starts = [player_start]

    for fuel_start in fuel_starts:
        from_fuel = _humanoid_reachable_cells(
            grid,
            fuel_start,
            passable_cells=passable_cells,
        )
        if any(car_cell in from_fuel for car_cell in car_cells):
            return True
    return False


def validate_connectivity(
    grid: list[str],
    *,
    requires_fuel: bool = False,
) -> set[tuple[int, int]] | None:
    """Validate both car and humanoid movement conditions.
    Returns car reachable cells if both pass, otherwise None.
    """
    car_reachable = validate_car_connectivity(grid)
    if car_reachable is None:
        return None
    if not validate_humanoid_objective_connectivity(
        grid,
        requires_fuel=requires_fuel,
    ):
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


def _place_exits(
    grid: list[list[str]],
    exits_per_side: int,
    sides: list[str] | None = None,
) -> None:
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

    if not sides:
        sides = ["top", "bottom", "left", "right"]
    else:
        sides = [side for side in sides if side in ("top", "bottom", "left", "right")]
        if not sides:
            sides = ["top", "bottom", "left", "right"]
    for side in sides:
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
                if grid[y][x + i] == ".":
                    grid[y][x + i] = "1"
        else:
            x = rng(2, cols - 3)
            y = rng(2, rows - 2 - length)
            for i in range(length):
                if (x, y + i) in forbidden:
                    continue
                if grid[y + i][x] == ".":
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

        # Reject if the new segment would connect end-to-end with another vertical segment.
        can_place = True
        if grid_v[y - 1][x] == "1" or grid_v[y + length][x] == "1":
            can_place = False
        else:
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

        # Reject if the new segment would connect end-to-end with another horizontal segment.
        can_place = True
        if grid_h[y][x - 1] == "1" or grid_h[y][x + length] == "1":
            can_place = False
        else:
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
    """Place isolated wall cells at a low density, avoiding adjacency."""
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
    """Place isolated wall cells at a low density, avoiding orthogonal adjacency."""
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
            ):
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


def _place_pitfall_zones(
    grid: list[list[str]],
    *,
    pitfall_zones: list[tuple[int, int, int, int]] | None = None,
    forbidden_cells: set[tuple[int, int]] | None = None,
) -> None:
    """Place zone-defined pitfalls on empty floor cells."""
    cols, rows = len(grid[0]), len(grid)
    forbidden = _collect_exit_adjacent_cells(grid)
    if forbidden_cells:
        forbidden |= forbidden_cells

    if not pitfall_zones:
        return
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


def _place_pitfall_density(
    grid: list[list[str]],
    *,
    density: float,
    forbidden_cells: set[tuple[int, int]] | None = None,
) -> None:
    """Replace empty floor cells with pitfalls based on density."""
    cols, rows = len(grid[0]), len(grid)
    forbidden = _collect_exit_adjacent_cells(grid)
    if forbidden_cells:
        forbidden |= forbidden_cells

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
    *,
    forbidden_cells: set[tuple[int, int]] | None = None,
) -> tuple[int, int]:
    cols, rows = len(grid[0]), len(grid)
    forbidden = forbidden_cells or set()
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


def _expand_zone_cells(
    zones: list[tuple[int, int, int, int]],
    *,
    grid_cols: int,
    grid_rows: int,
) -> set[tuple[int, int]]:
    cells: set[tuple[int, int]] = set()
    for col, row, width, height in zones:
        if width <= 0 or height <= 0:
            continue
        start_x = max(0, col)
        start_y = max(0, row)
        end_x = min(grid_cols, col + width)
        end_y = min(grid_rows, row + height)
        for y in range(start_y, end_y):
            for x in range(start_x, end_x):
                cells.add((x, y))
    return cells


def generate_random_blueprint(
    steel_chance: float,
    *,
    cols: int,
    rows: int,
    exit_sides: list[str] | None = None,
    wall_algo: str = "default",
    pitfall_density: float = 0.0,
    pitfall_zones: list[tuple[int, int, int, int]] | None = None,
    reserved_cells: set[tuple[int, int]] | None = None,
    moving_floor_cells: dict[tuple[int, int], MovingFloorDirection] | None = None,
    fuel_count: int = 1,
    flashlight_count: int = 2,
    shoes_count: int = 2,
) -> Blueprint:
    """Generate a single randomized blueprint grid without connectivity validation."""
    grid = _init_grid(cols, rows)
    _place_exits(grid, EXITS_PER_SIDE, exit_sides)

    # Reserved cells
    reserved_cells = set(reserved_cells or set())
    if moving_floor_cells:
        reserved_cells.update(moving_floor_cells.keys())

    # Place moving floors first so later steps treat them as reserved cells.
    if moving_floor_cells:
        for (mx, my), direction in moving_floor_cells.items():
            if mx < 0 or my < 0 or mx >= cols or my >= rows:
                continue
            if direction == MovingFloorDirection.UP:
                grid[my][mx] = "^"
            elif direction == MovingFloorDirection.DOWN:
                grid[my][mx] = "v"
            elif direction == MovingFloorDirection.LEFT:
                grid[my][mx] = "<"
            elif direction == MovingFloorDirection.RIGHT:
                grid[my][mx] = ">"

    # Place zone-defined pitfalls
    if pitfall_zones:
        _place_pitfall_zones(
            grid,
            pitfall_zones=pitfall_zones,
            forbidden_cells=reserved_cells,
        )
        reserved_cells.update(
            _expand_zone_cells(
                pitfall_zones,
                grid_cols=cols,
                grid_rows=rows,
            )
        )

    # Spawns: player, car
    px, py = _pick_empty_cell(grid, SPAWN_MARGIN, forbidden_cells=reserved_cells)
    grid[py][px] = "P"
    reserved_cells.add((px, py))
    cx, cy = _pick_empty_cell(grid, SPAWN_MARGIN, forbidden_cells=reserved_cells)
    grid[cy][cx] = "C"
    reserved_cells.add((cx, cy))
    # (No zombie candidate cells; initial spawns are handled by gameplay.)

    # Items
    fuel_count = max(0, int(fuel_count))
    flashlight_count = max(0, int(flashlight_count))
    shoes_count = max(0, int(shoes_count))

    for _ in range(fuel_count):
        fx, fy = _pick_empty_cell(grid, SPAWN_MARGIN, forbidden_cells=reserved_cells)
        grid[fy][fx] = "f"
        reserved_cells.add((fx, fy))

    for _ in range(flashlight_count):
        lx, ly = _pick_empty_cell(grid, SPAWN_MARGIN, forbidden_cells=reserved_cells)
        grid[ly][lx] = "l"
        reserved_cells.add((lx, ly))

    for _ in range(shoes_count):
        sx, sy = _pick_empty_cell(grid, SPAWN_MARGIN, forbidden_cells=reserved_cells)
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
        print(
            "WARNING: 'sparse.<int>%' is deprecated. Use 'sparse_moore.<int>%' instead."
        )
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
        base_line_count = (
            DEFAULT_WALL_LINES if base == "default" else DEFAULT_GRID_WIRE_WALL_LINES
        )
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
        print(
            f"WARNING: Unknown wall algorithm '{wall_algo}'. Falling back to 'default'."
        )
        wall_algo = "default"

    # Place density-based pitfalls.
    _place_pitfall_density(
        grid,
        density=pitfall_density,
        forbidden_cells=reserved_cells,
    )

    algo_func = WALL_ALGORITHMS[wall_algo]
    if wall_algo in {"sparse_moore", "sparse_ortho"}:
        algo_func(grid, density=sparse_density, forbidden_cells=reserved_cells)
    elif wall_algo in {"default", "grid_wire"}:
        algo_func(grid, line_count=wall_line_count, forbidden_cells=reserved_cells)
    else:
        algo_func(grid, forbidden_cells=reserved_cells)

    steel_beams = _place_steel_beams(
        grid, chance=steel_chance, forbidden_cells=reserved_cells
    )

    blueprint_rows = ["".join(row) for row in grid]
    return Blueprint(grid=blueprint_rows, steel_cells=steel_beams)
