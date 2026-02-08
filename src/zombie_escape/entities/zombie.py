from __future__ import annotations

import math
from typing import Callable, Iterable, TYPE_CHECKING

import pygame

try:
    from typing import Self
except ImportError:  # pragma: no cover - Python 3.10 fallback
    from typing_extensions import Self

from ..entities_constants import (
    FAST_ZOMBIE_BASE_SPEED,
    ZOMBIE_CARBONIZE_DECAY_FRAMES,
    ZOMBIE_DECAY_DURATION_FRAMES,
    ZOMBIE_DECAY_MIN_SPEED_RATIO,
    ZOMBIE_RADIUS,
    ZOMBIE_SEPARATION_DISTANCE,
    ZOMBIE_SPEED,
    ZOMBIE_TRACKER_SCAN_INTERVAL_MS,
    ZOMBIE_TRACKER_WANDER_INTERVAL_MS,
    ZOMBIE_WALL_DAMAGE,
    ZOMBIE_WANDER_INTERVAL_MS,
    PATROL_BOT_ZOMBIE_DAMAGE,
    PATROL_BOT_ZOMBIE_DAMAGE_INTERVAL_FRAMES,
    PATROL_BOT_PARALYZE_MS,
)
from ..models import Footprint, LevelLayout
from ..render_assets import (
    angle_bin_from_vector,
    build_zombie_directional_surfaces,
    draw_humanoid_hand,
    draw_humanoid_nose,
)
from ..render_constants import ANGLE_BINS, ZOMBIE_NOSE_COLOR
from ..rng import get_rng
from ..screen_constants import SCREEN_HEIGHT, SCREEN_WIDTH
from ..world_grid import apply_cell_edge_nudge
from .movement import (
    _circle_wall_collision,
    _zombie_normal_movement,
    _zombie_tracker_movement,
    _zombie_wall_hug_movement,
)
from .walls import Wall

if TYPE_CHECKING:  # pragma: no cover - typing-only imports
    from .patrol_bot import PatrolBot

RNG = get_rng()

MovementStrategy = Callable[
    [
        "Zombie",
        tuple[int, int],
        list[Wall],
        Iterable["Zombie"],
        list[Footprint],
        int,
        LevelLayout,
    ],
    tuple[float, float],
]


