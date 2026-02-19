"""Car entity logic."""

from __future__ import annotations
from typing import Iterable

import math

try:
    from typing import Self
except ImportError:  # pragma: no cover - Python 3.10 fallback
    from typing_extensions import Self

import pygame

from ..entities_constants import (
    CAR_HEALTH,
    CAR_HEIGHT,
    CAR_PITFALL_FALL_CENTER_RATIO,
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
from .movement import _circle_wall_collision, separate_circle_from_walls
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
        self.collision_radius = float(CAR_WIDTH) / 2.0
        self.shadow_radius = max(1, int(self.collision_radius * 1.2))
        self.shadow_offset_scale = 1.0
        self.last_move_dx = 0.0
        self.last_move_dy = 0.0
        self.last_safe_pos: tuple[float, float] = (self.x, self.y)
        self.pending_pitfall_fall = False
        self.pitfall_eject_pos: tuple[int, int] | None = None
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

    def _collision_center(self: Self, x: float, y: float) -> tuple[float, float]:
        angle = (self.facing_bin % ANGLE_BINS) * (math.tau / ANGLE_BINS)
        offset = (CAR_HEIGHT / 2.0) - self.collision_radius
        return (
            x + math.cos(angle) * offset,
            y + math.sin(angle) * offset,
        )

    def get_collision_circle(self: Self) -> tuple[tuple[int, int], float]:
        cx, cy = self._collision_center(self.x, self.y)
        return (int(round(cx)), int(round(cy))), float(self.collision_radius)

    def _pitfall_cell_at_position(
        self: Self,
        x: float,
        y: float,
        *,
        cell_size: int,
        pitfall_cells: set[tuple[int, int]],
    ) -> tuple[int, int] | None:
        cx, cy = self._collision_center(x, y)
        cell = (int(cx // cell_size), int(cy // cell_size))
        if cell in pitfall_cells:
            return cell
        return None

    def _is_pitfall_fall_position(
        self: Self,
        x: float,
        y: float,
        *,
        cell_size: int,
        pitfall_cell: tuple[int, int],
    ) -> bool:
        cx, cy = self._collision_center(x, y)
        pit_x = (pitfall_cell[0] + 0.5) * cell_size
        pit_y = (pitfall_cell[1] + 0.5) * cell_size
        threshold = cell_size * CAR_PITFALL_FALL_CENTER_RATIO
        return math.hypot(cx - pit_x, cy - pit_y) <= threshold

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
        self.pending_pitfall_fall = False
        self.pitfall_eject_pos = None
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
        car_center = self._collision_center(new_x, new_y)
        for wall in possible_walls:
            if _circle_wall_collision(car_center, self.collision_radius, wall):
                hit_walls.append(wall)

        entered_pitfall = False
        if pitfall_cells and cell_size:
            entered_pitfall = (
                self._pitfall_cell_at_position(
                    new_x,
                    new_y,
                    cell_size=cell_size,
                    pitfall_cells=pitfall_cells,
                )
                is not None
            )

        if hit_walls or entered_pitfall:
            if hit_walls:
                self._take_damage(CAR_WALL_DAMAGE)
                hit_walls.sort(
                    key=lambda w: (
                        (w.rect.centery - self.y) ** 2 + (w.rect.centerx - self.x) ** 2
                    )
                )
                nearest_wall = hit_walls[0]
                ordered_walls = [nearest_wall] + [
                    wall for wall in hit_walls if wall is not nearest_wall
                ]
                center_before = self._collision_center(new_x, new_y)
                center_after, separated = separate_circle_from_walls(
                    center_before,
                    float(self.collision_radius),
                    ordered_walls,
                    scale=2.1,
                    max_attempts=4,
                    first_extra_clearance=6.0,
                )
                new_x += center_after[0] - center_before[0]
                new_y += center_after[1] - center_before[1]
                if not separated:
                    new_x, new_y = self.last_safe_pos
            else:
                # Pitfall only: bounce back from current position
                new_x = self.x - dx * 0.5
                new_y = self.y - dy * 0.5

        if pitfall_cells and cell_size:
            pitfall_cell = self._pitfall_cell_at_position(
                new_x,
                new_y,
                cell_size=cell_size,
                pitfall_cells=pitfall_cells,
            )
            if pitfall_cell is not None:
                if self._is_pitfall_fall_position(
                    new_x,
                    new_y,
                    cell_size=cell_size,
                    pitfall_cell=pitfall_cell,
                ):
                    self.pending_pitfall_fall = True
                    safe_x, safe_y = self.last_safe_pos
                    self.pitfall_eject_pos = (int(safe_x), int(safe_y))
                else:
                    bounce_x = self.x - dx * 0.5
                    bounce_y = self.y - dy * 0.5
                    bounce_cell = self._pitfall_cell_at_position(
                        bounce_x,
                        bounce_y,
                        cell_size=cell_size,
                        pitfall_cells=pitfall_cells,
                    )
                    if bounce_cell is None:
                        new_x = bounce_x
                        new_y = bounce_y
                    else:
                        safe_x, safe_y = self.last_safe_pos
                        new_x = safe_x
                        new_y = safe_y

        self.x = new_x
        self.y = new_y
        self.rect.center = (int(self.x), int(self.y))
        if not (
            pitfall_cells
            and cell_size
            and self._pitfall_cell_at_position(
                self.x,
                self.y,
                cell_size=cell_size,
                pitfall_cells=pitfall_cells,
            )
        ):
            self.last_safe_pos = (self.x, self.y)
        self.last_move_dx = dx
        self.last_move_dy = dy
