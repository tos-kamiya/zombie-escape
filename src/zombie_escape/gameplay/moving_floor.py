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


def apply_moving_floor(
    entity: _MovingFloorEntity,
    layout: LevelLayout,
    *,
    cell_size: int,
    speed: float = MOVING_FLOOR_SPEED,
) -> bool:
    info = _floor_tile_for_entity(entity, layout, cell_size=cell_size)
    if info is None:
        setattr(entity, "on_moving_floor", False)
        return False
    direction, tile_rect = info

    radius = getattr(entity, "radius", None)
    if radius is None:
        radius = max(entity.rect.width, entity.rect.height) / 2
    min_x = tile_rect.left + radius
    max_x = tile_rect.right - radius
    min_y = tile_rect.top + radius
    max_y = tile_rect.bottom - radius

    dx = 0.0
    dy = 0.0
    if direction == MovingFloorDirection.UP:
        dy = -speed
        floor_dir = (0, -1)
    elif direction == MovingFloorDirection.DOWN:
        dy = speed
        floor_dir = (0, 1)
    elif direction == MovingFloorDirection.LEFT:
        dx = -speed
        floor_dir = (-1, 0)
    elif direction == MovingFloorDirection.RIGHT:
        dx = speed
        floor_dir = (1, 0)
    else:
        floor_dir = (0, 0)

    if hasattr(entity, "direction"):
        entity.direction = floor_dir
        if hasattr(entity, "_set_arrow_source"):
            entity._set_arrow_source(False)

    new_x = min(max(entity.x + dx, min_x), max_x)
    new_y = min(max(entity.y + dy, min_y), max_y)
    exiting = False
    if direction == MovingFloorDirection.UP and entity.y + dy <= min_y:
        new_y = min_y - 1
        exiting = True
    elif direction == MovingFloorDirection.DOWN and entity.y + dy >= max_y:
        new_y = max_y + 1
        exiting = True
    elif direction == MovingFloorDirection.LEFT and entity.x + dx <= min_x:
        new_x = min_x - 1
        exiting = True
    elif direction == MovingFloorDirection.RIGHT and entity.x + dx >= max_x:
        new_x = max_x + 1
        exiting = True

    move_x = new_x - entity.x
    move_y = new_y - entity.y

    entity.x = float(new_x)
    entity.y = float(new_y)
    entity.rect.center = (int(entity.x), int(entity.y))
    setattr(entity, "on_moving_floor", not exiting)
    if hasattr(entity, "last_move_dx"):
        entity.last_move_dx = move_x
    if hasattr(entity, "last_move_dy"):
        entity.last_move_dy = move_y
    if hasattr(entity, "_update_facing_from_movement"):
        entity._update_facing_from_movement(move_x, move_y)
    if hasattr(entity, "_apply_render_overlays"):
        entity._apply_render_overlays()
    if hasattr(entity, "_update_input_facing"):
        entity._update_input_facing(move_x, move_y)
    if hasattr(entity, "update_facing_from_input"):
        entity.update_facing_from_input(move_x, move_y)
    if hasattr(entity, "_update_facing_for_bump"):
        entity._update_facing_for_bump(False)
    return True


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
