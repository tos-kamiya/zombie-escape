"""Car entity logic."""

from __future__ import annotations
from typing import Iterable

try:
    from typing import Self
except ImportError:  # pragma: no cover - Python 3.10 fallback
    from typing_extensions import Self

import pygame

from ..entities_constants import (
    CAR_HEALTH,
    CAR_HEIGHT,
    CAR_SPEED,
    CAR_WALL_DAMAGE,
    CAR_WIDTH,
)
from ..render_assets import (
    angle_bin_from_vector,
    build_car_directional_surfaces,
    build_car_surface,
    paint_car_surface,
    resolve_car_color,
)
from ..render_constants import ANGLE_BINS
from .movement import _circle_wall_collision
from .walls import Wall


class Car(pygame.sprite.Sprite):
    def __init__(self: Self, x: int, y: int, *, appearance: str = "default") -> None:
        super().__init__()
        self.facing_bin = ANGLE_BINS * 3 // 4
        self.input_facing_bin = self.facing_bin
        self.original_image = build_car_surface(CAR_WIDTH, CAR_HEIGHT)
        self.directional_images: list[pygame.Surface] = []
        self.appearance = appearance
        self.image = self.original_image.copy()
        self.rect = self.image.get_rect(center=(x, y))
        self.speed = CAR_SPEED
        self.x = float(self.rect.centerx)
        self.y = float(self.rect.centery)
        self.health = CAR_HEALTH
        self.max_health = CAR_HEALTH
        self.collision_radius = _car_body_radius(CAR_WIDTH, CAR_HEIGHT)
        self.last_move_dx = 0.0
        self.last_move_dy = 0.0
        self._update_color()

    def _take_damage(self: Self, amount: float) -> None:
        if self.health > 0:
            self.health -= amount
            self._update_color()

    def _update_color(self: Self) -> None:
        health_ratio = max(0, self.health / self.max_health)
        color = resolve_car_color(health_ratio=health_ratio, appearance=self.appearance)
        paint_car_surface(
            self.original_image,
            width=CAR_WIDTH,
            height=CAR_HEIGHT,
            color=color,
        )
        self.directional_images = build_car_directional_surfaces(self.original_image)
        self.image = self.directional_images[self.facing_bin]
        old_center = self.rect.center
        self.rect = self.image.get_rect(center=old_center)

    def update_facing_from_input(self: Self, dx: float, dy: float) -> None:
        new_bin = angle_bin_from_vector(dx, dy)
        if new_bin is None:
            return
        self.input_facing_bin = new_bin
        self._set_facing_bin(self.input_facing_bin)

    def _set_facing_bin(self: Self, new_bin: int) -> None:
        if new_bin == self.facing_bin:
            return
        if not self.directional_images:
            return
        center = self.rect.center
        self.facing_bin = new_bin
        self.image = self.directional_images[self.facing_bin]
        self.rect = self.image.get_rect(center=center)

    def move(
        self: Self,
        dx: float,
        dy: float,
        walls: Iterable[Wall],
        *,
        walls_nearby: bool = False,
        cell_size: int | None = None,
        pitfall_cells: set[tuple[int, int]] | None = None,
    ) -> None:
        if self.health <= 0:
            return
        if dx == 0 and dy == 0:
            self.rect.center = (int(self.x), int(self.y))
            self.last_move_dx = 0.0
            self.last_move_dy = 0.0
            return
        new_x = self.x + dx
        new_y = self.y + dy

        hit_walls = []
        if walls_nearby:
            possible_walls = list(walls)
        else:
            possible_walls = [
                w
                for w in walls
                if abs(w.rect.centery - self.y) < 100
                and abs(w.rect.centerx - new_x) < 100
            ]
        car_center = (new_x, new_y)
        for wall in possible_walls:
            if _circle_wall_collision(car_center, self.collision_radius, wall):
                hit_walls.append(wall)

        in_pitfall = False
        if pitfall_cells and cell_size:
            cx, cy = int(new_x // cell_size), int(new_y // cell_size)
            if (cx, cy) in pitfall_cells:
                in_pitfall = True

        if hit_walls or in_pitfall:
            if hit_walls:
                self._take_damage(CAR_WALL_DAMAGE)
                hit_walls.sort(
                    key=lambda w: (
                        (w.rect.centery - self.y) ** 2 + (w.rect.centerx - self.x) ** 2
                    )
                )
                nearest_wall = hit_walls[0]
                new_x += (self.x - nearest_wall.rect.centerx) * 1.2
                new_y += (self.y - nearest_wall.rect.centery) * 1.2
            else:
                # Pitfall only: bounce back from current position
                new_x = self.x - dx * 0.5
                new_y = self.y - dy * 0.5

        self.x = new_x
        self.y = new_y
        self.rect.center = (int(self.x), int(self.y))
        self.last_move_dx = dx
        self.last_move_dy = dy


def _car_body_radius(width: float, height: float) -> float:
    """Approximate car collision radius using only its own dimensions."""
    return min(width, height) / 2
