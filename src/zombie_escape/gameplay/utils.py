from __future__ import annotations

import pygame

from ..entities import Camera, Player, random_position_outside_building
from ..rng import get_rng
from ..render_constants import (
    FLASHLIGHT_FOG_SCALE_ONE,
    FLASHLIGHT_FOG_SCALE_TWO,
    FOG_RADIUS_SCALE,
    FOV_RADIUS,
)
from ..screen_constants import SCREEN_HEIGHT, SCREEN_WIDTH

_LOGICAL_SCREEN_RECT = pygame.Rect(0, 0, SCREEN_WIDTH, SCREEN_HEIGHT)
RNG = get_rng()

__all__ = [
    "rect_visible_on_screen",
    "fov_radius_for_flashlights",
    "is_entity_in_fov",
    "is_active_zombie_threat",
    "find_interior_spawn_positions",
    "find_nearby_offscreen_spawn_position",
    "find_exterior_spawn_position",
]


def rect_visible_on_screen(camera: Camera | None, rect: pygame.Rect) -> bool:
    if camera is None:
        return False
    return camera.apply_rect(rect).colliderect(_LOGICAL_SCREEN_RECT)


def fov_radius_for_flashlights(flashlight_count: int) -> float:
    count = max(0, int(flashlight_count))
    if count <= 0:
        scale = FOG_RADIUS_SCALE
    elif count == 1:
        scale = FLASHLIGHT_FOG_SCALE_ONE
    else:
        scale = FLASHLIGHT_FOG_SCALE_TWO
    return FOV_RADIUS * scale


def is_entity_in_fov(
    entity_rect: pygame.Rect,
    *,
    fov_target: pygame.sprite.Sprite | None,
    flashlight_count: int,
) -> bool:
    if fov_target is None:
        return False
    fov_radius = fov_radius_for_flashlights(flashlight_count)
    dx = entity_rect.centerx - fov_target.rect.centerx
    dy = entity_rect.centery - fov_target.rect.centery
    return (dx * dx + dy * dy) <= fov_radius * fov_radius


def is_active_zombie_threat(zombie: pygame.sprite.Sprite, *, now_ms: int) -> bool:
    """Return True only when the zombie can currently threaten humans."""
    return (not getattr(zombie, "carbonized", False)) and now_ms >= getattr(
        zombie, "patrol_paralyze_until_ms", 0
    )


def _scatter_positions_on_walkable(
    walkable_cells: list[tuple[int, int]],
    cell_size: int,
    spawn_rate: float,
    *,
    jitter_ratio: float = 0.35,
) -> list[tuple[int, int]]:
    positions: list[tuple[int, int]] = []
    if not walkable_cells or spawn_rate <= 0:
        return positions

    clamped_rate = max(0.0, min(1.0, spawn_rate))
    cells = list(walkable_cells)
    RNG.shuffle(cells)
    target_count = int(len(cells) * clamped_rate + 0.5)
    if target_count <= 0:
        return positions
    for cell_x, cell_y in cells[:target_count]:
        jitter_extent = cell_size * jitter_ratio
        jitter_x = RNG.uniform(-jitter_extent, jitter_extent)
        jitter_y = RNG.uniform(-jitter_extent, jitter_extent)
        base_x = (cell_x * cell_size) + (cell_size / 2)
        base_y = (cell_y * cell_size) + (cell_size / 2)
        positions.append((int(base_x + jitter_x), int(base_y + jitter_y)))
    return positions


def find_interior_spawn_positions(
    walkable_cells: list[tuple[int, int]],
    cell_size: int,
    spawn_rate: float,
    *,
    player: Player | None = None,
    min_player_dist: float | None = None,
) -> list[tuple[int, int]]:
    positions = _scatter_positions_on_walkable(
        walkable_cells,
        cell_size,
        spawn_rate,
        jitter_ratio=0.35,
    )
    if not positions and spawn_rate > 0:
        positions = _scatter_positions_on_walkable(
            walkable_cells,
            cell_size,
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
    walkable_cells: list[tuple[int, int]],
    cell_size: int,
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
        cell_x, cell_y = RNG.choice(walkable_cells)
        jitter_extent = cell_size * 0.35
        jitter_x = RNG.uniform(-jitter_extent, jitter_extent)
        jitter_y = RNG.uniform(-jitter_extent, jitter_extent)
        candidate = (
            int((cell_x * cell_size) + (cell_size / 2) + jitter_x),
            int((cell_y * cell_size) + (cell_size / 2) + jitter_y),
        )
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
    if player is not None and (
        min_distance_sq is not None or max_distance_sq is not None
    ):
        for _ in range(20):
            cell_x, cell_y = RNG.choice(walkable_cells)
            center = (
                (cell_x * cell_size) + (cell_size / 2),
                (cell_y * cell_size) + (cell_size / 2),
            )
            if view_rect is not None and view_rect.collidepoint(center):
                continue
            dx = center[0] - player.x
            dy = center[1] - player.y
            dist_sq = dx * dx + dy * dy
            if min_distance_sq is not None and dist_sq < min_distance_sq:
                continue
            if max_distance_sq is not None and dist_sq > max_distance_sq:
                continue
            fallback_extent = cell_size * 0.2
            fallback_x = RNG.uniform(-fallback_extent, fallback_extent)
            fallback_y = RNG.uniform(-fallback_extent, fallback_extent)
            return (int(center[0] + fallback_x), int(center[1] + fallback_y))
    fallback_cell_x, fallback_cell_y = RNG.choice(walkable_cells)
    fallback_center_x = (fallback_cell_x * cell_size) + (cell_size / 2)
    fallback_center_y = (fallback_cell_y * cell_size) + (cell_size / 2)
    fallback_extent = cell_size * 0.35
    fallback_x = RNG.uniform(-fallback_extent, fallback_extent)
    fallback_y = RNG.uniform(-fallback_extent, fallback_extent)
    return (
        int(fallback_center_x + fallback_x),
        int(fallback_center_y + fallback_y),
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
