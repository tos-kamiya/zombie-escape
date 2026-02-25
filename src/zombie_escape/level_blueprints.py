# Blueprint generator for randomized layouts.

from collections import deque
from dataclasses import dataclass, field

from .level_constants import (
    DEFAULT_CORRIDOR_BREAK_RATIO,
    DEFAULT_GRID_WIRE_WALL_LINES,
    DEFAULT_SPARSE_WALL_DENSITY,
    DEFAULT_STEEL_BEAM_CHANCE,
    DEFAULT_WALL_LINES,
)
from .models import FuelMode
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
            # Car can drive through moving-floor cells; only solid blockers are excluded.
            if ch not in ("x", "B", "R", "O"):
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
            if ch not in ("x", "B", "R", "F"):
                passable_cells.add((x, y))

    if start_pos is None:
        return False

    reachable = _humanoid_reachable_cells(
        grid, start_pos, passable_cells=passable_cells
    )
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
            if grid[y][x] not in ("x", "B", "R", "F")
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
    fuel_mode: FuelMode = FuelMode.START_FULL,
    require_player_exit_path: bool = False,
    require_car_spawn: bool = True,
) -> bool:
    """Check objective pathing for humans with moving-floor constraints.

    - fuel_mode=1 (FUEL_CAN): P -> any reachable f -> any C
    - fuel_mode=0 (REFUEL_CHAIN): P -> reachable e -> reachable f -> any C
    - fuel_mode=2 (START_FULL): treat P as the fuel start, then P -> any C
    - require_player_exit_path=True: additionally require P -> any E
    """
    rows = len(grid)
    cols = len(grid[0])
    passable_cells = {
        (x, y)
        for y in range(rows)
        for x in range(cols)
        if grid[y][x] not in ("x", "B", "R", "F")
    }
    player_cells = [
        (x, y) for y in range(rows) for x in range(cols) if grid[y][x] == "P"
    ]
    car_cells = {(x, y) for y in range(rows) for x in range(cols) if grid[y][x] == "C"}
    empty_can_cells = {
        (x, y) for y in range(rows) for x in range(cols) if grid[y][x] == "e"
    }
    fuel_cells = {(x, y) for y in range(rows) for x in range(cols) if grid[y][x] == "f"}
    exit_cells = {(x, y) for y in range(rows) for x in range(cols) if grid[y][x] == "E"}

    if len(player_cells) != 1:
        return False
    if require_car_spawn and not car_cells:
        return False
    player_start = player_cells[0]

    from_player = _humanoid_reachable_cells(
        grid,
        player_start,
        passable_cells=passable_cells,
    )
    if require_player_exit_path and (
        not exit_cells or not any(exit_cell in from_player for exit_cell in exit_cells)
    ):
        return False
    if not require_car_spawn:
        # Car-less stages only require on-foot objective reachability.
        return fuel_mode == FuelMode.START_FULL
    if fuel_mode == FuelMode.REFUEL_CHAIN:
        if not empty_can_cells or not fuel_cells:
            return False
        empty_candidates = [cell for cell in empty_can_cells if cell in from_player]
        if not empty_candidates:
            return False
        for empty_cell in empty_candidates:
            from_empty = _humanoid_reachable_cells(
                grid,
                empty_cell,
                passable_cells=passable_cells,
            )
            station_candidates = [cell for cell in fuel_cells if cell in from_empty]
            if not station_candidates:
                continue
            for station_cell in station_candidates:
                from_station = _humanoid_reachable_cells(
                    grid,
                    station_cell,
                    passable_cells=passable_cells,
                )
                if any(car_cell in from_station for car_cell in car_cells):
                    return True
        return False
    if fuel_mode == FuelMode.FUEL_CAN:
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
    fuel_mode: FuelMode = FuelMode.START_FULL,
    require_player_exit_path: bool = False,
    require_car_spawn: bool = True,
) -> set[tuple[int, int]] | None:
    """Validate both car and humanoid movement conditions.
    Returns car reachable cells if both pass, otherwise None.
    """
    if require_car_spawn:
        car_reachable = validate_car_connectivity(grid)
        if car_reachable is None:
            return None
    else:
        car_reachable = set()
    if not validate_humanoid_objective_connectivity(
        grid,
        fuel_mode=fuel_mode,
        require_player_exit_path=require_player_exit_path,
        require_car_spawn=require_car_spawn,
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

    def _axis_pick_range(min_inclusive: int, max_inclusive: int) -> tuple[int, int]:
        """Prefer positions one cell away from side-ends; fallback for small maps."""
        preferred_min = min_inclusive + 1
        preferred_max = max_inclusive - 1
        if preferred_min <= preferred_max:
            return preferred_min, preferred_max
        return min_inclusive, max_inclusive

    def _pick_pos(side: str) -> tuple[int, int]:
        if side in ("top", "bottom"):
            start_x, end_x = _axis_pick_range(2, cols - 3)
            x = rng(start_x, end_x)
            y = 1 if side == "top" else rows - 2
        else:
            start_y, end_y = _axis_pick_range(2, rows - 3)
            y = rng(start_y, end_y)
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


def _place_corner_outer_walls_for_closed_sides(
    grid: list[list[str]],
    *,
    exit_sides: list[str] | None,
) -> None:
    """Add corner outer walls when a side has no exits configured."""
    cols, rows = len(grid[0]), len(grid)
    valid_sides = {"top", "bottom", "left", "right"}
    if not exit_sides:
        open_sides = valid_sides
    else:
        open_sides = {side for side in exit_sides if side in valid_sides}
        if not open_sides:
            open_sides = valid_sides
    closed_sides = valid_sides - open_sides
    if not closed_sides:
        return

    corner_cells: set[tuple[int, int]] = set()
    if "top" in closed_sides:
        corner_cells.add((0, 0))
        corner_cells.add((cols - 1, 0))
    if "bottom" in closed_sides:
        corner_cells.add((0, rows - 1))
        corner_cells.add((cols - 1, rows - 1))
    if "left" in closed_sides:
        corner_cells.add((0, 0))
        corner_cells.add((0, rows - 1))
    if "right" in closed_sides:
        corner_cells.add((cols - 1, 0))
        corner_cells.add((cols - 1, rows - 1))

    for x, y in corner_cells:
        grid[y][x] = "B"


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


def _place_walls_corridor(
    grid: list[list[str]],
    *,
    break_ratio: float = DEFAULT_CORRIDOR_BREAK_RATIO,
    forbidden_cells: set[tuple[int, int]] | None = None,
) -> None:
    """Generate a maze-like corridor layout, then open extra loops."""
    cols, rows = len(grid[0]), len(grid)
    forbidden = _collect_exit_adjacent_cells(grid)
    if forbidden_cells:
        forbidden |= forbidden_cells

    interior_min_x = 2
    interior_max_x = cols - 3
    interior_min_y = 2
    interior_max_y = rows - 3

    if interior_min_x > interior_max_x or interior_min_y > interior_max_y:
        return

    def _can_carve(x: int, y: int) -> bool:
        if x < interior_min_x or x > interior_max_x:
            return False
        if y < interior_min_y or y > interior_max_y:
            return False
        if (x, y) in forbidden:
            return False
        return grid[y][x] in {".", "1"}

    def _set_floor(x: int, y: int) -> None:
        if grid[y][x] == "1":
            grid[y][x] = "."

    # Fill non-reserved interior floors with walls first.
    for y in range(interior_min_y, interior_max_y + 1):
        for x in range(interior_min_x, interior_max_x + 1):
            if (x, y) in forbidden:
                continue
            if grid[y][x] == ".":
                grid[y][x] = "1"

    nodes = [
        (x, y)
        for y in range(interior_min_y, interior_max_y + 1)
        for x in range(interior_min_x, interior_max_x + 1)
        if (x - interior_min_x) % 2 == 0
        and (y - interior_min_y) % 2 == 0
        and _can_carve(x, y)
    ]
    if not nodes:
        return

    unvisited = set(nodes)
    while unvisited:
        start = RNG.choice(tuple(unvisited))
        stack = [start]
        unvisited.remove(start)
        _set_floor(*start)

        while stack:
            x, y = stack[-1]
            directions = [(2, 0), (-2, 0), (0, 2), (0, -2)]
            RNG.shuffle(directions)
            moved = False
            for dx, dy in directions:
                nx = x + dx
                ny = y + dy
                if (nx, ny) not in unvisited:
                    continue
                if not _can_carve(nx, ny):
                    continue
                wx = x + dx // 2
                wy = y + dy // 2
                if not _can_carve(wx, wy):
                    continue
                _set_floor(wx, wy)
                _set_floor(nx, ny)
                unvisited.remove((nx, ny))
                stack.append((nx, ny))
                moved = True
                break
            if not moved:
                stack.pop()

    # Add a limited number of wall breaks to create loops.
    clamped_break_ratio = max(0.0, min(0.2, break_ratio))
    for y in range(interior_min_y, interior_max_y + 1):
        for x in range(interior_min_x, interior_max_x + 1):
            if grid[y][x] != "1" or (x, y) in forbidden:
                continue
            if RNG.random() >= clamped_break_ratio:
                continue
            has_horizontal = _can_carve(x - 1, y) and _can_carve(x + 1, y)
            has_vertical = _can_carve(x, y - 1) and _can_carve(x, y + 1)
            if has_horizontal or has_vertical:
                grid[y][x] = "."

    # Keep all reserved cells passable.
    if forbidden_cells:
        for cell_x, cell_y in forbidden_cells:
            if (
                interior_min_x <= cell_x <= interior_max_x
                and interior_min_y <= cell_y <= interior_max_y
                and grid[cell_y][cell_x] == "1"
            ):
                grid[cell_y][cell_x] = "."


WALL_ALGORITHMS = {
    "default": _place_walls_default,
    "empty": _place_walls_empty,
    "grid_wire": _place_walls_grid_wire,
    "sparse_moore": _place_walls_sparse_moore,
    "sparse_ortho": _place_walls_sparse_ortho,
    "corridor": _place_walls_corridor,
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
    candidates = [
        (x, y)
        for y in range(1, rows - 1)
        for x in range(1, cols - 1)
        if (x, y) not in forbidden and grid[y][x] == "."
    ]
    selected = _select_cells_by_ratio(
        candidates,
        density,
        feature_name="pitfall",
    )
    for x, y in selected:
        grid[y][x] = "x"


def _place_spiky_plant_zones(
    grid: list[list[str]],
    *,
    spiky_plant_zones: list[tuple[int, int, int, int]] | None = None,
    forbidden_cells: set[tuple[int, int]] | None = None,
) -> None:
    """Place zone-defined spiky plants on empty floor cells."""
    cols, rows = len(grid[0]), len(grid)
    forbidden = _collect_exit_adjacent_cells(grid)
    if forbidden_cells:
        forbidden |= forbidden_cells

    if not spiky_plant_zones:
        return
    for col, row, width, height in spiky_plant_zones:
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
                    grid[y][x] = "h"


def _place_spiky_plant_density(
    grid: list[list[str]],
    *,
    density: float,
    forbidden_cells: set[tuple[int, int]] | None = None,
) -> None:
    """Replace empty floor cells with spiky plants based on density."""
    cols, rows = len(grid[0]), len(grid)
    forbidden = _collect_exit_adjacent_cells(grid)
    if forbidden_cells:
        forbidden |= forbidden_cells

    if density <= 0.0:
        return
    candidates = [
        (x, y)
        for y in range(1, rows - 1)
        for x in range(1, cols - 1)
        if (x, y) not in forbidden and grid[y][x] == "."
    ]
    selected = _select_cells_by_ratio(
        candidates,
        density,
        feature_name="spiky_plant",
    )
    for x, y in selected:
        grid[y][x] = "h"


def _place_puddle_zones(
    grid: list[list[str]],
    *,
    puddle_zones: list[tuple[int, int, int, int]] | None = None,
    forbidden_cells: set[tuple[int, int]] | None = None,
) -> None:
    """Place zone-defined puddles on empty floor cells."""
    cols, rows = len(grid[0]), len(grid)
    forbidden = _collect_exit_adjacent_cells(grid)
    if forbidden_cells:
        forbidden |= forbidden_cells

    if not puddle_zones:
        return
    for col, row, width, height in puddle_zones:
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
                    grid[y][x] = "w"


def _place_puddle_density(
    grid: list[list[str]],
    *,
    density: float,
    forbidden_cells: set[tuple[int, int]] | None = None,
) -> None:
    """Replace empty floor cells with puddles based on density."""
    cols, rows = len(grid[0]), len(grid)
    forbidden = _collect_exit_adjacent_cells(grid)
    if forbidden_cells:
        forbidden |= forbidden_cells

    if density <= 0.0:
        return
    candidates = [
        (x, y)
        for y in range(1, rows - 1)
        for x in range(1, cols - 1)
        if (x, y) not in forbidden and grid[y][x] == "."
    ]
    selected = _select_cells_by_ratio(
        candidates,
        density,
        feature_name="puddle",
    )
    for x, y in selected:
        grid[y][x] = "w"


def _place_fire_floor_zones(
    grid: list[list[str]],
    *,
    fire_floor_zones: list[tuple[int, int, int, int]] | None = None,
    forbidden_cells: set[tuple[int, int]] | None = None,
) -> None:
    """Place zone-defined fire-floor cells on empty floor cells."""
    cols, rows = len(grid[0]), len(grid)
    forbidden = _collect_exit_adjacent_cells(grid)
    if forbidden_cells:
        forbidden |= forbidden_cells

    if not fire_floor_zones:
        return
    for col, row, width, height in fire_floor_zones:
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
                    grid[y][x] = "F"


def _place_fire_floor_density(
    grid: list[list[str]],
    *,
    density: float,
    forbidden_cells: set[tuple[int, int]] | None = None,
) -> None:
    """Replace empty floor cells with fire floors based on density."""
    cols, rows = len(grid[0]), len(grid)
    forbidden = _collect_exit_adjacent_cells(grid)
    if forbidden_cells:
        forbidden |= forbidden_cells

    if density <= 0.0:
        return
    candidates = [
        (x, y)
        for y in range(1, rows - 1)
        for x in range(1, cols - 1)
        if (x, y) not in forbidden and grid[y][x] == "."
    ]
    selected = _select_cells_by_ratio(
        candidates,
        density,
        feature_name="fire floor",
    )
    for x, y in selected:
        grid[y][x] = "F"


def _place_metal_floor_zones(
    grid: list[list[str]],
    *,
    metal_floor_zones: list[tuple[int, int, int, int]] | None = None,
    forbidden_cells: set[tuple[int, int]] | None = None,
) -> None:
    """Place zone-defined metal-floor cells on empty floor cells."""
    cols, rows = len(grid[0]), len(grid)
    forbidden = _collect_exit_adjacent_cells(grid)
    if forbidden_cells:
        forbidden |= forbidden_cells

    if not metal_floor_zones:
        return
    for col, row, width, height in metal_floor_zones:
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
                    grid[y][x] = "m"


def _place_metal_floor_density(
    grid: list[list[str]],
    *,
    density: float,
    forbidden_cells: set[tuple[int, int]] | None = None,
) -> None:
    """Replace empty floor cells with metal floors based on density."""
    cols, rows = len(grid[0]), len(grid)
    forbidden = _collect_exit_adjacent_cells(grid)
    if forbidden_cells:
        forbidden |= forbidden_cells

    if density <= 0.0:
        return
    candidates = [
        (x, y)
        for y in range(1, rows - 1)
        for x in range(1, cols - 1)
        if (x, y) not in forbidden and grid[y][x] == "."
    ]
    selected = _select_cells_by_ratio(
        candidates,
        density,
        feature_name="metal floor",
    )
    for x, y in selected:
        grid[y][x] = "m"


def _place_metal_adjacent_to_fire_floor(grid: list[list[str]]) -> None:
    """Convert floor cells adjacent to fire floors into metal floor cells."""
    cols, rows = len(grid[0]), len(grid)
    fire_cells = [
        (x, y)
        for y in range(rows)
        for x in range(cols)
        if grid[y][x] == "F"
    ]
    if not fire_cells:
        return
    for x, y in fire_cells:
        for dx, dy in ((0, 1), (0, -1), (1, 0), (-1, 0)):
            nx, ny = x + dx, y + dy
            if nx < 0 or ny < 0 or nx >= cols or ny >= rows:
                continue
            if grid[ny][nx] == ".":
                grid[ny][nx] = "m"


def _place_reinforced_wall_zones(
    grid: list[list[str]],
    *,
    reinforced_wall_zones: list[tuple[int, int, int, int]] | None = None,
    forbidden_cells: set[tuple[int, int]] | None = None,
) -> None:
    """Place zone-defined reinforced walls on empty floor cells."""
    cols, rows = len(grid[0]), len(grid)
    forbidden = _collect_exit_adjacent_cells(grid)
    if forbidden_cells:
        forbidden |= forbidden_cells

    if not reinforced_wall_zones:
        return
    for col, row, width, height in reinforced_wall_zones:
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
                    grid[y][x] = "R"


def _place_reinforced_wall_density(
    grid: list[list[str]],
    *,
    density: float,
    forbidden_cells: set[tuple[int, int]] | None = None,
) -> None:
    """Replace empty floor cells with reinforced walls based on density."""
    cols, rows = len(grid[0]), len(grid)
    forbidden = _collect_exit_adjacent_cells(grid)
    if forbidden_cells:
        forbidden |= forbidden_cells

    if density <= 0.0:
        return
    candidates = [
        (x, y)
        for y in range(1, rows - 1)
        for x in range(1, cols - 1)
        if (x, y) not in forbidden and grid[y][x] == "."
    ]
    selected = _select_cells_by_ratio(
        candidates,
        density,
        feature_name="reinforced wall",
    )
    for x, y in selected:
        grid[y][x] = "R"


def _select_cells_by_ratio(
    candidates: list[tuple[int, int]],
    ratio: float,
    *,
    feature_name: str,
) -> list[tuple[int, int]]:
    if ratio <= 0.0:
        return []
    if not candidates:
        raise MapGenerationError(
            f"{feature_name} ratio is positive but no candidate cells are available"
        )
    target_count = int(round(len(candidates) * ratio))
    if target_count == 0:
        target_count = 1
    target_count = max(0, min(len(candidates), target_count))
    if target_count == 0:
        return []
    shuffled = list(candidates)
    RNG.shuffle(shuffled)
    return shuffled[:target_count]


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
    fire_floor_density: float = 0.0,
    fire_floor_zones: list[tuple[int, int, int, int]] | None = None,
    metal_floor_density: float = 0.0,
    metal_floor_zones: list[tuple[int, int, int, int]] | None = None,
    reserved_cells: set[tuple[int, int]] | None = None,
    moving_floor_cells: dict[tuple[int, int], MovingFloorDirection] | None = None,
    fuel_count: int = 1,
    empty_fuel_can_count: int = 0,
    fuel_station_count: int = 0,
    flashlight_count: int = 2,
    shoes_count: int = 2,
    spiky_plant_density: float = 0.0,
    spiky_plant_zones: list[tuple[int, int, int, int]] | None = None,
    puddle_density: float = 0.0,
    puddle_zones: list[tuple[int, int, int, int]] | None = None,
    reinforced_wall_density: float = 0.0,
    reinforced_wall_zones: list[tuple[int, int, int, int]] | None = None,
    fall_spawn_zones: list[tuple[int, int, int, int]] | None = None,
) -> Blueprint:
    """Generate a single randomized blueprint grid without connectivity validation."""
    _ = fall_spawn_zones
    grid = _init_grid(cols, rows)
    _place_exits(grid, EXITS_PER_SIDE, exit_sides)
    _place_corner_outer_walls_for_closed_sides(grid, exit_sides=exit_sides)

    # Reserved cells (player, car, items, exits)
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

    # Place zone-defined metal floors first to keep them from later hazard replacement.
    if metal_floor_zones:
        _place_metal_floor_zones(
            grid,
            metal_floor_zones=metal_floor_zones,
            forbidden_cells=reserved_cells,
        )
        reserved_cells.update(
            _expand_zone_cells(
                metal_floor_zones,
                grid_cols=cols,
                grid_rows=rows,
            )
        )

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

    # Place zone-defined puddles
    if puddle_zones:
        _place_puddle_zones(
            grid,
            puddle_zones=puddle_zones,
            forbidden_cells=reserved_cells,
        )
        reserved_cells.update(
            _expand_zone_cells(
                puddle_zones,
                grid_cols=cols,
                grid_rows=rows,
            )
        )
    # Place zone-defined fire floors.
    if fire_floor_zones:
        _place_fire_floor_zones(
            grid,
            fire_floor_zones=fire_floor_zones,
            forbidden_cells=reserved_cells,
        )
        reserved_cells.update(
            _expand_zone_cells(
                fire_floor_zones,
                grid_cols=cols,
                grid_rows=rows,
            )
        )

    # Place zone-defined spiky plants.
    if spiky_plant_zones:
        _place_spiky_plant_zones(
            grid,
            spiky_plant_zones=spiky_plant_zones,
            forbidden_cells=reserved_cells,
        )
        reserved_cells.update(
            _expand_zone_cells(
                spiky_plant_zones,
                grid_cols=cols,
                grid_rows=rows,
            )
        )

    # Place zone-defined reinforced walls.
    if reinforced_wall_zones:
        _place_reinforced_wall_zones(
            grid,
            reinforced_wall_zones=reinforced_wall_zones,
            forbidden_cells=reserved_cells,
        )
        reserved_cells.update(
            _expand_zone_cells(
                reinforced_wall_zones,
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
    empty_fuel_can_count = max(0, int(empty_fuel_can_count))
    fuel_station_count = max(0, int(fuel_station_count))
    flashlight_count = max(0, int(flashlight_count))
    shoes_count = max(0, int(shoes_count))

    for _ in range(empty_fuel_can_count):
        ex, ey = _pick_empty_cell(grid, SPAWN_MARGIN, forbidden_cells=reserved_cells)
        grid[ey][ex] = "e"
        reserved_cells.add((ex, ey))

    for _ in range(fuel_count):
        fx, fy = _pick_empty_cell(grid, SPAWN_MARGIN, forbidden_cells=reserved_cells)
        grid[fy][fx] = "f"
        reserved_cells.add((fx, fy))

    for _ in range(fuel_station_count):
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
    corridor_break_ratio = DEFAULT_CORRIDOR_BREAK_RATIO
    original_wall_algo = wall_algo
    if wall_algo == "normal":
        wall_algo = "default"
    elif wall_algo.startswith("normal."):
        wall_algo = f"default.{wall_algo[len('normal.') :]}"
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
    if wall_algo.startswith("corridor."):
        _, suffix = wall_algo.split(".", 1)
        if suffix.endswith("%") and suffix[:-1].isdigit():
            percent = int(suffix[:-1])
            if 0 <= percent <= 200:
                corridor_break_ratio = max(
                    0.0,
                    min(
                        0.2,
                        percent * 0.003,
                    ),
                )
                wall_algo = "corridor"
            else:
                print(
                    "WARNING: Corridor break ratio must be 0-200%. "
                    f"Got '{suffix}'. Falling back to default corridor break ratio."
                )
                wall_algo = "corridor"
        else:
            print(
                "WARNING: Invalid corridor format. Use 'corridor.<int>%'. "
                f"Got '{wall_algo}'. Falling back to default corridor break ratio."
            )
            wall_algo = "corridor"

    if wall_algo not in WALL_ALGORITHMS:
        print(
            f"WARNING: Unknown wall algorithm '{wall_algo}'. Falling back to 'default'."
        )
        wall_algo = "default"

    # Place density-based pitfalls.
    _place_metal_floor_density(
        grid,
        density=metal_floor_density,
        forbidden_cells=reserved_cells,
    )

    # Place density-based pitfalls.
    _place_pitfall_density(
        grid,
        density=pitfall_density,
        forbidden_cells=reserved_cells,
    )

    # Place density-based puddles.
    _place_puddle_density(
        grid,
        density=puddle_density,
        forbidden_cells=reserved_cells,
    )
    # Place density-based fire floors.
    _place_fire_floor_density(
        grid,
        density=fire_floor_density,
        forbidden_cells=reserved_cells,
    )

    # Place density-based spiky plants.
    _place_spiky_plant_density(
        grid,
        density=spiky_plant_density,
        forbidden_cells=reserved_cells,
    )
    # Place density-based reinforced walls.
    _place_reinforced_wall_density(
        grid,
        density=reinforced_wall_density,
        forbidden_cells=reserved_cells,
    )

    algo_func = WALL_ALGORITHMS[wall_algo]
    if wall_algo in {"sparse_moore", "sparse_ortho"}:
        algo_func(grid, density=sparse_density, forbidden_cells=reserved_cells)
    elif wall_algo in {"default", "grid_wire"}:
        algo_func(grid, line_count=wall_line_count, forbidden_cells=reserved_cells)
    elif wall_algo == "corridor":
        algo_func(
            grid,
            break_ratio=corridor_break_ratio,
            forbidden_cells=reserved_cells,
        )
    else:
        algo_func(grid, forbidden_cells=reserved_cells)

    _place_metal_adjacent_to_fire_floor(grid)

    steel_beams = _place_steel_beams(
        grid, chance=steel_chance, forbidden_cells=reserved_cells
    )

    blueprint_rows = ["".join(row) for row in grid]
    return Blueprint(grid=blueprint_rows, steel_cells=steel_beams)
