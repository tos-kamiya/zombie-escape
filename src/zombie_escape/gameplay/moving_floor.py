from __future__ import annotations

from typing import Protocol

import pygame

from ..entities_constants import MOVING_FLOOR_SPEED, MovingFloorDirection
from ..models import LevelLayout


class _MovingFloorEntity(Protocol):
    x: float
    y: float
    rect: pygame.Rect
    radius: float


def is_entity_on_moving_floor(entity: object) -> bool:
    return bool(getattr(entity, "on_moving_floor", False))


def get_floor_overlap_rect(entity: _MovingFloorEntity) -> pygame.Rect:
    radius = getattr(entity, "radius", None)
    if radius is None:
        return entity.rect
    size = max(1, int(radius * 2))
    rect = pygame.Rect(0, 0, size, size)
    rect.center = (int(entity.x), int(entity.y))
    return rect



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
