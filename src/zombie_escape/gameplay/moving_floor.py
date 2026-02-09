from __future__ import annotations

from typing import Protocol

import pygame

from ..entities_constants import MOVING_FLOOR_SPEED, MovingFloorDirection
from ..models import LevelLayout


class _MovingFloorEntity(Protocol):
    x: float
    y: float
    rect: pygame.Rect


def is_entity_on_moving_floor(entity: object) -> bool:
    return bool(getattr(entity, "on_moving_floor", False))


def _floor_tile_for_entity(
    entity: _MovingFloorEntity,
    layout: LevelLayout,
    *,
    cell_size: int,
) -> tuple[MovingFloorDirection, pygame.Rect] | None:
    if cell_size <= 0 or not layout.moving_floor_cells:
        return None
    cell_x = int(entity.rect.centerx // cell_size)
    cell_y = int(entity.rect.centery // cell_size)
    direction = layout.moving_floor_cells.get((cell_x, cell_y))
    if direction is None:
        return None
    tile_rect = pygame.Rect(
        cell_x * cell_size,
        cell_y * cell_size,
        cell_size,
        cell_size,
    )
    radius = getattr(entity, "radius", None)
    if radius is not None:
        cx = float(entity.rect.centerx)
        cy = float(entity.rect.centery)
        if direction in (MovingFloorDirection.UP, MovingFloorDirection.DOWN):
            if cx - radius < tile_rect.left or cx + radius > tile_rect.right:
                return None
            if direction == MovingFloorDirection.UP:
                if cy - radius < tile_rect.top:
                    return None
                if cy + radius <= tile_rect.top:
                    return None
                if cy - radius >= tile_rect.bottom:
                    return None
            else:
                if cy + radius > tile_rect.bottom:
                    return None
                if cy - radius >= tile_rect.bottom:
                    return None
                if cy + radius <= tile_rect.top:
                    return None
        else:
            if cy - radius < tile_rect.top or cy + radius > tile_rect.bottom:
                return None
            if direction == MovingFloorDirection.LEFT:
                if cx - radius < tile_rect.left:
                    return None
                if cx + radius <= tile_rect.left:
                    return None
                if cx - radius >= tile_rect.right:
                    return None
            else:
                if cx + radius > tile_rect.right:
                    return None
                if cx - radius >= tile_rect.right:
                    return None
                if cx + radius <= tile_rect.left:
                    return None
    else:
        if not tile_rect.contains(entity.rect):
            return None
    return direction, tile_rect


def get_overlapping_moving_floor_direction(
    rect: pygame.Rect,
    layout: LevelLayout,
    *,
    cell_size: int,
) -> MovingFloorDirection | None:
    """Return moving-floor direction for any tile overlapping the rect."""
    if cell_size <= 0 or not layout.moving_floor_cells:
        return None
    center_x = int(rect.centerx // cell_size)
    center_y = int(rect.centery // cell_size)
    direction = layout.moving_floor_cells.get((center_x, center_y))
    if direction is not None:
        return direction

    min_x = max(0, int(rect.left // cell_size))
    max_x = max(0, int((rect.right - 1) // cell_size))
    min_y = max(0, int(rect.top // cell_size))
    max_y = max(0, int((rect.bottom - 1) // cell_size))
    for y in range(min_y, max_y + 1):
        for x in range(min_x, max_x + 1):
            direction = layout.moving_floor_cells.get((x, y))
            if direction is not None:
                return direction
    return None


def get_moving_floor_drift(
    rect: pygame.Rect,
    layout: LevelLayout,
    *,
    cell_size: int,
    speed: float = MOVING_FLOOR_SPEED,
) -> tuple[float, float]:
    """Return the drift vector for any moving floor overlapping the rect."""
    direction = get_overlapping_moving_floor_direction(
        rect,
        layout,
        cell_size=cell_size,
    )
    if direction is None:
        return 0.0, 0.0
    if direction == MovingFloorDirection.UP:
        return 0.0, -speed
    if direction == MovingFloorDirection.DOWN:
        return 0.0, speed
    if direction == MovingFloorDirection.LEFT:
        return -speed, 0.0
    if direction == MovingFloorDirection.RIGHT:
        return speed, 0.0
    return 0.0, 0.0


def apply_moving_floor(
    entity: _MovingFloorEntity,
    layout: LevelLayout,
    *,
    cell_size: int,
    speed: float = MOVING_FLOOR_SPEED,
    drift_factor: float = 1.0,
) -> bool:
    dx, dy = get_moving_floor_drift(
        entity.rect,
        layout,
        cell_size=cell_size,
        speed=speed,
    )
    dx *= drift_factor
    dy *= drift_factor
    on_floor = abs(dx) > 0.0 or abs(dy) > 0.0
    setattr(entity, "on_moving_floor", on_floor)
    return on_floor


def get_moving_floor_direction(
    entity: _MovingFloorEntity,
    layout: LevelLayout,
    *,
    cell_size: int,
) -> MovingFloorDirection | None:
    info = _floor_tile_for_entity(entity, layout, cell_size=cell_size)
    if info is None:
        return None
    return info[0]
