from __future__ import annotations

import math
from typing import Iterable, TYPE_CHECKING

if TYPE_CHECKING:
    from .entities import Wall


WallIndex = dict[tuple[int, int], list["Wall"]]


def build_wall_index(walls: Iterable["Wall"], *, cell_size: int) -> WallIndex:
    index: WallIndex = {}
    if cell_size <= 0:
        return index
    for wall in walls:
        cell_x = int(wall.rect.centerx // cell_size)
        cell_y = int(wall.rect.centery // cell_size)
        index.setdefault((cell_x, cell_y), []).append(wall)
    return index


def _infer_grid_size_from_index(wall_index: WallIndex) -> tuple[int | None, int | None]:
    if not wall_index:
        return None, None
    max_col = max(cell[0] for cell in wall_index)
    max_row = max(cell[1] for cell in wall_index)
    return max_col + 1, max_row + 1


def walls_for_radius(
    wall_index: WallIndex,
    center: tuple[float, float],
    radius: float,
    *,
    cell_size: int,
    grid_cols: int | None = None,
    grid_rows: int | None = None,
) -> list["Wall"]:
    if grid_cols is None or grid_rows is None:
        grid_cols, grid_rows = _infer_grid_size_from_index(wall_index)
    if grid_cols is None or grid_rows is None:
        return []
    search_radius = radius + cell_size
    min_x = max(0, int((center[0] - search_radius) // cell_size))
    max_x = min(grid_cols - 1, int((center[0] + search_radius) // cell_size))
    min_y = max(0, int((center[1] - search_radius) // cell_size))
    max_y = min(grid_rows - 1, int((center[1] + search_radius) // cell_size))
    candidates: list[Wall] = []
    for cy in range(min_y, max_y + 1):
        for cx in range(min_x, max_x + 1):
            candidates.extend(wall_index.get((cx, cy), []))
    return candidates


def apply_tile_edge_nudge(
    x: float,
    y: float,
    dx: float,
    dy: float,
    *,
    cell_size: int,
    wall_cells: set[tuple[int, int]] | None,
    bevel_corners: dict[tuple[int, int], tuple[bool, bool, bool, bool]] | None = None,
    grid_cols: int,
    grid_rows: int,
    strength: float = 0.03,
    edge_margin_ratio: float = 0.15,
    min_margin: float = 2.0,
) -> tuple[float, float]:
    if dx == 0 and dy == 0:
        return dx, dy
    if cell_size <= 0 or not wall_cells:
        return dx, dy
    cell_x = int(x // cell_size)
    cell_y = int(y // cell_size)
    if cell_x < 0 or cell_y < 0 or cell_x >= grid_cols or cell_y >= grid_rows:
        return dx, dy
    speed = math.hypot(dx, dy)
    if speed <= 0:
        return dx, dy

    edge_margin = max(min_margin, cell_size * edge_margin_ratio)
    left_dist = x - (cell_x * cell_size)
    right_dist = ((cell_x + 1) * cell_size) - x
    top_dist = y - (cell_y * cell_size)
    bottom_dist = ((cell_y + 1) * cell_size) - y

    def apply_push(dist: float, direction: float) -> float:
        if dist >= edge_margin:
            return 0.0
        ratio = (edge_margin - dist) / edge_margin
        return ratio * speed * strength * direction

    if (cell_x - 1, cell_y) in wall_cells:
        dx += apply_push(left_dist, 1.0)
    if (cell_x + 1, cell_y) in wall_cells:
        dx += apply_push(right_dist, -1.0)
    if (cell_x, cell_y - 1) in wall_cells:
        dy += apply_push(top_dist, 1.0)
    if (cell_x, cell_y + 1) in wall_cells:
        dy += apply_push(bottom_dist, -1.0)

    def apply_corner_push(dist_a: float, dist_b: float, boost: float = 1.0) -> float:
        if dist_a >= edge_margin or dist_b >= edge_margin:
            return 0.0
        ratio = (edge_margin - min(dist_a, dist_b)) / edge_margin
        return ratio * speed * strength * boost

    if bevel_corners:
        boosted = 1.25
        corner_wall = bevel_corners.get((cell_x - 1, cell_y - 1))
        if corner_wall and corner_wall[2]:
            push = apply_corner_push(left_dist, top_dist, boosted)
            dx += push
            dy += push
        corner_wall = bevel_corners.get((cell_x + 1, cell_y - 1))
        if corner_wall and corner_wall[3]:
            push = apply_corner_push(right_dist, top_dist, boosted)
            dx -= push
            dy += push
        corner_wall = bevel_corners.get((cell_x + 1, cell_y + 1))
        if corner_wall and corner_wall[0]:
            push = apply_corner_push(right_dist, bottom_dist, boosted)
            dx -= push
            dy -= push
        corner_wall = bevel_corners.get((cell_x - 1, cell_y + 1))
        if corner_wall and corner_wall[1]:
            push = apply_corner_push(left_dist, bottom_dist, boosted)
            dx += push
            dy -= push

    return dx, dy
