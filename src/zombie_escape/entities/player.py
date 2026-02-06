"""Player entity logic."""

from __future__ import annotations

from typing import TYPE_CHECKING

try:
    from typing import Self
except ImportError:  # pragma: no cover - Python 3.10 fallback
    from typing_extensions import Self

import pygame

if TYPE_CHECKING:
    from ..models import LevelLayout

from ..entities_constants import (
    HUMANOID_WALL_BUMP_FRAMES,
    JUMP_DURATION_MS,
    JUMP_SCALE_MAX,
    PLAYER_JUMP_RANGE,
    PLAYER_RADIUS,
    PLAYER_SPEED,
    PLAYER_WALL_DAMAGE,
)
from ..render_assets import angle_bin_from_vector, build_player_directional_surfaces
from ..render_constants import ANGLE_BINS
from ..world_grid import WallIndex
from .collisions import _spritecollide_walls
from .movement import _can_humanoid_jump, _get_jump_scale
from .movement_helpers import (
    move_axis_with_pitfall,
    set_facing_bin,
    update_directional_image_scale,
)
from .walls import Wall, _is_inner_wall


class Player(pygame.sprite.Sprite):
    def __init__(
        self: Self,
        x: float,
        y: float,
    ) -> None:
        super().__init__()
        self.radius = PLAYER_RADIUS
        self.facing_bin = 0
        self.input_facing_bin = 0
        self.wall_bump_counter = 0
        self.wall_bump_flip = 1
        self.inner_wall_hit = False
        self.inner_wall_cell = None
        self.directional_images = build_player_directional_surfaces(self.radius)
        self.image = self.directional_images[self.facing_bin]
        self.rect = self.image.get_rect(center=(x, y))
        self.speed = PLAYER_SPEED
        self.in_car = False
        self.x = float(self.rect.centerx)
        self.y = float(self.rect.centery)
        self.jump_start_at = 0
        self.jump_duration = JUMP_DURATION_MS
        self.is_jumping = False

    def move(
        self: Self,
        dx: float,
        dy: float,
        walls: pygame.sprite.Group,
        *,
        wall_index: WallIndex | None = None,
        cell_size: int | None = None,
        layout: LevelLayout,
    ) -> None:
        if self.in_car:
            return

        pitfall_cells = layout.pitfall_cells
        walkable_cells = layout.walkable_cells
        level_width = layout.field_rect.width
        level_height = layout.field_rect.height

        now = pygame.time.get_ticks()
        if self.is_jumping:
            elapsed = now - self.jump_start_at
            if elapsed >= self.jump_duration:
                self.is_jumping = False
                self._update_image_scale(1.0)
            else:
                self._update_image_scale(
                    _get_jump_scale(elapsed, self.jump_duration, JUMP_SCALE_MAX)
                )

        # Pre-calculate jump possibility based on actual movement vector
        can_jump_now = (
            not self.is_jumping
            and pitfall_cells
            and cell_size
            and walkable_cells
            and _can_humanoid_jump(
                self.x, self.y, dx, dy, PLAYER_JUMP_RANGE, cell_size, walkable_cells
            )
        )

        inner_wall_hit = False
        inner_wall_cell: tuple[int, int] | None = None

        def _on_player_wall_hit(hit_list: list[Wall]) -> None:
            nonlocal inner_wall_hit, inner_wall_cell
            damage = max(1, PLAYER_WALL_DAMAGE)
            for wall in hit_list:
                if wall.alive():
                    wall._take_damage(amount=damage)
                    if _is_inner_wall(wall):
                        inner_wall_hit = True
                        if inner_wall_cell is None and cell_size:
                            inner_wall_cell = (
                                int(wall.rect.centerx // cell_size),
                                int(wall.rect.centery // cell_size),
                            )

        def _collide_player() -> list[Wall]:
            return _spritecollide_walls(
                self,
                walls,
                wall_index=wall_index,
                cell_size=cell_size,
            )

        move_axis_with_pitfall(
            sprite=self,
            axis="x",
            delta=dx,
            collide=_collide_player,
            cell_size=cell_size,
            pitfall_cells=pitfall_cells,
            can_jump_now=bool(can_jump_now),
            now=now,
            rollback_factor=1.5,
            clamp_range=(0.0, level_width),
            on_wall_hit=_on_player_wall_hit,
        )

        move_axis_with_pitfall(
            sprite=self,
            axis="y",
            delta=dy,
            collide=_collide_player,
            cell_size=cell_size,
            pitfall_cells=pitfall_cells,
            can_jump_now=bool(can_jump_now),
            now=now,
            rollback_factor=1.5,
            clamp_range=(0.0, level_height),
            on_wall_hit=_on_player_wall_hit,
        )

        self.rect.center = (int(self.x), int(self.y))
        self.inner_wall_hit = inner_wall_hit
        self.inner_wall_cell = inner_wall_cell
        self._update_facing_for_bump(inner_wall_hit)

    def _update_image_scale(self: Self, scale: float) -> None:
        """Apply scaling to the current directional image."""
        update_directional_image_scale(self, scale)

    def update_facing_from_input(self: Self, dx: float, dy: float) -> None:
        if self.in_car:
            return
        new_bin = angle_bin_from_vector(dx, dy)
        if new_bin is None:
            return
        self.input_facing_bin = new_bin

    def _update_facing_for_bump(self: Self, inner_wall_hit: bool) -> None:
        if self.in_car:
            return
        if inner_wall_hit:
            self.wall_bump_counter += 1
            if self.wall_bump_counter % HUMANOID_WALL_BUMP_FRAMES == 0:
                self.wall_bump_flip *= -1
            bumped_bin = (self.input_facing_bin + self.wall_bump_flip) % ANGLE_BINS
            self._set_facing_bin(bumped_bin)
            return
        if self.wall_bump_counter:
            self.wall_bump_counter = 0
            self.wall_bump_flip = 1
        self._set_facing_bin(self.input_facing_bin)

    def _set_facing_bin(self: Self, new_bin: int) -> None:
        set_facing_bin(self, new_bin)
