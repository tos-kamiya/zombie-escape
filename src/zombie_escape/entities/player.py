"""Player entity logic."""

from __future__ import annotations

from typing import TYPE_CHECKING

try:
    from typing import Self
except ImportError:  # pragma: no cover - Python 3.10 fallback
    from typing_extensions import Self

import pygame

if TYPE_CHECKING:
    from .car import Car
    from ..models import LevelLayout

from ..entities_constants import (
    HUMANOID_WALL_BUMP_FRAMES,
    HUMANOID_WALL_BUMP_HOLD_FRAMES,
    JUMP_DURATION_MS,
    JUMP_SCALE_MAX,
    PLAYER_JUMP_RANGE,
    PLAYER_RADIUS,
    PLAYER_SPEED,
    PLAYER_WALL_DAMAGE,
)
from ..render_assets import (
    angle_bin_from_vector,
    build_player_directional_surfaces,
    build_zombie_directional_surfaces,
)
from ..render_constants import ANGLE_BINS, PLAYER_SHADOW_RADIUS_MULT
from ..world_grid import WallIndex, walls_for_radius
from .collisions import collide_circle_custom
from .movement import _can_humanoid_jump, _get_jump_scale
from .movement_helpers import (
    move_axis_with_pitfall,
    separate_circle_from_blockers,
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
        self.input_active = False
        self.wall_bump_counter = 0
        self.wall_bump_flip = 1
        self.wall_bump_hold = 0
        self.inner_wall_hit = False
        self.inner_wall_cell = None
        self.directional_images = build_player_directional_surfaces(self.radius)
        self.image = self.directional_images[self.facing_bin]
        self.rect = self.image.get_rect(center=(x, y))
        self.speed = PLAYER_SPEED
        self.mounted_vehicle: pygame.sprite.Sprite | None = None
        self._legacy_in_car = False
        self.x = float(self.rect.centerx)
        self.y = float(self.rect.centery)
        self.jump_start_at = 0
        self.jump_duration = JUMP_DURATION_MS
        self.is_jumping = False
        self.collision_radius = float(self.radius)
        self.shadow_radius = max(
            1, int(self.collision_radius * PLAYER_SHADOW_RADIUS_MULT)
        )
        self.shadow_offset_scale = 1.0
        self.is_zombified_visual = False

    @property
    def in_car(self: Self) -> bool:
        mounted_car = self.mounted_car
        return mounted_car is not None or self._legacy_in_car

    @in_car.setter
    def in_car(self: Self, value: bool) -> None:
        bool_value = bool(value)
        self._legacy_in_car = bool_value
        if not bool_value:
            mounted_car = self.mounted_car
            if mounted_car is not None:
                self.mounted_vehicle = None

    @property
    def mounted_car(self: Self) -> "Car | None":
        mounted = self.mounted_vehicle
        if mounted is None:
            return None
        from .car import Car

        if isinstance(mounted, Car):
            return mounted
        return None

    def move(
        self: Self,
        dx: float,
        dy: float,
        walls: pygame.sprite.Group,
        *,
        patrol_bot_group: pygame.sprite.Group | None = None,
        wall_index: WallIndex | None = None,
        cell_size: int | None = None,
        layout: LevelLayout,
        now_ms: int,
    ) -> None:
        if self.mounted_vehicle is not None:
            return
        self.pending_pitfall_fall = False

        pitfall_cells = layout.pitfall_cells
        fire_floor_cells = layout.fire_floor_cells
        material_cells = layout.material_cells
        pitfall_hazard_cells = pitfall_cells | fire_floor_cells
        jumpable_hazard_cells = pitfall_cells | fire_floor_cells
        walkable_cells = layout.walkable_cells
        level_width = layout.field_rect.width
        level_height = layout.field_rect.height
        grid_cols = layout.grid_cols
        grid_rows = layout.grid_rows

        now = now_ms
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
            and cell_size
            and walkable_cells
            and _can_humanoid_jump(
                self.x,
                self.y,
                dx,
                dy,
                PLAYER_JUMP_RANGE,
                cell_size,
                jumpable_hazard_cells,
                walkable_cells,
            )
        )

        inner_wall_hit = False
        inner_wall_cell: tuple[int, int] | None = None

        def _apply_player_wall_damage(hit_walls: list[pygame.sprite.Sprite]) -> None:
            nonlocal inner_wall_hit, inner_wall_cell
            targets = [
                wall
                for wall in hit_walls
                if wall is not None and hasattr(wall, "_take_damage") and wall.alive()
            ]
            if not targets:
                return
            damage = max(1, PLAYER_WALL_DAMAGE)
            unique_targets: list[pygame.sprite.Sprite] = []
            seen: set[int] = set()
            for wall in targets:
                key = id(wall)
                if key in seen:
                    continue
                seen.add(key)
                unique_targets.append(wall)
            split_count = len(unique_targets)
            if split_count <= 0:
                return
            base_damage = damage // split_count
            remainder = damage % split_count
            for idx, wall in enumerate(unique_targets):
                wall_damage = base_damage + (1 if idx < remainder else 0)
                if wall_damage > 0 and wall.alive():
                    wall._take_damage(amount=wall_damage)
            inner_wall = next(
                (wall for wall in unique_targets if _is_inner_wall(wall)), None
            )
            if inner_wall is not None:
                inner_wall_hit = True
                if inner_wall_cell is None and cell_size:
                    inner_wall_cell = (
                        int(inner_wall.rect.centerx // cell_size),
                        int(inner_wall.rect.centery // cell_size),
                    )

        def _collide_player() -> Wall | None:
            return None

        move_axis_with_pitfall(
            sprite=self,
            axis="x",
            delta=dx,
            collide=_collide_player,
            cell_size=cell_size,
            pitfall_cells=pitfall_hazard_cells,
            blocked_cells=None,
            pending_fall_cells=pitfall_cells,
            can_jump_now=bool(can_jump_now),
            now=now,
            rollback_factor=1.0,
            clamp_range=(0.0, level_width),
        )

        move_axis_with_pitfall(
            sprite=self,
            axis="y",
            delta=dy,
            collide=_collide_player,
            cell_size=cell_size,
            pitfall_cells=pitfall_hazard_cells,
            blocked_cells=None,
            pending_fall_cells=pitfall_cells,
            can_jump_now=bool(can_jump_now),
            now=now,
            rollback_factor=1.0,
            clamp_range=(0.0, level_height),
        )

        wall_candidates: list[pygame.sprite.Sprite]
        if wall_index is None:
            wall_candidates = [wall for wall in walls if wall.alive()]
        elif cell_size is None:
            wall_candidates = []
        else:
            wall_candidates = list(
                walls_for_radius(
                    wall_index,
                    (self.x, self.y),
                    float(getattr(self, "collision_radius", self.radius)),
                    cell_size=cell_size,
                    grid_cols=grid_cols,
                    grid_rows=grid_rows,
                )
            )
        separation = separate_circle_from_blockers(
            x=self.x,
            y=self.y,
            radius=float(getattr(self, "collision_radius", self.radius)),
            walls=wall_candidates,
            cell_size=int(cell_size or 0),
            blocked_cells=material_cells,
            grid_cols=grid_cols,
            grid_rows=grid_rows,
            max_attempts=5,
        )
        self.x = separation.x
        self.y = separation.y
        if separation.hit_walls:
            _apply_player_wall_damage(separation.hit_walls)

        self.rect.center = (int(self.x), int(self.y))
        if inner_wall_hit:
            self.wall_bump_hold = HUMANOID_WALL_BUMP_HOLD_FRAMES
        elif self.wall_bump_hold:
            self.wall_bump_hold -= 1
            inner_wall_hit = True

        self.inner_wall_hit = inner_wall_hit
        self.inner_wall_cell = inner_wall_cell
        self._update_facing_for_bump(inner_wall_hit)
        if not self.is_jumping:
            overlap_bot = bool(
                patrol_bot_group
                and pygame.sprite.spritecollideany(
                    self, patrol_bot_group, collided=collide_circle_custom
                )
            )
            self._update_image_scale(1.08 if overlap_bot else 1.0)

    def _update_image_scale(self: Self, scale: float) -> None:
        """Apply scaling to the current directional image."""
        update_directional_image_scale(self, scale)

    def update_facing_from_input(self: Self, dx: float, dy: float) -> None:
        if self.mounted_vehicle is not None:
            return
        new_bin = angle_bin_from_vector(dx, dy)
        if new_bin is None:
            self.input_active = False
            return
        self.input_active = True
        self.input_facing_bin = new_bin

    def _update_facing_for_bump(self: Self, inner_wall_hit: bool) -> None:
        if self.mounted_vehicle is not None:
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

    def set_zombified_visual(self: Self) -> None:
        """Swap visuals to a simple zombie-style body (no hands)."""
        if self.is_zombified_visual:
            return
        center = self.rect.center
        self.directional_images = build_zombie_directional_surfaces(
            self.radius,
            draw_hands=False,
        )
        self.image = self.directional_images[self.facing_bin]
        self.rect = self.image.get_rect(center=center)
        self.x = float(self.rect.centerx)
        self.y = float(self.rect.centery)
        self.is_zombified_visual = True
