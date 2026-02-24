from __future__ import annotations

import math
from typing import TYPE_CHECKING

import pygame

try:
    from typing import Self
except ImportError:  # pragma: no cover - Python 3.10 fallback
    from typing_extensions import Self

from ..entities_constants import (
    PATROL_BOT_HUMANOID_PAUSE_MS,
    PATROL_BOT_COLLISION_RADIUS,
    PATROL_BOT_DIRECTION_COMMAND_RADIUS,
    PATROL_BOT_DIRECTION_COMMAND_HOLD_MS,
    PATROL_BOT_SPRITE_SIZE,
    PATROL_BOT_SPEED,
    PATROL_BOT_COLLISION_MARGIN,
    PUDDLE_SPEED_FACTOR,
)
from ..render_assets import angle_bin_from_vector, build_patrol_bot_directional_surfaces
from ..render_constants import ANGLE_BINS
from ..rng import get_rng
from ..surface_effects import is_in_puddle_cell
from ..world_grid import apply_cell_edge_nudge
from .base_line_bot import BaseLineBot
from .movement import separate_circle_from_walls
from .walls import Wall

if TYPE_CHECKING:  # pragma: no cover - typing-only imports
    from .spiky_plant import SpikyPlant

RNG = get_rng()


class PatrolBot(BaseLineBot):
    def __init__(self: Self, x: float, y: float) -> None:
        super().__init__()
        self.size = PATROL_BOT_SPRITE_SIZE
        self.radius = float(PATROL_BOT_COLLISION_RADIUS)
        self.facing_bin = 0
        self.collision_radius = float(self.radius)
        self.shadow_radius = max(1, int(self.collision_radius * 1.2))
        self.shadow_offset_scale = 1.0 / 3.0
        self.direction_command_radius = float(PATROL_BOT_DIRECTION_COMMAND_RADIUS)
        assert self.direction_command_radius < self.collision_radius
        self.directional_images_player = build_patrol_bot_directional_surfaces(
            self.size, arrow_scale=1.0
        )
        self.directional_images_auto = build_patrol_bot_directional_surfaces(
            self.size, arrow_scale=2.0 / 3.0
        )
        self.directional_images_waiting = build_patrol_bot_directional_surfaces(
            self.size, arrow_scale=1.0, marker_mode="diamond"
        )
        self.indicator_mode = "auto"
        self.directional_images = self.directional_images_auto
        self.image = self.directional_images[self.facing_bin]
        self.rect = self.image.get_rect(center=(int(x), int(y)))
        self.x = float(self.rect.centerx)
        self.y = float(self.rect.centery)
        self.speed = PATROL_BOT_SPEED
        self.direction = RNG.choice([(1, 0), (-1, 0), (0, 1), (0, -1)])
        self.turn_patterns = [
            [True, False],
            [True, True, False, False],
            [True, True, True, False, False, False],
            [True, True, True, True, False, False, False, False],
            [True, True, True, True, True, False, False, False, False, False],
        ]
        self.turn_pattern_idx = 0
        self.turn_step_idx = 0
        self.last_move_dx = 0.0
        self.last_move_dy = 0.0
        self.pause_until_ms = 0
        self.direction_command_hold_until_ms = 0
        self.awaiting_player_direction_input = False
        self._on_moving_floor_last = False

    def _set_facing_bin(self: Self, new_bin: int) -> None:
        if new_bin == self.facing_bin:
            return
        center = self.rect.center
        self.facing_bin = new_bin
        self.image = self.directional_images[self.facing_bin]
        self.rect = self.image.get_rect(center=center)

    def _set_indicator_mode(self: Self, mode: str) -> None:
        if mode == self.indicator_mode:
            return
        if mode not in ("auto", "player", "waiting"):
            mode = "auto"
        self.indicator_mode = mode
        center = self.rect.center
        if mode == "player":
            self.directional_images = self.directional_images_player
        elif mode == "waiting":
            self.directional_images = self.directional_images_waiting
        else:
            self.directional_images = self.directional_images_auto
        self.image = self.directional_images[self.facing_bin]
        self.rect = self.image.get_rect(center=center)

    def _update_facing_from_movement(self: Self, dx: float, dy: float) -> None:
        new_bin = angle_bin_from_vector(dx, dy)
        if new_bin is None:
            return
        self._set_facing_bin(new_bin)

    def _rotate_direction(self: Self, *, turn_right: bool) -> None:
        dx, dy = self.direction
        if turn_right:
            self.direction = (dy, -dx)
        else:
            self.direction = (-dy, dx)
        self._set_indicator_mode("auto")

    def _set_direction_from_player(
        self: Self, player: pygame.sprite.Sprite, *, now_ms: int
    ) -> None:
        input_bin = getattr(player, "input_facing_bin", None)
        if input_bin is None:
            return
        angle_rad = (input_bin % ANGLE_BINS) * (math.tau / ANGLE_BINS)
        dx = math.cos(angle_rad)
        dy = math.sin(angle_rad)
        if abs(dx) >= abs(dy):
            self.direction = (1, 0) if dx >= 0 else (-1, 0)
        else:
            self.direction = (0, 1) if dy >= 0 else (0, -1)
        self.direction_command_hold_until_ms = (
            now_ms + PATROL_BOT_DIRECTION_COMMAND_HOLD_MS
        )
        self._update_facing_from_movement(*self.direction)
        self._set_indicator_mode("player")

    def update(
        self: Self,
        walls: list[Wall],
        *,
        patrol_bot_group: pygame.sprite.Group | None = None,
        human_group: pygame.sprite.Group | None = None,
        player: pygame.sprite.Sprite | None = None,
        car: pygame.sprite.Sprite | None = None,
        parked_cars: list[pygame.sprite.Sprite] | None = None,
        cell_size: int,
        pitfall_cells: set[tuple[int, int]],
        fire_floor_cells: set[tuple[int, int]] | None = None,
        layout,
        drift: tuple[float, float] = (0.0, 0.0),
        now_ms: int,
        spiky_plants: dict[tuple[int, int], "SpikyPlant"] | None = None,
    ) -> None:
        now = now_ms
        drift_x, drift_y = drift

        if now < self.pause_until_ms:
            if player is not None and getattr(player, "alive", lambda: True)():
                hx, hy = player.rect.center
                hr = getattr(player, "collision_radius", None)
                if hr is None:
                    hr = max(player.rect.width, player.rect.height) / 2
                dx = self.x - hx
                dy = self.y - hy
                hit_range = (
                    self.collision_radius + PATROL_BOT_COLLISION_MARGIN
                ) + float(hr)
                if dx * dx + dy * dy <= hit_range * hit_range:
                    input_active = bool(getattr(player, "input_active", False))
                    if not input_active:
                        self.awaiting_player_direction_input = True
                        self._set_indicator_mode("waiting")
                    elif self.awaiting_player_direction_input:
                        self._set_direction_from_player(player, now_ms=now)
                        self.awaiting_player_direction_input = False
                    else:
                        self._set_indicator_mode("auto")
                else:
                    self.awaiting_player_direction_input = False
                    self._set_indicator_mode("auto")
            else:
                self.awaiting_player_direction_input = False
                self._set_indicator_mode("auto")
            self.last_move_dx = 0.0
            self.last_move_dy = 0.0
            return

        self.awaiting_player_direction_input = False

        cell_x = None
        cell_y = None
        if cell_size > 0:
            cell_x = int(self.rect.centerx // cell_size)
            cell_y = int(self.rect.centery // cell_size)
        on_floor = abs(drift_x) > 0.0 or abs(drift_y) > 0.0
        command_hold_active = now < self.direction_command_hold_until_ms
        forced_floor_dir = on_floor
        if on_floor and not command_hold_active:
            if abs(drift_x) >= abs(drift_y) and abs(drift_x) > 0.0:
                self.direction = (1, 0) if drift_x > 0 else (-1, 0)
            elif abs(drift_y) > 0.0:
                self.direction = (0, 1) if drift_y > 0 else (0, -1)
            self._set_indicator_mode("auto")

        move_x = float(self.direction[0]) * self.speed + drift_x
        move_y = float(self.direction[1]) * self.speed + drift_y

        # Puddle slow-down
        if is_in_puddle_cell(
            self.x,
            self.y,
            cell_size=cell_size,
            puddle_cells=layout.puddle_cells,
        ):
            move_x *= PUDDLE_SPEED_FACTOR
            move_y *= PUDDLE_SPEED_FACTOR

        move_x, move_y = apply_cell_edge_nudge(
            self.x,
            self.y,
            move_x,
            move_y,
            layout=layout,
            cell_size=cell_size,
        )
        self._update_facing_from_movement(
            float(self.direction[0]), float(self.direction[1])
        )
        self.last_move_dx = move_x
        self.last_move_dy = move_y

        next_x = self.x + move_x
        next_y = self.y + move_y
        collision_radius = self.collision_radius + PATROL_BOT_COLLISION_MARGIN
        final_x, final_y, hit_wall = self._handle_axis_collision(
            next_x=next_x,
            next_y=next_y,
            current_x=self.x,
            current_y=self.y,
            walls=walls,
            radius=collision_radius,
        )
        hit_bot = False
        possible_bots = []
        if patrol_bot_group:
            possible_bots = [
                b
                for b in patrol_bot_group
                if b is not self
                and b.alive()
                and abs(b.x - self.x) < 100
                and abs(b.y - self.y) < 100
            ]

        def _bot_collision(check_x: float, check_y: float) -> bool:
            for bot in possible_bots:
                dx = check_x - bot.x
                dy = check_y - bot.y
                hit_range = collision_radius + bot.collision_radius
                if dx * dx + dy * dy <= hit_range * hit_range:
                    return True
            return False

        if _bot_collision(final_x, final_y):
            hit_bot = True
            final_x = self.x
            final_y = self.y
            closest_bot = None
            closest_dist_sq = None
            for bot in possible_bots:
                dx = final_x - bot.x
                dy = final_y - bot.y
                dist_sq = dx * dx + dy * dy
                if closest_dist_sq is None or dist_sq < closest_dist_sq:
                    closest_bot = bot
                    closest_dist_sq = dist_sq

        hit_car = False
        car_candidates: list[pygame.sprite.Sprite] = []
        if car is not None and getattr(car, "alive", lambda: True)():
            car_candidates.append(car)
        if parked_cars:
            car_candidates.extend([c for c in parked_cars if c.alive()])
        for car_candidate in car_candidates:
            cx, cy = car_candidate.rect.center
            cr = getattr(car_candidate, "collision_radius", None)
            if cr is None:
                cr = max(car_candidate.rect.width, car_candidate.rect.height) / 2
            dx = final_x - cx
            dy = final_y - cy
            hit_range = collision_radius + float(cr)
            if dx * dx + dy * dy <= hit_range * hit_range:
                hit_car = True
                final_x = self.x
                final_y = self.y
                break

        hit_spiky_plant = False
        if spiky_plants and cell_size > 0:
            cx_idx = int(final_x // cell_size)
            cy_idx = int(final_y // cell_size)
            for dy in range(-1, 2):
                for dx in range(-1, 2):
                    hp = spiky_plants.get((cx_idx + dx, cy_idx + dy))
                    if hp and hp.alive():
                        h_dx = final_x - hp.x
                        h_dy = final_y - hp.y
                        h_hit_range = collision_radius + hp.collision_radius
                        if h_dx * h_dx + h_dy * h_dy <= h_hit_range * h_hit_range:
                            hit_spiky_plant = True
                            final_x = self.x
                            final_y = self.y
                            break
                if hit_spiky_plant:
                    break

        possible_humans = []
        if human_group:
            possible_humans.extend(
                [
                    h
                    for h in human_group
                    if h.alive()
                    and abs(h.rect.centerx - self.x) < 120
                    and abs(h.rect.centery - self.y) < 120
                ]
            )
        if player is not None and getattr(player, "alive", lambda: True)():
            if (
                abs(player.rect.centerx - self.x) < 120
                and abs(player.rect.centery - self.y) < 120
            ):
                possible_humans.append(player)

        def _humanoid_collision(check_x: float, check_y: float) -> bool:
            for human in possible_humans:
                hx, hy = human.rect.center
                hr = getattr(human, "collision_radius", None)
                if hr is None:
                    hr = max(human.rect.width, human.rect.height) / 2
                dx = check_x - hx
                dy = check_y - hy
                hit_range = collision_radius + float(hr)
                if dx * dx + dy * dy <= hit_range * hit_range:
                    return True
            return False

        hit_pitfall = False
        blocked_hazard_cells = set(pitfall_cells) | set(layout.material_cells)
        if blocked_hazard_cells and cell_size > 0:
            lead_x = next_x + float(self.direction[0]) * collision_radius
            lead_y = next_y + float(self.direction[1]) * collision_radius
            cell_x = int(lead_x // cell_size)
            cell_y = int(lead_y // cell_size)
            if (cell_x, cell_y) in blocked_hazard_cells:
                hit_pitfall = True
                final_x = self.x
                final_y = self.y

        hit_outer = False
        if cell_size > 0:
            cell_x = int(final_x // cell_size)
            cell_y = int(final_y // cell_size)
            if (cell_x, cell_y) in layout.outer_wall_cells or (
                cell_x,
                cell_y,
            ) in layout.outside_cells:
                hit_outer = True
                final_x = self.x
                final_y = self.y
        if not (
            0 <= final_x < layout.field_rect.width
            and 0 <= final_y < layout.field_rect.height
        ):
            hit_outer = True
            final_x = self.x
            final_y = self.y

        if _humanoid_collision(final_x, final_y):
            self.pause_until_ms = now + PATROL_BOT_HUMANOID_PAUSE_MS
        elif (
            hit_wall
            or hit_pitfall
            or hit_bot
            or hit_car
            or hit_outer
            or hit_spiky_plant
        ):
            # Step back slightly to avoid corner lock, then rotate.
            backoff = max(0.5, self.speed * 0.5)
            final_x = self.x - float(self.direction[0]) * backoff
            final_y = self.y - float(self.direction[1]) * backoff
            final_x = min(layout.field_rect.width, max(0.0, final_x))
            final_y = min(layout.field_rect.height, max(0.0, final_y))
            if hit_bot and closest_bot is not None:
                final_x, final_y = self._resolve_circle_overlap(
                    final_x,
                    final_y,
                    collision_radius,
                    other_x=closest_bot.x,
                    other_y=closest_bot.y,
                    other_radius=closest_bot.collision_radius,
                )
            if hit_wall:
                (final_x, final_y), separated = separate_circle_from_walls(
                    (final_x, final_y),
                    collision_radius,
                    walls,
                    scale=1.0,
                    max_attempts=4,
                    first_extra_clearance=0.0,
                )
                final_x = min(layout.field_rect.width, max(0.0, final_x))
                final_y = min(layout.field_rect.height, max(0.0, final_y))
                if not separated:
                    final_x = self.x
                    final_y = self.y

            if not forced_floor_dir:
                # If we hit the outer boundary, reverse direction.
                if hit_outer:
                    self._reverse_direction()
                    self._set_indicator_mode("auto")
                else:
                    pattern = self.turn_patterns[self.turn_pattern_idx]
                    preferred_turn = pattern[self.turn_step_idx]
                    self.turn_step_idx += 1
                    if self.turn_step_idx >= len(pattern):
                        self.turn_step_idx = 0
                        self.turn_pattern_idx = (self.turn_pattern_idx + 1) % len(
                            self.turn_patterns
                        )
                    self._rotate_direction(turn_right=preferred_turn)
                    # Keep the chosen turn even if it would remain blocked.

        level_width = layout.field_rect.width
        level_height = layout.field_rect.height
        if (
            final_x <= 0
            or final_y <= 0
            or final_x >= level_width
            or final_y >= level_height
        ):
            self._reverse_direction()
            self._set_indicator_mode("auto")
            final_x = min(level_width - 1, max(1.0, final_x))
            final_y = min(level_height - 1, max(1.0, final_y))

        self.x = final_x
        self.y = final_y
        self.rect.center = (int(self.x), int(self.y))
        self._on_moving_floor_last = on_floor