class Zombie(pygame.sprite.Sprite):
    def __init__(
        self: Self,
        x: float,
        y: float,
        *,
        speed: float = ZOMBIE_SPEED,
        tracker: bool = False,
        wall_hugging: bool = False,
        movement_strategy: MovementStrategy | None = None,
        decay_duration_frames: float = ZOMBIE_DECAY_DURATION_FRAMES,
    ) -> None:
        super().__init__()
        self.radius = ZOMBIE_RADIUS
        self.facing_bin = 0
        self.tracker = tracker
        self.wall_hugging = wall_hugging
        self.carbonized = False
        self.directional_images = build_zombie_directional_surfaces(
            self.radius,
            draw_hands=False,
        )
        self.image = self.directional_images[self.facing_bin]
        self.rect = self.image.get_rect(center=(x, y))
        jitter_base = FAST_ZOMBIE_BASE_SPEED if speed > ZOMBIE_SPEED else ZOMBIE_SPEED
        jitter = jitter_base * 0.2
        base_speed = speed + RNG.uniform(-jitter, jitter)
        self.initial_speed = base_speed
        self.speed = base_speed
        self.x = float(self.rect.centerx)
        self.y = float(self.rect.centery)
        self.was_in_sight = False
        self.max_health = 100
        self.health = self.max_health
        self.decay_carry = 0.0
        self.decay_duration_frames = decay_duration_frames
        self.last_damage_ms: int | None = None
        self.last_damage_source: str | None = None
        if movement_strategy is None:
            if tracker:
                movement_strategy = _zombie_tracker_movement
            elif wall_hugging:
                movement_strategy = _zombie_wall_hug_movement
            else:
                movement_strategy = _zombie_normal_movement
        self.movement_strategy = movement_strategy
        self.tracker_target_pos: tuple[float, float] | None = None
        self.tracker_target_time: int | None = None
        self.tracker_last_scan_time = 0
        self.tracker_scan_interval_ms = ZOMBIE_TRACKER_SCAN_INTERVAL_MS
        self.tracker_relock_after_time: int | None = None
        self.tracker_force_wander = False
        self.wall_hug_side = RNG.choice([-1.0, 1.0]) if wall_hugging else 0.0
        self.wall_hug_angle = RNG.uniform(0, math.tau) if wall_hugging else None
        self.wall_hug_last_wall_time: int | None = None
        self.wall_hug_last_side_has_wall = False
        self.wall_hug_stuck_flag = False
        self.wander_angle = RNG.uniform(0, math.tau)
        self.wander_interval_ms = (
            ZOMBIE_TRACKER_WANDER_INTERVAL_MS if tracker else ZOMBIE_WANDER_INTERVAL_MS
        )
        self.last_wander_change_time = pygame.time.get_ticks()
        self.wander_change_interval = max(
            0, self.wander_interval_ms + RNG.randint(-500, 500)
        )
        self.last_move_dx = 0.0
        self.last_move_dy = 0.0
        self.patrol_damage_frame_counter = 0
        self.patrol_paralyze_until_ms = 0

    def _update_mode(
        self: Self, player_center: tuple[int, int], sight_range: float
    ) -> bool:
        dx_target = player_center[0] - self.x
        dy_target = player_center[1] - self.y
        dist_to_player_sq = dx_target * dx_target + dy_target * dy_target
        is_in_sight = dist_to_player_sq <= sight_range * sight_range
        self.was_in_sight = is_in_sight
        return is_in_sight

    def _handle_wall_collision(
        self: Self, next_x: float, next_y: float, walls: list[Wall]
    ) -> tuple[float, float]:
        final_x, final_y = next_x, next_y

        possible_walls = [
            w
            for w in walls
            if abs(w.rect.centerx - self.x) < 100 and abs(w.rect.centery - self.y) < 100
        ]

        for wall in possible_walls:
            collides = _circle_wall_collision((next_x, self.y), self.radius, wall)
            if collides:
                if wall.alive():
                    wall._take_damage(amount=ZOMBIE_WALL_DAMAGE)
                if wall.alive():
                    final_x = self.x
                    break

        for wall in possible_walls:
            collides = _circle_wall_collision((final_x, next_y), self.radius, wall)
            if collides:
                if wall.alive():
                    wall._take_damage(amount=ZOMBIE_WALL_DAMAGE)
                if wall.alive():
                    final_y = self.y
                    break

        return final_x, final_y

    def _avoid_other_zombies(
        self: Self,
        move_x: float,
        move_y: float,
        zombies: Iterable[Zombie],
    ) -> tuple[float, float]:
        """If another zombie is too close, steer directly away from the closest one."""
        orig_move_x, orig_move_y = move_x, move_y
        next_x = self.x + move_x
        next_y = self.y + move_y

        closest: Zombie | None = None
        closest_dist_sq = ZOMBIE_SEPARATION_DISTANCE * ZOMBIE_SEPARATION_DISTANCE
        for other in zombies:
            if other is self or not other.alive():
                continue
            dx = other.x - next_x
            dy = other.y - next_y
            if (
                abs(dx) > ZOMBIE_SEPARATION_DISTANCE
                or abs(dy) > ZOMBIE_SEPARATION_DISTANCE
            ):
                continue
            dist_sq = dx * dx + dy * dy
            if dist_sq < closest_dist_sq:
                closest = other
                closest_dist_sq = dist_sq

        if closest is None:
            return move_x, move_y

        if self.wall_hugging:
            other_radius = float(closest.radius)
            bump_dist_sq = (self.radius + other_radius) ** 2
            if closest_dist_sq < bump_dist_sq and RNG.random() < 0.1:
                if self.wall_hug_angle is None:
                    self.wall_hug_angle = self.wander_angle
                self.wall_hug_angle = (self.wall_hug_angle + math.pi) % math.tau
                self.wall_hug_side *= -1.0
                return (
                    math.cos(self.wall_hug_angle) * self.speed,
                    math.sin(self.wall_hug_angle) * self.speed,
                )

        away_dx = next_x - closest.x
        away_dy = next_y - closest.y
        away_dist = math.hypot(away_dx, away_dy)
        if away_dist == 0:
            angle = RNG.uniform(0, 2 * math.pi)
            away_dx, away_dy = math.cos(angle), math.sin(angle)
            away_dist = 1

        move_x = (away_dx / away_dist) * self.speed
        move_y = (away_dy / away_dist) * self.speed
        if self.wall_hugging:
            if orig_move_x or orig_move_y:
                orig_angle = math.atan2(orig_move_y, orig_move_x)
                new_angle = math.atan2(move_y, move_x)
                diff = (new_angle - orig_angle + math.pi) % math.tau - math.pi
                if abs(diff) > math.pi / 2.0:
                    clamped = math.copysign(math.pi / 2.0, diff)
                    new_angle = orig_angle + clamped
                    move_x = math.cos(new_angle) * self.speed
                    move_y = math.sin(new_angle) * self.speed
        return move_x, move_y

    def _apply_decay(self: Self) -> None:
        """Reduce zombie health over time and despawn when depleted."""
        if self.decay_duration_frames <= 0:
            return
        self.decay_carry += self.max_health / self.decay_duration_frames
        if self.decay_carry >= 1.0:
            decay_amount = int(self.decay_carry)
            self.decay_carry -= decay_amount
            self.health -= decay_amount
        health_ratio = 0.0 if self.max_health <= 0 else self.health / self.max_health
        health_ratio = max(0.0, min(1.0, health_ratio))
        speed_ratio = ZOMBIE_DECAY_MIN_SPEED_RATIO + (
            1.0 - ZOMBIE_DECAY_MIN_SPEED_RATIO
        ) * health_ratio
        self.speed = self.initial_speed * speed_ratio
        if self.health <= 0:
            self.kill()

    def take_damage(self: Self, amount: int, *, source: str | None = None) -> None:
        if amount <= 0 or not self.alive():
            return
        self.last_damage_ms = pygame.time.get_ticks()
        self.last_damage_source = source
        self.health -= amount
        if self.health <= 0:
            self.kill()

    def _set_facing_bin(self: Self, new_bin: int) -> None:
        if new_bin == self.facing_bin:
            return
        center = self.rect.center
        self.facing_bin = new_bin
        self.image = self.directional_images[self.facing_bin]
        self.rect = self.image.get_rect(center=center)

    def _update_facing_from_movement(self: Self, dx: float, dy: float) -> None:
        new_bin = angle_bin_from_vector(dx, dy)
        if new_bin is None:
            return
        self._set_facing_bin(new_bin)

    def _apply_render_overlays(self: Self) -> None:
        base_surface = self.directional_images[self.facing_bin]
        needs_overlay = self.tracker or (
            self.wall_hugging
            and self.wall_hug_side != 0
            and self.wall_hug_last_side_has_wall
        )
        if not needs_overlay:
            self.image = base_surface
            return
        self.image = base_surface.copy()
        angle_rad = (self.facing_bin % ANGLE_BINS) * (math.tau / ANGLE_BINS)
        if self.tracker:
            draw_humanoid_nose(
                self.image,
                radius=self.radius,
                angle_rad=angle_rad,
                color=ZOMBIE_NOSE_COLOR,
            )
        if (
            self.wall_hugging
            and self.wall_hug_side != 0
            and self.wall_hug_last_side_has_wall
        ):
            side_sign = 1.0 if self.wall_hug_side > 0 else -1.0
            hand_angle = angle_rad + side_sign * (math.pi / 2.0)
            draw_humanoid_hand(
                self.image,
                radius=self.radius,
                angle_rad=hand_angle,
                color=ZOMBIE_NOSE_COLOR,
            )

    def _avoid_pitfalls(
        self: Self,
        pitfall_cells: set[tuple[int, int]],
        cell_size: int,
    ) -> tuple[float, float]:
        if cell_size <= 0 or not pitfall_cells:
            return 0.0, 0.0
        cell_x = int(self.x // cell_size)
        cell_y = int(self.y // cell_size)
        search_cells = 1
        avoid_radius = cell_size * 1.25
        max_strength = self.speed * 0.5
        push_x = 0.0
        push_y = 0.0
        for cy in range(cell_y - search_cells, cell_y + search_cells + 1):
            for cx in range(cell_x - search_cells, cell_x + search_cells + 1):
                if (cx, cy) not in pitfall_cells:
                    continue
                pit_x = (cx + 0.5) * cell_size
                pit_y = (cy + 0.5) * cell_size
                dx = self.x - pit_x
                dy = self.y - pit_y
                dist_sq = dx * dx + dy * dy
                if dist_sq <= 0:
                    continue
                dist = math.sqrt(dist_sq)
                if dist >= avoid_radius:
                    continue
                strength = (1.0 - dist / avoid_radius) * max_strength
                push_x += (dx / dist) * strength
                push_y += (dy / dist) * strength
        return push_x, push_y

    def update(
        self: Self,
        player_center: tuple[int, int],
        walls: list[Wall],
        nearby_zombies: Iterable[Zombie],
        nearby_patrol_bots: Iterable["PatrolBot"],
        footprints: list[Footprint] | None = None,
        *,
        cell_size: int,
        layout: LevelLayout,
    ) -> None:
        if self.carbonized:
            self._apply_decay()
            return
        now = pygame.time.get_ticks()
        level_width = layout.field_rect.width
        level_height = layout.field_rect.height
        self._apply_decay()
        if not self.alive():
            return
        bot_hit_now = False
        possible_bots = [
            b
            for b in nearby_patrol_bots
            if abs(b.x - self.x) < 100 and abs(b.y - self.y) < 100
        ]
        for bot in possible_bots:
            dx = self.x - bot.x
            dy = self.y - bot.y
            hit_range = self.radius + bot.radius
            if dx * dx + dy * dy <= hit_range * hit_range:
                bot_hit_now = True
                break
        if bot_hit_now:
            self.patrol_damage_frame_counter = (
                self.patrol_damage_frame_counter + 1
            ) % PATROL_BOT_ZOMBIE_DAMAGE_INTERVAL_FRAMES
            if self.patrol_damage_frame_counter == 0:
                self.take_damage(PATROL_BOT_ZOMBIE_DAMAGE, source="patrol_bot")
            self.patrol_paralyze_until_ms = max(
                self.patrol_paralyze_until_ms,
                now + PATROL_BOT_PARALYZE_MS,
            )
        if now < self.patrol_paralyze_until_ms:
            self.last_move_dx = 0.0
            self.last_move_dy = 0.0
            return
        dx_player = player_center[0] - self.x
        dy_player = player_center[1] - self.y
        dist_to_player_sq = dx_player * dx_player + dy_player * dy_player
        avoid_radius = max(SCREEN_WIDTH, SCREEN_HEIGHT) * 2
        avoid_radius_sq = avoid_radius * avoid_radius
        move_x, move_y = self.movement_strategy(
            self,
            player_center,
            walls,
            nearby_zombies,
            footprints or [],
            cell_size,
            layout,
        )
        if dist_to_player_sq <= avoid_radius_sq or self.wall_hugging:
            move_x, move_y = self._avoid_other_zombies(move_x, move_y, nearby_zombies)
        move_x, move_y = apply_cell_edge_nudge(
            self.x,
            self.y,
            move_x,
            move_y,
            layout=layout,
            cell_size=cell_size,
        )
        self._update_facing_from_movement(move_x, move_y)
        self._apply_render_overlays()
        self.last_move_dx = move_x
        self.last_move_dy = move_y
        possible_walls = [
            w
            for w in walls
            if abs(w.rect.centerx - self.x) < 100 and abs(w.rect.centery - self.y) < 100
        ]
        bot_hit = False

        def _bot_collision(check_x: float, check_y: float) -> bool:
            nonlocal bot_hit
            for bot in possible_bots:
                dx = check_x - bot.x
                dy = check_y - bot.y
                hit_range = self.radius + bot.radius
                if dx * dx + dy * dy <= hit_range * hit_range:
                    bot_hit = True
                    return True
            return False

        final_x = self.x
        final_y = self.y
        if move_x:
            next_x = final_x + move_x
            if _bot_collision(next_x, final_y):
                next_x = final_x
            for wall in possible_walls:
                if _circle_wall_collision((next_x, final_y), self.radius, wall):
                    if wall.alive():
                        wall._take_damage(amount=ZOMBIE_WALL_DAMAGE)
                    if wall.alive():
                        next_x = final_x
                        break
            final_x = next_x
        if move_y:
            next_y = final_y + move_y
            if _bot_collision(final_x, next_y):
                next_y = final_y
            for wall in possible_walls:
                if _circle_wall_collision((final_x, next_y), self.radius, wall):
                    if wall.alive():
                        wall._take_damage(amount=ZOMBIE_WALL_DAMAGE)
                    if wall.alive():
                        next_y = final_y
                        break
            final_y = next_y

        if not (0 <= final_x < level_width and 0 <= final_y < level_height):
            self.kill()
            return

        self.x = final_x
        self.y = final_y
        self.rect.center = (int(self.x), int(self.y))
        if bot_hit:
            self.patrol_damage_frame_counter = (
                self.patrol_damage_frame_counter + 1
            ) % PATROL_BOT_ZOMBIE_DAMAGE_INTERVAL_FRAMES
            if self.patrol_damage_frame_counter == 0:
                self.take_damage(PATROL_BOT_ZOMBIE_DAMAGE, source="patrol_bot")
            self.patrol_paralyze_until_ms = max(
                self.patrol_paralyze_until_ms,
                now + PATROL_BOT_PARALYZE_MS,
            )

    def carbonize(self: Self) -> None:
        if self.carbonized:
            return
        self.carbonized = True
        self.speed = 0
        if self.decay_duration_frames > 0:
            remaining_ratio = min(
                1.0, ZOMBIE_CARBONIZE_DECAY_FRAMES / self.decay_duration_frames
            )
            remaining_health = max(1, int(round(self.max_health * remaining_ratio)))
            self.health = min(self.health, remaining_health)
            self.decay_carry = 0.0
        self.image = self.directional_images[self.facing_bin].copy()
        self.image.fill((0, 0, 0, 0))
        color = (80, 80, 80)
        center = self.image.get_rect().center
        pygame.draw.circle(self.image, color, center, self.radius)
        pygame.draw.circle(
            self.image,
            (30, 30, 30),
            center,
            self.radius,
            width=1,
        )
