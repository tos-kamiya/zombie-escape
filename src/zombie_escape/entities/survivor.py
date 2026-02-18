from __future__ import annotations

import math
from typing import TYPE_CHECKING, Callable

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
from ..render_constants import ANGLE_BINS, ENTITY_SHADOW_RADIUS_MULT
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
        self._inner_wall_hit = False
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
        self.collision_radius = float(self.radius)
        self.shadow_radius = max(
            1, int(self.collision_radius * ENTITY_SHADOW_RADIUS_MULT)
        )
        self.shadow_offset_scale = 1.0

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
        player_collision_radius: float | None = None,
        drift: tuple[float, float] = (0.0, 0.0),
        now_ms: int,
        speed_factor: float = 1.0,
    ) -> None:
        self.pending_pitfall_fall = False
        pitfall_cells = layout.pitfall_cells
        walkable_cells = layout.walkable_cells
        level_width = layout.field_rect.width
        level_height = layout.field_rect.height

        now = now_ms
        drift_x, drift_y = drift
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
            self._update_buddy_behavior(
                player_pos,
                walls,
                patrol_bot_group=patrol_bot_group,
                wall_index=wall_index,
                cell_size=cell_size,
                layout=layout,
                wall_target_cell=wall_target_cell,
                player_collision_radius=player_collision_radius,
                drift=drift,
                pitfall_cells=pitfall_cells,
                walkable_cells=walkable_cells,
                now=now,
                level_width=level_width,
                level_height=level_height,
                speed_factor=speed_factor,
            )
        else:
            self._update_survivor_behavior(
                player_pos,
                walls,
                patrol_bot_group=patrol_bot_group,
                wall_index=wall_index,
                cell_size=cell_size,
                layout=layout,
                drift=drift,
                pitfall_cells=pitfall_cells,
                walkable_cells=walkable_cells,
                now=now,
                speed_factor=speed_factor,
            )

    def _apply_drift_only(
        self: Self,
        drift: tuple[float, float],
        *,
        walls: pygame.sprite.Group,
        wall_index: WallIndex | None,
        cell_size: int | None,
        layout: "LevelLayout",
        pitfall_cells: set[tuple[int, int]],
        walkable_cells: set[tuple[int, int]],
        now: int,
        speed_factor: float = 1.0,
    ) -> None:
        move_x, move_y = drift[0] * speed_factor, drift[1] * speed_factor
        if move_x == 0.0 and move_y == 0.0:
            self.rect.center = (int(self.x), int(self.y))
            return

        def _collide() -> Wall | None:
            return self._collide_walls(walls, wall_index, cell_size, layout)

        if cell_size is not None:
            move_x, move_y = apply_cell_edge_nudge(
                self.x,
                self.y,
                move_x,
                move_y,
                layout=layout,
                cell_size=cell_size,
            )

        can_jump_now = (
            not self.is_jumping
            and cell_size
            and walkable_cells
            and _can_humanoid_jump(
                self.x,
                self.y,
                move_x,
                move_y,
                SURVIVOR_JUMP_RANGE,
                cell_size,
                pitfall_cells,
                walkable_cells,
            )
        )

        self._move_with_pitfall(
            move_x,
            move_y,
            collide=_collide,
            cell_size=cell_size,
            pitfall_cells=pitfall_cells,
            can_jump_now=bool(can_jump_now),
            now=now,
        )
        self.rect.center = (int(self.x), int(self.y))

    def _update_buddy_behavior(
        self: Self,
        player_pos: tuple[int, int],
        walls: pygame.sprite.Group,
        *,
        patrol_bot_group: pygame.sprite.Group | None,
        wall_index: WallIndex | None,
        cell_size: int | None,
        layout: "LevelLayout",
        wall_target_cell: tuple[int, int] | None,
        player_collision_radius: float | None,
        drift: tuple[float, float],
        pitfall_cells: set[tuple[int, int]],
        walkable_cells: set[tuple[int, int]],
        now: int,
        level_width: int,
        level_height: int,
        speed_factor: float = 1.0,
    ) -> None:
        drift_x, drift_y = drift
        if self.rescued or not self.following:
            self._apply_drift_only(
                drift,
                walls=walls,
                wall_index=wall_index,
                cell_size=cell_size,
                layout=layout,
                pitfall_cells=pitfall_cells,
                walkable_cells=walkable_cells,
                now=now,
            )
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
            self._apply_drift_only(
                drift,
                walls=walls,
                wall_index=wall_index,
                cell_size=cell_size,
                layout=layout,
                pitfall_cells=pitfall_cells,
                walkable_cells=walkable_cells,
                now=now,
            )
            self._update_facing_for_bump(False)
            return

        dist = math.sqrt(dist_sq)
        move_x = (dx / dist) * BUDDY_FOLLOW_SPEED * speed_factor + drift_x
        move_y = (dy / dist) * BUDDY_FOLLOW_SPEED * speed_factor + drift_y

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
        self._inner_wall_hit = False

        can_jump_now = (
            not self.is_jumping
            and cell_size
            and walkable_cells
            and _can_humanoid_jump(
                self.x,
                self.y,
                move_x,
                move_y,
                SURVIVOR_JUMP_RANGE,
                cell_size,
                pitfall_cells,
                walkable_cells,
            )
        )

        def _on_buddy_wall_hit(hit_wall: Wall) -> None:
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
                self._inner_wall_hit = True

        self._move_with_pitfall(
            move_x,
            move_y,
            collide=lambda: self._collide_walls(walls, wall_index, cell_size, layout),
            cell_size=cell_size,
            pitfall_cells=pitfall_cells,
            can_jump_now=bool(can_jump_now),
            now=now,
            rollback_factor=1.5,
            on_wall_hit=_on_buddy_wall_hit,
        )

        player_radius = (
            float(player_collision_radius)
            if player_collision_radius is not None
            else PLAYER_RADIUS
        )
        overlap_radius = (self.collision_radius + player_radius) * 1.05
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
        if self._inner_wall_hit:
            self.wall_bump_hold = HUMANOID_WALL_BUMP_HOLD_FRAMES
        elif self.wall_bump_hold:
            self.wall_bump_hold -= 1
            self._inner_wall_hit = True
        self._update_facing_for_bump(self._inner_wall_hit)
        self._update_overlap_scale(patrol_bot_group)

    def _update_survivor_behavior(
        self: Self,
        player_pos: tuple[int, int],
        walls: pygame.sprite.Group,
        *,
        patrol_bot_group: pygame.sprite.Group | None,
        wall_index: WallIndex | None,
        cell_size: int | None,
        layout: "LevelLayout",
        drift: tuple[float, float],
        pitfall_cells: set[tuple[int, int]],
        walkable_cells: set[tuple[int, int]],
        now: int,
        speed_factor: float = 1.0,
    ) -> None:
        drift_x, drift_y = drift
        dx = player_pos[0] - self.x
        dy = player_pos[1] - self.y
        dist_sq = dx * dx + dy * dy
        if (
            dist_sq <= 0
            or dist_sq > SURVIVOR_APPROACH_RADIUS * SURVIVOR_APPROACH_RADIUS
        ):
            if drift_x != 0.0 or drift_y != 0.0:
                self._apply_drift_only(
                    drift,
                    walls=walls,
                    wall_index=wall_index,
                    cell_size=cell_size,
                    layout=layout,
                    pitfall_cells=pitfall_cells,
                    walkable_cells=walkable_cells,
                    now=now,
                    speed_factor=speed_factor,
                )
                self._update_input_facing(drift_x, drift_y)
                self._update_facing_for_bump(False)
                self._update_overlap_scale(patrol_bot_group)
            return

        dist = math.sqrt(dist_sq)
        move_x = (dx / dist) * SURVIVOR_APPROACH_SPEED * speed_factor + drift_x
        move_y = (dy / dist) * SURVIVOR_APPROACH_SPEED * speed_factor + drift_y

        self._update_input_facing(move_x, move_y)

        can_jump_now = (
            not self.is_jumping
            and cell_size
            and walkable_cells
            and _can_humanoid_jump(
                self.x,
                self.y,
                move_x,
                move_y,
                SURVIVOR_JUMP_RANGE,
                cell_size,
                pitfall_cells,
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

        self._move_with_pitfall(
            move_x,
            move_y,
            collide=lambda: self._collide_walls(walls, wall_index, cell_size, layout),
            cell_size=cell_size,
            pitfall_cells=pitfall_cells,
            can_jump_now=bool(can_jump_now),
            now=now,
        )

        self.rect.center = (int(self.x), int(self.y))
        self._update_facing_for_bump(False)
        self._update_overlap_scale(patrol_bot_group)

    def _collide_walls(
        self: Self,
        walls: pygame.sprite.Group,
        wall_index: WallIndex | None,
        cell_size: int | None,
        layout: "LevelLayout",
    ) -> Wall | None:
        return spritecollideany_walls(
            self,
            walls,
            wall_index=wall_index,
            cell_size=cell_size,
            grid_cols=layout.grid_cols,
            grid_rows=layout.grid_rows,
        )

    def _update_overlap_scale(
        self: Self, patrol_bot_group: pygame.sprite.Group | None
    ) -> None:
        if self.is_jumping:
            return
        overlap_bot = bool(
            patrol_bot_group
            and pygame.sprite.spritecollideany(
                self, patrol_bot_group, collided=collide_circle_custom
            )
        )
        self._update_image_scale(1.08 if overlap_bot else 1.0)

    def _move_with_pitfall(
        self: Self,
        move_x: float,
        move_y: float,
        *,
        collide: Callable[[], Wall | None],
        cell_size: int | None,
        pitfall_cells: set[tuple[int, int]],
        can_jump_now: bool,
        now: int,
        rollback_factor: float = 1.0,
        on_wall_hit: Callable[[Wall], None] | None = None,
    ) -> None:
        move_axis_with_pitfall(
            sprite=self,
            axis="x",
            delta=move_x,
            collide=collide,
            cell_size=cell_size,
            pitfall_cells=pitfall_cells,
            can_jump_now=can_jump_now,
            now=now,
            rollback_factor=rollback_factor,
            on_wall_hit=on_wall_hit,
        )
        move_axis_with_pitfall(
            sprite=self,
            axis="y",
            delta=move_y,
            collide=collide,
            cell_size=cell_size,
            pitfall_cells=pitfall_cells,
            can_jump_now=can_jump_now,
            now=now,
            rollback_factor=rollback_factor,
            on_wall_hit=on_wall_hit,
        )


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
