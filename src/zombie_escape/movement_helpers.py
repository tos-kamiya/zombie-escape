from __future__ import annotations

from typing import Callable, Literal, TypeVar

import pygame

T = TypeVar("T")


def pitfall_target(
    *,
    x: float,
    y: float,
    cell_size: int,
    pitfall_cells: set[tuple[int, int]],
    pull_distance: float,
) -> tuple[int, int] | None:
    """Return the pulled target position if inside a pitfall cell."""
    cx = int(x // cell_size)
    cy = int(y // cell_size)
    if (cx, cy) not in pitfall_cells:
        return None

    cell_center_x = (cx * cell_size) + (cell_size // 2)
    cell_center_y = (cy * cell_size) + (cell_size // 2)
    dx, dy = cell_center_x - x, cell_center_y - y
    dist = (dx * dx + dy * dy) ** 0.5
    if dist > 0:
        move_factor = min(1.0, pull_distance / dist)
        return int(x + dx * move_factor), int(y + dy * move_factor)
    return int(x), int(y)


def move_axis_with_pitfall(
    *,
    sprite: pygame.sprite.Sprite,
    axis: Literal["x", "y"],
    delta: float,
    collide: Callable[[], T | None],
    cell_size: int | None,
    pitfall_cells: set[tuple[int, int]],
    can_jump_now: bool,
    now: int,
    rollback_factor: float = 1.0,
    clamp_range: tuple[float, float] | None = None,
    on_wall_hit: Callable[[T], None] | None = None,
) -> None:
    if not delta:
        return

    if axis == "x":
        sprite.x += delta  # type: ignore[attr-defined]
        if clamp_range is not None:
            sprite.x = min(clamp_range[1], max(clamp_range[0], sprite.x))  # type: ignore[attr-defined]
        sprite.rect.centerx = int(sprite.x)  # type: ignore[attr-defined]
    else:
        sprite.y += delta  # type: ignore[attr-defined]
        if clamp_range is not None:
            sprite.y = min(clamp_range[1], max(clamp_range[0], sprite.y))  # type: ignore[attr-defined]
        sprite.rect.centery = int(sprite.y)  # type: ignore[attr-defined]

    hit = collide()
    blocked_by_pitfall = False

    if not sprite.is_jumping and pitfall_cells and cell_size:  # type: ignore[attr-defined]
        cx = int(sprite.rect.centerx // cell_size)
        cy = int(sprite.rect.centery // cell_size)
        if (cx, cy) in pitfall_cells:
            if can_jump_now:
                sprite.is_jumping = True  # type: ignore[attr-defined]
                sprite.jump_start_at = now  # type: ignore[attr-defined]
            else:
                blocked_by_pitfall = True

    if hit or blocked_by_pitfall:
        if hit and on_wall_hit is not None:
            on_wall_hit(hit)
        if axis == "x":
            sprite.x -= delta * rollback_factor  # type: ignore[attr-defined]
            if clamp_range is not None:
                sprite.x = min(clamp_range[1], max(clamp_range[0], sprite.x))  # type: ignore[attr-defined]
            sprite.rect.centerx = int(sprite.x)  # type: ignore[attr-defined]
        else:
            sprite.y -= delta * rollback_factor  # type: ignore[attr-defined]
            if clamp_range is not None:
                sprite.y = min(clamp_range[1], max(clamp_range[0], sprite.y))  # type: ignore[attr-defined]
            sprite.rect.centery = int(sprite.y)  # type: ignore[attr-defined]
