from __future__ import annotations

import pygame

from ..entities import Camera, Player, random_position_outside_building
from ..rng import get_rng
from ..screen_constants import SCREEN_HEIGHT, SCREEN_WIDTH

LOGICAL_SCREEN_RECT = pygame.Rect(0, 0, SCREEN_WIDTH, SCREEN_HEIGHT)
RNG = get_rng()

__all__ = [
    "LOGICAL_SCREEN_RECT",
    "rect_visible_on_screen",
    "find_interior_spawn_positions",
    "find_nearby_offscreen_spawn_position",
    "find_exterior_spawn_position",
]


def rect_visible_on_screen(camera: Camera | None, rect: pygame.Rect) -> bool:
    if camera is None:
        return False
    return camera.apply_rect(rect).colliderect(LOGICAL_SCREEN_RECT)


def _scatter_positions_on_walkable(
    walkable_cells: list[pygame.Rect],
    spawn_rate: float,
    *,
    jitter_ratio: float = 0.35,
) -> list[tuple[int, int]]:
    positions: list[tuple[int, int]] = []
    if not walkable_cells or spawn_rate <= 0:
        return positions

    clamped_rate = max(0.0, min(1.0, spawn_rate))
    for cell in walkable_cells:
        if RNG.random() >= clamped_rate:
            continue
        jitter_x = RNG.uniform(-cell.width * jitter_ratio, cell.width * jitter_ratio)
        jitter_y = RNG.uniform(-cell.height * jitter_ratio, cell.height * jitter_ratio)
        positions.append((int(cell.centerx + jitter_x), int(cell.centery + jitter_y)))
    return positions


def find_interior_spawn_positions(
    walkable_cells: list[pygame.Rect],
    spawn_rate: float,
    *,
    player: Player | None = None,
    min_player_dist: float | None = None,
) -> list[tuple[int, int]]:
    positions = _scatter_positions_on_walkable(
        walkable_cells,
        spawn_rate,
        jitter_ratio=0.35,
    )
    if not positions and spawn_rate > 0:
        positions = _scatter_positions_on_walkable(
            walkable_cells,
            spawn_rate * 1.5,
            jitter_ratio=0.35,
        )
    if not positions:
        return []
    if player is None or min_player_dist is None or min_player_dist <= 0:
        return positions
    min_player_dist_sq = min_player_dist * min_player_dist
    filtered: list[tuple[int, int]] = []
    for pos in positions:
        dx = pos[0] - player.x
        dy = pos[1] - player.y
        if dx * dx + dy * dy < min_player_dist_sq:
            continue
        filtered.append(pos)
    return filtered


def find_nearby_offscreen_spawn_position(
    walkable_cells: list[pygame.Rect],
    *,
    player: Player | None = None,
    camera: Camera | None = None,
    min_player_dist: float | None = None,
    max_player_dist: float | None = None,
    attempts: int = 18,
) -> tuple[int, int]:
    if not walkable_cells:
        raise ValueError("walkable_cells must not be empty")
    view_rect = None
    if camera is not None:
        view_rect = pygame.Rect(
            -camera.camera.x,
            -camera.camera.y,
            SCREEN_WIDTH,
            SCREEN_HEIGHT,
        )
        view_rect.inflate_ip(SCREEN_WIDTH, SCREEN_HEIGHT)
    min_distance_sq = (
        None if min_player_dist is None else min_player_dist * min_player_dist
    )
    max_distance_sq = (
        None if max_player_dist is None else max_player_dist * max_player_dist
    )
    for _ in range(max(1, attempts)):
        cell = RNG.choice(walkable_cells)
        jitter_x = RNG.uniform(-cell.width * 0.35, cell.width * 0.35)
        jitter_y = RNG.uniform(-cell.height * 0.35, cell.height * 0.35)
        candidate = (int(cell.centerx + jitter_x), int(cell.centery + jitter_y))
        if player is not None and (
            min_distance_sq is not None or max_distance_sq is not None
        ):
            dx = candidate[0] - player.x
            dy = candidate[1] - player.y
            dist_sq = dx * dx + dy * dy
            if min_distance_sq is not None and dist_sq < min_distance_sq:
                continue
            if max_distance_sq is not None and dist_sq > max_distance_sq:
                continue
        if view_rect is not None and view_rect.collidepoint(candidate):
            continue
        return candidate
    if player is not None and (min_distance_sq is not None or max_distance_sq is not None):
        for _ in range(20):
            cell = RNG.choice(walkable_cells)
            center = (cell.centerx, cell.centery)
            if view_rect is not None and view_rect.collidepoint(center):
                continue
            dx = center[0] - player.x
            dy = center[1] - player.y
            dist_sq = dx * dx + dy * dy
            if min_distance_sq is not None and dist_sq < min_distance_sq:
                continue
            if max_distance_sq is not None and dist_sq > max_distance_sq:
                continue
            fallback_x = RNG.uniform(-cell.width * 0.2, cell.width * 0.2)
            fallback_y = RNG.uniform(-cell.height * 0.2, cell.height * 0.2)
            return (int(cell.centerx + fallback_x), int(cell.centery + fallback_y))
    fallback_cell = RNG.choice(walkable_cells)
    fallback_x = RNG.uniform(-fallback_cell.width * 0.35, fallback_cell.width * 0.35)
    fallback_y = RNG.uniform(-fallback_cell.height * 0.35, fallback_cell.height * 0.35)
    return (
        int(fallback_cell.centerx + fallback_x),
        int(fallback_cell.centery + fallback_y),
    )


def find_exterior_spawn_position(
    level_width: int,
    level_height: int,
    *,
    hint_pos: tuple[float, float] | None = None,
    attempts: int = 5,
) -> tuple[int, int]:
    if hint_pos is None:
        return random_position_outside_building(level_width, level_height)
    points = [
        random_position_outside_building(level_width, level_height)
        for _ in range(max(1, attempts))
    ]
    return min(
        points,
        key=lambda pos: (pos[0] - hint_pos[0]) ** 2 + (pos[1] - hint_pos[1]) ** 2,
    )
