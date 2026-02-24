from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Callable, Literal, TypeVar

import pygame

from .movement import _circle_rect_collision, _circle_wall_collision

T = TypeVar("T")


def _sprite_in_pitfall(
    sprite: pygame.sprite.Sprite,
    *,
    cell_size: int,
    pitfall_cells: set[tuple[int, int]],
) -> bool:
    cx = int(sprite.rect.centerx // cell_size)
    cy = int(sprite.rect.centery // cell_size)
    return (cx, cy) in pitfall_cells


def _repel_from_pitfall_center(
    *,
    sprite: pygame.sprite.Sprite,
    axis: Literal["x", "y"],
    delta: float,
    rollback_factor: float,
    cell_size: int,
    clamp_range: tuple[float, float] | None,
) -> None:
    cell_x = int(sprite.rect.centerx // cell_size)
    cell_y = int(sprite.rect.centery // cell_size)
    center_x = (cell_x + 0.5) * cell_size
    center_y = (cell_y + 0.5) * cell_size
    if axis == "x":
        offset = sprite.x - center_x  # type: ignore[attr-defined]
    else:
        offset = sprite.y - center_y  # type: ignore[attr-defined]
    if abs(offset) < 0.01:
        offset = -delta if delta else -1.0
    direction = 1.0 if offset > 0 else -1.0
    repel_amount = max(1.0, abs(delta) * rollback_factor)
    if axis == "x":
        sprite.x += direction * repel_amount  # type: ignore[attr-defined]
        if clamp_range is not None:
            sprite.x = min(clamp_range[1], max(clamp_range[0], sprite.x))  # type: ignore[attr-defined]
        sprite.rect.centerx = int(sprite.x)  # type: ignore[attr-defined]
    else:
        sprite.y += direction * repel_amount  # type: ignore[attr-defined]
        if clamp_range is not None:
            sprite.y = min(clamp_range[1], max(clamp_range[0], sprite.y))  # type: ignore[attr-defined]
        sprite.rect.centery = int(sprite.y)  # type: ignore[attr-defined]


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


def update_directional_image_scale(sprite: pygame.sprite.Sprite, scale: float) -> None:
    """Scale current directional image, preserving center."""
    base_img = sprite.directional_images[sprite.facing_bin]  # type: ignore[attr-defined]
    if scale == 1.0:
        sprite.image = base_img
    else:
        w, h = base_img.get_size()
        sprite.image = pygame.transform.scale(
            base_img, (int(w * scale), int(h * scale))
        )
    old_center = sprite.rect.center
    sprite.rect = sprite.image.get_rect(center=old_center)


def set_facing_bin(sprite: pygame.sprite.Sprite, new_bin: int) -> None:
    """Update facing bin and image, preserving center."""
    if new_bin == sprite.facing_bin:  # type: ignore[attr-defined]
        return
    center = sprite.rect.center
    sprite.facing_bin = new_bin  # type: ignore[attr-defined]
    sprite.image = sprite.directional_images[sprite.facing_bin]  # type: ignore[attr-defined]
    sprite.rect = sprite.image.get_rect(center=center)


@dataclass
class SeparationResult:
    x: float
    y: float
    hit_walls: list[pygame.sprite.Sprite]
    hit_cells: set[tuple[int, int]]


def _repel_circle_from_rect(
    x: float,
    y: float,
    radius: float,
    rect_obj: pygame.Rect,
    *,
    epsilon: float = 0.0,
) -> tuple[float, float]:
    closest_x = max(rect_obj.left, min(x, rect_obj.right))
    closest_y = max(rect_obj.top, min(y, rect_obj.bottom))
    dx = x - closest_x
    dy = y - closest_y
    dist = math.hypot(dx, dy)
    target = radius + max(0.0, epsilon)
    if dist > 1e-6:
        penetration = target - dist
        if penetration <= 0.0:
            return x, y
        return x + (dx / dist) * penetration, y + (dy / dist) * penetration

    left_pen = (x - rect_obj.left) + target
    right_pen = (rect_obj.right - x) + target
    top_pen = (y - rect_obj.top) + target
    bottom_pen = (rect_obj.bottom - y) + target
    penetration, nx, ny = min(
        (
            (left_pen, -1.0, 0.0),
            (right_pen, 1.0, 0.0),
            (top_pen, 0.0, -1.0),
            (bottom_pen, 0.0, 1.0),
        ),
        key=lambda item: item[0],
    )
    push = max(0.0, penetration)
    return x + nx * push, y + ny * push


def separate_circle_from_blockers(
    *,
    x: float,
    y: float,
    radius: float,
    walls: list[pygame.sprite.Sprite],
    cell_size: int,
    blocked_cells: set[tuple[int, int]] | None = None,
    grid_cols: int | None = None,
    grid_rows: int | None = None,
    max_attempts: int = 4,
    epsilon: float = 0.01,
) -> SeparationResult:
    blocked = blocked_cells or set()
    hit_walls: list[pygame.sprite.Sprite] = []
    hit_wall_ids: set[int] = set()
    hit_cells: set[tuple[int, int]] = set()
    cur_x, cur_y = x, y

    for _ in range(max(1, max_attempts)):
        moved = False
        for wall in walls:
            if not wall.alive():
                continue
            if not _circle_wall_collision((cur_x, cur_y), radius, wall):
                continue
            wall_id = id(wall)
            if wall_id not in hit_wall_ids:
                hit_wall_ids.add(wall_id)
                hit_walls.append(wall)
            cur_x, cur_y = _repel_circle_from_rect(
                cur_x, cur_y, radius, wall.rect, epsilon=epsilon
            )
            moved = True

        if blocked and cell_size > 0 and grid_cols and grid_rows:
            min_cell_x = max(0, int((cur_x - radius) // cell_size))
            max_cell_x = min(grid_cols - 1, int((cur_x + radius) // cell_size))
            min_cell_y = max(0, int((cur_y - radius) // cell_size))
            max_cell_y = min(grid_rows - 1, int((cur_y + radius) // cell_size))
            for cy in range(min_cell_y, max_cell_y + 1):
                for cx in range(min_cell_x, max_cell_x + 1):
                    cell = (cx, cy)
                    if cell not in blocked:
                        continue
                    rect_obj = pygame.Rect(
                        cx * cell_size,
                        cy * cell_size,
                        cell_size,
                        cell_size,
                    )
                    if not _circle_rect_collision((cur_x, cur_y), radius, rect_obj):
                        continue
                    hit_cells.add(cell)
                    cur_x, cur_y = _repel_circle_from_rect(
                        cur_x, cur_y, radius, rect_obj, epsilon=epsilon
                    )
                    moved = True

        if not moved:
            break

    return SeparationResult(x=cur_x, y=cur_y, hit_walls=hit_walls, hit_cells=hit_cells)


def move_axis_with_pitfall(
    *,
    sprite: pygame.sprite.Sprite,
    axis: Literal["x", "y"],
    delta: float,
    collide: Callable[[], T | None],
    cell_size: int | None,
    pitfall_cells: set[tuple[int, int]],
    blocked_cells: set[tuple[int, int]] | None = None,
    pending_fall_cells: set[tuple[int, int]] | None = None,
    can_jump_now: bool,
    now: int,
    rollback_factor: float = 1.0,
    clamp_range: tuple[float, float] | None = None,
    on_wall_hit: Callable[[T], None] | None = None,
) -> None:
    if not delta:
        return

    pending_cells = (
        pitfall_cells if pending_fall_cells is None else pending_fall_cells
    )

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
    blocked_by_cell = False
    blocked_by_pitfall = False

    if blocked_cells and cell_size:
        cx = int(sprite.rect.centerx // cell_size)
        cy = int(sprite.rect.centery // cell_size)
        blocked_by_cell = (cx, cy) in blocked_cells

    if not sprite.is_jumping and pitfall_cells and cell_size:  # type: ignore[attr-defined]
        cx = int(sprite.rect.centerx // cell_size)
        cy = int(sprite.rect.centery // cell_size)
        if (cx, cy) in pitfall_cells:
            if can_jump_now:
                sprite.is_jumping = True  # type: ignore[attr-defined]
                sprite.jump_start_at = now  # type: ignore[attr-defined]
            else:
                blocked_by_pitfall = True

    if hit or blocked_by_cell or blocked_by_pitfall:
        if hit and on_wall_hit is not None:
            on_wall_hit(hit)
        if blocked_by_pitfall and cell_size:
            _repel_from_pitfall_center(
                sprite=sprite,
                axis=axis,
                delta=delta,
                rollback_factor=rollback_factor,
                cell_size=cell_size,
                clamp_range=clamp_range,
            )
        elif axis == "x":
            sprite.x -= delta * rollback_factor  # type: ignore[attr-defined]
            if clamp_range is not None:
                sprite.x = min(clamp_range[1], max(clamp_range[0], sprite.x))  # type: ignore[attr-defined]
            sprite.rect.centerx = int(sprite.x)  # type: ignore[attr-defined]
        else:
            sprite.y -= delta * rollback_factor  # type: ignore[attr-defined]
            if clamp_range is not None:
                sprite.y = min(clamp_range[1], max(clamp_range[0], sprite.y))  # type: ignore[attr-defined]
            sprite.rect.centery = int(sprite.y)  # type: ignore[attr-defined]
        if (
            blocked_by_pitfall
            and cell_size
            and _sprite_in_pitfall(
                sprite,
                cell_size=cell_size,
                pitfall_cells=pending_cells,
            )
        ):
            sprite.pending_pitfall_fall = True  # type: ignore[attr-defined]
