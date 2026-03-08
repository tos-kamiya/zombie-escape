from __future__ import annotations

from typing import Protocol, cast

import pygame

from ..world_grid import WallIndex, walls_for_radius
from .base import RectSprite
from .movement import _circle_wall_collision
from .walls import Wall


class CollisionSprite(Protocol):
    rect: pygame.Rect

    def get_collision_circle(self) -> tuple[tuple[int, int], float]: ...


class RadiusSprite(Protocol):
    rect: pygame.Rect
    radius: float
    collision_radius: float


def _sprite_center_and_radius(
    sprite: RectSprite,
) -> tuple[tuple[int, int], float]:
    center = sprite.rect.center
    if hasattr(sprite, "radius"):
        radius_sprite = cast(RadiusSprite, sprite)
        radius = float(
            getattr(radius_sprite, "collision_radius", radius_sprite.radius)
        )
    else:
        radius = float(max(sprite.rect.width, sprite.rect.height) / 2)
    return center, radius


def _sprite_collision_circle(
    sprite: RectSprite,
) -> tuple[tuple[int, int], float]:
    if hasattr(sprite, "get_collision_circle"):
        collision_sprite = cast(CollisionSprite, sprite)
        center, radius = collision_sprite.get_collision_circle()
        return (int(center[0]), int(center[1])), float(radius)
    return _sprite_center_and_radius(sprite)


def collide_circle_custom(
    sprite_a: RectSprite, sprite_b: RectSprite
) -> bool:
    center_a, radius_a = _sprite_collision_circle(sprite_a)
    center_b, radius_b = _sprite_collision_circle(sprite_b)
    dx = center_a[0] - center_b[0]
    dy = center_a[1] - center_b[1]
    radius = radius_a + radius_b
    return dx * dx + dy * dy <= radius * radius


def _walls_for_sprite(
    sprite: RectSprite,
    wall_index: WallIndex,
    *,
    cell_size: int,
    grid_cols: int,
    grid_rows: int,
) -> list[Wall]:
    center, radius = _sprite_center_and_radius(sprite)
    return walls_for_radius(
        wall_index,
        center,
        radius,
        cell_size=cell_size,
        grid_cols=grid_cols,
        grid_rows=grid_rows,
    )


def _collide_sprite_wall(sprite: RectSprite, wall: Wall) -> bool:
    if hasattr(sprite, "radius"):
        radius_sprite = cast(RadiusSprite, sprite)
        center = radius_sprite.rect.center
        radius = float(
            getattr(radius_sprite, "collision_radius", radius_sprite.radius)
        )
        return _circle_wall_collision(center, radius, wall)
    return wall.collides_rect(sprite.rect)


def spritecollideany_walls(
    sprite: RectSprite,
    walls: pygame.sprite.Group,
    *,
    wall_index: WallIndex | None = None,
    cell_size: int | None = None,
    grid_cols: int | None = None,
    grid_rows: int | None = None,
) -> Wall | None:
    if wall_index is None:
        return cast(
            Wall | None,
            pygame.sprite.spritecollideany(
                sprite, walls, collided=_collide_sprite_wall
            ),
        )
    if cell_size is None or grid_cols is None or grid_rows is None:
        raise ValueError(
            "cell_size/grid_cols/grid_rows are required when using wall_index"
        )
    for wall in _walls_for_sprite(
        sprite,
        wall_index,
        cell_size=cell_size,
        grid_cols=grid_cols,
        grid_rows=grid_rows,
    ):
        if _collide_sprite_wall(sprite, wall):
            return wall
    return None
