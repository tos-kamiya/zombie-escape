from __future__ import annotations

from typing import cast

import pygame

from ..world_grid import WallIndex, walls_for_radius
from .movement import _circle_wall_collision
from .walls import Wall


def _sprite_center_and_radius(
    sprite: pygame.sprite.Sprite,
) -> tuple[tuple[int, int], float]:
    center = sprite.rect.center
    if hasattr(sprite, "radius"):
        radius = float(sprite.radius)
    else:
        radius = float(max(sprite.rect.width, sprite.rect.height) / 2)
    return center, radius


def _walls_for_sprite(
    sprite: pygame.sprite.Sprite,
    wall_index: WallIndex,
    *,
    cell_size: int,
    grid_cols: int | None = None,
    grid_rows: int | None = None,
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


def _collide_sprite_wall(
    sprite: pygame.sprite.Sprite, wall: pygame.sprite.Sprite
) -> bool:
    if hasattr(sprite, "radius"):
        center = sprite.rect.center
        radius = float(sprite.radius)
        return _circle_wall_collision(center, radius, wall)
    if hasattr(wall, "collides_rect"):
        return wall.collides_rect(sprite.rect)
    if hasattr(sprite, "collides_rect"):
        return sprite.collides_rect(wall.rect)
    return sprite.rect.colliderect(wall.rect)


def _spritecollide_walls(
    sprite: pygame.sprite.Sprite,
    walls: pygame.sprite.Group,
    *,
    dokill: bool = False,
    wall_index: WallIndex | None = None,
    cell_size: int | None = None,
    grid_cols: int | None = None,
    grid_rows: int | None = None,
) -> list[Wall]:
    if wall_index is None:
        return cast(
            list[Wall],
            pygame.sprite.spritecollide(
                sprite, walls, dokill, collided=_collide_sprite_wall
            ),
        )
    if cell_size is None:
        raise ValueError("cell_size is required when using wall_index")
    candidates = _walls_for_sprite(
        sprite,
        wall_index,
        cell_size=cell_size,
        grid_cols=grid_cols,
        grid_rows=grid_rows,
    )
    if not candidates:
        return []
    hit_list = [wall for wall in candidates if _collide_sprite_wall(sprite, wall)]
    if dokill:
        for wall in hit_list:
            wall.kill()
    return hit_list


def spritecollideany_walls(
    sprite: pygame.sprite.Sprite,
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
    if cell_size is None:
        raise ValueError("cell_size is required when using wall_index")
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
