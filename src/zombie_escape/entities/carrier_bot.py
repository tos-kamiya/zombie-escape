from __future__ import annotations

from typing import TYPE_CHECKING, Iterable

import pygame

try:
    from typing import Self
except ImportError:  # pragma: no cover - Python 3.10 fallback
    from typing_extensions import Self

from ..entities_constants import (
    CARRIER_BOT_COLLISION_RADIUS,
    CARRIER_BOT_HEIGHT,
    CARRIER_BOT_SPEED,
    CARRIER_BOT_WIDTH,
)
from .base_line_bot import BaseLineBot
from .material import Material
from .movement import _circle_wall_collision
from .walls import Wall

if TYPE_CHECKING:  # pragma: no cover - typing-only imports
    from ..models import LevelLayout


class CarrierBot(BaseLineBot):
    """Line-based carrier bot that can pick up and drop one material."""

    def __init__(
        self: Self,
        x: float,
        y: float,
        *,
        axis: str = "x",
        direction_sign: int = 1,
        speed: float = CARRIER_BOT_SPEED,
    ) -> None:
        super().__init__()
        self.image = pygame.Surface((CARRIER_BOT_WIDTH, CARRIER_BOT_HEIGHT), pygame.SRCALPHA)
        self.image.fill((236, 236, 236))
        pygame.draw.rect(self.image, (20, 20, 20), self.image.get_rect(), width=1)
        self.rect = self.image.get_rect(center=(int(x), int(y)))
        self.x = float(self.rect.centerx)
        self.y = float(self.rect.centery)
        self.collision_radius = float(CARRIER_BOT_COLLISION_RADIUS)
        self.shadow_radius = max(1, int(self.collision_radius * 1.2))
        self.shadow_offset_scale = 1.0 / 3.0
        self.speed = max(0.1, float(speed))
        self.axis = "y" if axis == "y" else "x"
        self.direction = self._initial_direction(sign=direction_sign)
        self.carried_material: Material | None = None
        self._recently_dropped_material: Material | None = None

    def _initial_direction(self: Self, *, sign: int) -> tuple[int, int]:
        step = 1 if sign >= 0 else -1
        if self.axis == "y":
            return (0, step)
        return (step, 0)

    def _sync_carried_material(self: Self) -> None:
        material = self.carried_material
        if material is None:
            return
        material.place_at(self.x, self.y)

    def _place_material_here(self: Self) -> None:
        material = self.carried_material
        if material is None:
            return
        material.carried_by = None
        material.place_at(self.x, self.y)
        self.carried_material = None
        self._recently_dropped_material = material

    def _cell_center(self: Self, *, cell: tuple[int, int], cell_size: int) -> tuple[float, float]:
        return (
            float((cell[0] * cell_size) + (cell_size / 2)),
            float((cell[1] * cell_size) + (cell_size / 2)),
        )

    def _can_drop_on_cell(
        self: Self,
        *,
        cell: tuple[int, int],
        cell_size: int,
        layout: "LevelLayout",
        pitfall_cells: set[tuple[int, int]],
        walls: list[Wall],
        materials: Iterable[Material],
    ) -> bool:
        cx, cy = cell
        if cell_size <= 0:
            return False
        if not (0 <= cx < layout.grid_cols and 0 <= cy < layout.grid_rows):
            return False
        if cell in pitfall_cells or cell in layout.outer_wall_cells or cell in layout.outside_cells:
            return False
        drop_x, drop_y = self._cell_center(cell=cell, cell_size=cell_size)
        carried = self.carried_material
        if carried is None:
            return False
        drop_radius = float(carried.collision_radius)
        for wall in walls:
            if _circle_wall_collision((drop_x, drop_y), drop_radius, wall):
                return False
        for material in materials:
            if material is carried or material.carried_by is not None:
                continue
            if int(material.rect.centerx // cell_size) == cx and int(
                material.rect.centery // cell_size
            ) == cy:
                return False
        return True

    def _place_material_on_grid(
        self: Self,
        *,
        cell_size: int,
        layout: "LevelLayout",
        pitfall_cells: set[tuple[int, int]],
        walls: list[Wall],
        materials: Iterable[Material],
    ) -> None:
        material = self.carried_material
        if material is None or cell_size <= 0:
            self._place_material_here()
            return
        base_cell = (int(self.x // cell_size), int(self.y // cell_size))
        backward = (-int(self.direction[0]), -int(self.direction[1]))
        candidates = [
            base_cell,
            (base_cell[0] + backward[0], base_cell[1] + backward[1]),
            (base_cell[0] + backward[0] * 2, base_cell[1] + backward[1] * 2),
        ]
        for cell in candidates:
            if not self._can_drop_on_cell(
                cell=cell,
                cell_size=cell_size,
                layout=layout,
                pitfall_cells=pitfall_cells,
                walls=walls,
                materials=materials,
            ):
                continue
            drop_x, drop_y = self._cell_center(cell=cell, cell_size=cell_size)
            material.carried_by = None
            material.place_at(drop_x, drop_y)
            self.carried_material = None
            self._recently_dropped_material = material
            return
        self._place_material_here()

    def _try_pick_overlapping_material(
        self: Self,
        *,
        materials: Iterable[Material],
    ) -> bool:
        for material in materials:
            if material.carried_by is not None:
                continue
            if material is self._recently_dropped_material:
                continue
            dx = self.x - float(material.rect.centerx)
            dy = self.y - float(material.rect.centery)
            # "Complete overlap": either circle is fully inside the other.
            pickup_range = abs(self.collision_radius - material.collision_radius)
            if dx * dx + dy * dy > pickup_range * pickup_range:
                continue
            material.carried_by = self
            self.carried_material = material
            self._sync_carried_material()
            return True
        return False

    def _is_blocked(
        self: Self,
        *,
        next_x: float,
        next_y: float,
        walls: list[Wall],
        layout: "LevelLayout",
        cell_size: int,
        pitfall_cells: set[tuple[int, int]],
        blockers: Iterable[pygame.sprite.Sprite],
    ) -> bool:
        _, _, hit_wall = self._handle_axis_collision(
            next_x=next_x,
            next_y=next_y,
            current_x=self.x,
            current_y=self.y,
            walls=walls,
            radius=self.collision_radius,
        )
        if hit_wall:
            return True

        if not (
            0 <= next_x < layout.field_rect.width and 0 <= next_y < layout.field_rect.height
        ):
            return True

        if cell_size > 0:
            lead_x = next_x + float(self.direction[0]) * (self.collision_radius + 1.0)
            lead_y = next_y + float(self.direction[1]) * (self.collision_radius + 1.0)
            lead_cell = (int(lead_x // cell_size), int(lead_y // cell_size))
            if lead_cell in pitfall_cells:
                return True
            if lead_cell in layout.outer_wall_cells or lead_cell in layout.outside_cells:
                return True

        for blocker in blockers:
            if blocker is self:
                continue
            if blocker is self.carried_material:
                continue
            if blocker is self._recently_dropped_material:
                continue
            br = getattr(blocker, "collision_radius", None)
            if br is None:
                br = max(blocker.rect.width, blocker.rect.height) / 2
            dx = next_x - float(blocker.rect.centerx)
            dy = next_y - float(blocker.rect.centery)
            hit_range = self.collision_radius + float(br)
            if dx * dx + dy * dy <= hit_range * hit_range:
                return True
        return False

    def update(
        self: Self,
        walls: list[Wall],
        *,
        layout: "LevelLayout",
        cell_size: int,
        pitfall_cells: set[tuple[int, int]],
        materials: Iterable[Material],
        blockers: Iterable[pygame.sprite.Sprite] = (),
    ) -> None:
        recent = self._recently_dropped_material
        if recent is not None:
            if recent.carried_by is not None:
                self._recently_dropped_material = None
            else:
                dx = self.x - float(recent.rect.centerx)
                dy = self.y - float(recent.rect.centery)
                release_dist = (
                    self.collision_radius + recent.collision_radius + max(1.0, self.speed)
                )
                if dx * dx + dy * dy >= release_dist * release_dist:
                    self._recently_dropped_material = None

        # Pick material only when physically overlapping it.
        if self.carried_material is None and self._try_pick_overlapping_material(
            materials=materials
        ):
            self._reverse_direction()
            return

        move_x = float(self.direction[0]) * self.speed
        move_y = float(self.direction[1]) * self.speed
        next_x = self.x + move_x
        next_y = self.y + move_y
        all_blockers = list(blockers)
        if self.carried_material is not None:
            all_blockers.extend([m for m in materials if m is not self.carried_material])

        if self._is_blocked(
            next_x=next_x,
            next_y=next_y,
            walls=walls,
            layout=layout,
            cell_size=cell_size,
            pitfall_cells=pitfall_cells,
            blockers=all_blockers,
        ):
            if self.carried_material is not None:
                self._place_material_on_grid(
                    cell_size=cell_size,
                    layout=layout,
                    pitfall_cells=pitfall_cells,
                    walls=walls,
                    materials=materials,
                )
            self._reverse_direction()
            return

        self.x = next_x
        self.y = next_y
        self.rect.center = (int(self.x), int(self.y))
        self._sync_carried_material()
        if self.carried_material is None and self._try_pick_overlapping_material(
            materials=materials
        ):
            self._reverse_direction()
