from __future__ import annotations

from typing import Iterable

import pygame

try:
    from typing import Self
except ImportError:  # pragma: no cover - Python 3.10 fallback
    from typing_extensions import Self

from .movement import _circle_wall_collision
from .walls import Wall


class BaseLineBot(pygame.sprite.Sprite):
    """Shared line-bot mechanics used by patrol/carrier variants."""

    direction: tuple[int, int]

    def _movement_axis(self: Self) -> str:
        """Return the current movement axis from direction state."""
        dx, dy = self.direction
        if abs(dx) >= abs(dy):
            return "x"
        return "y"

    def _forward_cell(
        self: Self,
        *,
        x: float,
        y: float,
        cell_size: int,
        step_cells: int = 1,
    ) -> tuple[int, int] | None:
        """Return the grid cell ahead of (x, y) along current direction."""
        if cell_size <= 0:
            return None
        if step_cells < 1:
            step_cells = 1
        dx, dy = self.direction
        step_x = 0
        step_y = 0
        if abs(dx) >= abs(dy):
            if dx > 0:
                step_x = step_cells
            elif dx < 0:
                step_x = -step_cells
        else:
            if dy > 0:
                step_y = step_cells
            elif dy < 0:
                step_y = -step_cells
        return int(x // cell_size) + step_x, int(y // cell_size) + step_y

    def _reverse_direction(self: Self) -> None:
        self.direction = (-self.direction[0], -self.direction[1])

    def _handle_axis_collision(
        self: Self,
        *,
        next_x: float,
        next_y: float,
        current_x: float,
        current_y: float,
        walls: list[Wall],
        radius: float,
    ) -> tuple[float, float, bool]:
        final_x, final_y = next_x, next_y
        hit = False
        if next_x != current_x:
            for wall in walls:
                if _circle_wall_collision((next_x, current_y), radius, wall):
                    final_x = current_x
                    hit = True
                    break
        if next_y != current_y:
            for wall in walls:
                if _circle_wall_collision((final_x, next_y), radius, wall):
                    final_y = current_y
                    hit = True
                    break
        return final_x, final_y, hit

    def _resolve_circle_overlap(
        self: Self,
        cx: float,
        cy: float,
        radius: float,
        *,
        other_x: float,
        other_y: float,
        other_radius: float,
    ) -> tuple[float, float]:
        dx = cx - other_x
        dy = cy - other_y
        dist_sq = dx * dx + dy * dy
        min_dist = radius + other_radius
        if dist_sq <= 0:
            return cx + min_dist, cy
        dist = dist_sq**0.5
        if dist >= min_dist:
            return cx, cy
        push = min_dist - dist
        return cx + (dx / dist) * push, cy + (dy / dist) * push

    def _push_overlapping_entities(
        self: Self,
        *,
        center_x: float,
        center_y: float,
        radius: float,
        entities: Iterable[pygame.sprite.Sprite],
        ignore: Iterable[pygame.sprite.Sprite] = (),
    ) -> None:
        ignored = set(ignore)
        for entity in entities:
            if entity is self or entity in ignored:
                continue
            if getattr(entity, "mounted_vehicle", None) is not None:
                continue
            ex = float(entity.rect.centerx)
            ey = float(entity.rect.centery)
            er = float(
                getattr(
                    entity,
                    "collision_radius",
                    getattr(entity, "radius", max(entity.rect.width, entity.rect.height) / 2),
                )
            )
            new_x, new_y = self._resolve_circle_overlap(
                ex,
                ey,
                er,
                other_x=center_x,
                other_y=center_y,
                other_radius=radius,
            )
            if new_x == ex and new_y == ey:
                continue
            entity.rect.center = (int(new_x), int(new_y))
            if hasattr(entity, "x"):
                entity.x = float(entity.rect.centerx)
            if hasattr(entity, "y"):
                entity.y = float(entity.rect.centery)
