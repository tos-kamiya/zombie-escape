from __future__ import annotations

import math
from typing import TYPE_CHECKING

import pygame

try:
    from typing import Self
except ImportError:  # pragma: no cover - Python 3.10 fallback
    from typing_extensions import Self

from ..entities_constants import (
    BUDDY_FOLLOW_SPEED,
    BUDDY_RADIUS,
    BUDDY_WALL_DAMAGE,
    BUDDY_WALL_DAMAGE_RANGE,
    HUMANOID_WALL_BUMP_FRAMES,
    HUMANOID_WALL_BUMP_HOLD_FRAMES,
    JUMP_DURATION_MS,
    JUMP_SCALE_MAX,
    PLAYER_RADIUS,
    SURVIVOR_APPROACH_RADIUS,
    SURVIVOR_APPROACH_SPEED,
    SURVIVOR_JUMP_RANGE,
    SURVIVOR_RADIUS,
)
from ..render_assets import angle_bin_from_vector, build_survivor_directional_surfaces
from ..render_constants import ANGLE_BINS
from ..world_grid import WallIndex, apply_cell_edge_nudge
from .collisions import collide_circle_custom, spritecollideany_walls
from .movement import _can_humanoid_jump, _get_jump_scale
from .movement_helpers import (
    move_axis_with_pitfall,
    set_facing_bin,
    update_directional_image_scale,
)
from .walls import Wall, _is_inner_wall

if TYPE_CHECKING:
    from ..models import LevelLayout


class Survivor(pygame.sprite.Sprite):
    """Civilians that gather near the player; optional buddy behavior."""

    def __init__(
        self: Self,
        x: float,
        y: float,
        *,
        is_buddy: bool = False,
    ) -> None:
        super().__init__()
        self.is_buddy = is_buddy
        self.radius = BUDDY_RADIUS if is_buddy else SURVIVOR_RADIUS
        self.facing_bin = 0
        self.input_facing_bin = 0
        self.wall_bump_counter = 0
        self.wall_bump_flip = 1
        self.wall_bump_hold = 0
        self.directional_images = build_survivor_directional_surfaces(
            self.radius,
            is_buddy=is_buddy,
            draw_hands=is_buddy,
        )
        self.image = self.directional_images[self.facing_bin]
        self.rect = self.image.get_rect(center=(int(x), int(y)))
        self.x = float(self.rect.centerx)
        self.y = float(self.rect.centery)
        self.following = False
        self.rescued = False
        self.jump_start_at = 0
        self.jump_duration = JUMP_DURATION_MS
        self.is_jumping = False

    def set_following(self: Self) -> None:
        if self.is_buddy and not self.rescued:
            self.following = True

    def mark_rescued(self: Self) -> None:
        if self.is_buddy:
            self.following = False
            self.rescued = True

    def teleport(self: Self, pos: tuple[int, int]) -> None:
        """Reposition the survivor (used for quiet respawns)."""
        self.x, self.y = float(pos[0]), float(pos[1])
        self.rect.center = (int(self.x), int(self.y))
        if self.is_buddy:
            self.following = False

    def update_behavior(
        self: Self,
        player_pos: tuple[int, int],
        walls: pygame.sprite.Group,
        *,
        patrol_bot_group: pygame.sprite.Group | None = None,
        wall_index: WallIndex | None = None,
        cell_size: int | None = None,
        layout: "LevelLayout",
        wall_target_cell: tuple[int, int] | None = None,
        drift_x: float = 0.0,
        drift_y: float = 0.0,
    ) -> None:
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

        if self.is_buddy:
            if self.rescued or not self.following:
                self.rect.center = (int(self.x), int(self.y))
                return

            target_pos = player_pos
            if wall_target_cell is not None and cell_size is not None:
                target_pos = (
                    wall_target_cell[0] * cell_size + cell_size // 2,
                    wall_target_cell[1] * cell_size + cell_size // 2,
                )

            dx = target_pos[0] - self.x
            dy = target_pos[1] - self.y
            dist_sq = dx * dx + dy * dy
            if dist_sq <= 0:
                self.rect.center = (int(self.x), int(self.y))
                self._update_facing_for_bump(False)
                return

            dist = math.sqrt(dist_sq)
            move_x = (dx / dist) * BUDDY_FOLLOW_SPEED + drift_x
            move_y = (dy / dist) * BUDDY_FOLLOW_SPEED + drift_y

            if cell_size is not None:
                move_x, move_y = apply_cell_edge_nudge(
                    self.x,
                    self.y,
                    move_x,
                    move_y,
                    layout=layout,
                    cell_size=cell_size,
                )

            self._update_input_facing(move_x, move_y)
            inner_wall_hit = False

            can_jump_now = (
                not self.is_jumping
                and pitfall_cells
                and cell_size
                and walkable_cells
                and _can_humanoid_jump(
                    self.x,
                    self.y,
                    move_x,
                    move_y,
                    SURVIVOR_JUMP_RANGE,
                    cell_size,
                    walkable_cells,
                )
            )

            def _on_buddy_wall_hit(hit_wall: Wall) -> None:
                nonlocal inner_wall_hit
                if not hasattr(hit_wall, "_take_damage"):
                    return
                if hit_wall.alive():
                    dx_to_player = player_pos[0] - self.x
                    dy_to_player = player_pos[1] - self.y
                    if dx_to_player * dx_to_player + dy_to_player * dy_to_player <= (
                        BUDDY_WALL_DAMAGE_RANGE * BUDDY_WALL_DAMAGE_RANGE
                    ):
                        hit_wall._take_damage(amount=max(1, BUDDY_WALL_DAMAGE))
                if _is_inner_wall(hit_wall):
                    inner_wall_hit = True

            def _collide_buddy() -> Wall | None:
                hit_wall = spritecollideany_walls(
                    self,
                    walls,
                    wall_index=wall_index,
                    cell_size=cell_size,
                    grid_cols=layout.grid_cols,
                    grid_rows=layout.grid_rows,
                )
                return hit_wall

            move_axis_with_pitfall(
                sprite=self,
                axis="x",
                delta=move_x,
                collide=_collide_buddy,
                cell_size=cell_size,
                pitfall_cells=pitfall_cells,
                can_jump_now=bool(can_jump_now),
                now=now,
                rollback_factor=1.5,
                on_wall_hit=_on_buddy_wall_hit,
            )

            move_axis_with_pitfall(
                sprite=self,
                axis="y",
                delta=move_y,
                collide=_collide_buddy,
                cell_size=cell_size,
                pitfall_cells=pitfall_cells,
                can_jump_now=bool(can_jump_now),
                now=now,
                rollback_factor=1.5,
                on_wall_hit=_on_buddy_wall_hit,
            )

            overlap_radius = (self.radius + PLAYER_RADIUS) * 1.05
            dx_after = target_pos[0] - self.x
            dy_after = target_pos[1] - self.y
            dist_after_sq = dx_after * dx_after + dy_after * dy_after
            if 0 < dist_after_sq < overlap_radius * overlap_radius:
                dist_after = math.sqrt(dist_after_sq)
                push_dist = overlap_radius - dist_after
                self.x -= (dx_after / dist_after) * push_dist
                self.y -= (dy_after / dist_after) * push_dist
                self.rect.center = (int(self.x), int(self.y))

            self.x = min(level_width, max(0, self.x))
            self.y = min(level_height, max(0, self.y))
            self.rect.center = (int(self.x), int(self.y))
            if inner_wall_hit:
                self.wall_bump_hold = HUMANOID_WALL_BUMP_HOLD_FRAMES
            elif self.wall_bump_hold:
                self.wall_bump_hold -= 1
                inner_wall_hit = True
            self._update_facing_for_bump(inner_wall_hit)
            if not self.is_jumping:
                overlap_bot = (
                    bool(
                        patrol_bot_group
                        and pygame.sprite.spritecollideany(
                            self, patrol_bot_group, collided=collide_circle_custom
                        )
                    )
                )
                self._update_image_scale(1.08 if overlap_bot else 1.0)
            return

        dx = player_pos[0] - self.x
        dy = player_pos[1] - self.y
        dist_sq = dx * dx + dy * dy
        if (
            dist_sq <= 0
            or dist_sq > SURVIVOR_APPROACH_RADIUS * SURVIVOR_APPROACH_RADIUS
        ):
            return

        dist = math.sqrt(dist_sq)
        move_x = (dx / dist) * SURVIVOR_APPROACH_SPEED + drift_x
        move_y = (dy / dist) * SURVIVOR_APPROACH_SPEED + drift_y

        self._update_input_facing(move_x, move_y)

        can_jump_now = (
            not self.is_jumping
            and pitfall_cells
            and cell_size
            and walkable_cells
            and _can_humanoid_jump(
                self.x,
                self.y,
                move_x,
                move_y,
                SURVIVOR_JUMP_RANGE,
                cell_size,
                walkable_cells,
            )
        )

        if cell_size is not None:
            move_x, move_y = apply_cell_edge_nudge(
                self.x,
                self.y,
                move_x,
                move_y,
                layout=layout,
                cell_size=cell_size,
            )

        def _collide_survivor() -> Wall | None:
            hit_wall = spritecollideany_walls(
                self,
                walls,
                wall_index=wall_index,
                cell_size=cell_size,
                grid_cols=layout.grid_cols,
                grid_rows=layout.grid_rows,
            )
            return hit_wall

        move_axis_with_pitfall(
            sprite=self,
            axis="x",
            delta=move_x,
            collide=_collide_survivor,
            cell_size=cell_size,
            pitfall_cells=pitfall_cells,
            can_jump_now=bool(can_jump_now),
            now=now,
        )
        move_axis_with_pitfall(
            sprite=self,
            axis="y",
            delta=move_y,
            collide=_collide_survivor,
            cell_size=cell_size,
            pitfall_cells=pitfall_cells,
            can_jump_now=bool(can_jump_now),
            now=now,
        )

        self.rect.center = (int(self.x), int(self.y))
        self._update_facing_for_bump(False)
        if not self.is_jumping:
            overlap_bot = (
                bool(
                    patrol_bot_group
                    and pygame.sprite.spritecollideany(
                        self, patrol_bot_group, collided=collide_circle_custom
                    )
                )
            )
            self._update_image_scale(1.08 if overlap_bot else 1.0)

    def _update_image_scale(self: Self, scale: float) -> None:
        """Apply scaling to the current directional image."""
        update_directional_image_scale(self, scale)

    def _update_input_facing(self: Self, dx: float, dy: float) -> None:
        new_bin = angle_bin_from_vector(dx, dy)
        if new_bin is None:
            return
        self.input_facing_bin = new_bin

    def _update_facing_for_bump(self: Self, inner_wall_hit: bool) -> None:
        if not self.is_buddy:
            self._set_facing_bin(self.input_facing_bin)
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
