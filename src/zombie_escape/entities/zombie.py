from __future__ import annotations

import math
import random
from typing import Iterable, Protocol, TYPE_CHECKING

import pygame

try:
    from typing import Self
except ImportError:  # pragma: no cover - Python 3.10 fallback
    from typing_extensions import Self

from ..entities_constants import (
    FAST_ZOMBIE_BASE_SPEED,
    ZombieKind,
    ZOMBIE_CARBONIZE_DECAY_FRAMES,
    ZOMBIE_DECAY_DURATION_FRAMES,
    ZOMBIE_DECAY_MIN_SPEED_RATIO,
    ZOMBIE_DOG_LONG_AXIS_RATIO,
    ZOMBIE_DOG_SHORT_AXIS_RATIO,
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
    PATROL_BOT_PARALYZE_BLINK_MS,
    PATROL_BOT_PARALYZE_MARKER_COLOR,
)
from ..models import Footprint, LevelLayout
from ..render_assets import (
    angle_bin_from_vector,
    build_zombie_directional_surfaces,
    build_zombie_dog_directional_surfaces,
    draw_lineformer_direction_arm,
    draw_humanoid_hand,
    draw_humanoid_nose,
)
from ..render_constants import ANGLE_BINS, ZOMBIE_NOSE_COLOR, ZOMBIE_OUTLINE_COLOR
from ..rng import get_rng
from ..screen_constants import SCREEN_HEIGHT, SCREEN_WIDTH
from ..world_grid import apply_cell_edge_nudge
from .patrol_paralyze import draw_paralyze_marker
from .movement import _circle_wall_collision
from .zombie_movement import (
    _zombie_lineformer_train_head_movement,
    _zombie_normal_movement,
    _zombie_tracker_movement,
    _zombie_wall_hug_movement,
)
from .walls import Wall
from .zombie_visuals import build_grayscale_image
from .zombie_vitals import ZombieVitals

if TYPE_CHECKING:  # pragma: no cover - typing-only imports
    from .patrol_bot import PatrolBot

RNG = get_rng()

class MovementStrategy(Protocol):
    def __call__(
        self,
        zombie: "Zombie",
        walls: list[Wall],
        cell_size: int,
        layout: LevelLayout,
        player_center: tuple[float, float],
        nearby_zombies: Iterable["Zombie"],
        footprints: list[Footprint],
        *,
        now_ms: int,
    ) -> tuple[float, float]: ...


class Zombie(pygame.sprite.Sprite):
    _next_lineformer_id = 1

    def __init__(
        self: Self,
        x: float,
        y: float,
        *,
        speed: float = ZOMBIE_SPEED,
        kind: ZombieKind = ZombieKind.NORMAL,
        movement_strategy: MovementStrategy | None = None,
        decay_duration_frames: float = ZOMBIE_DECAY_DURATION_FRAMES,
    ) -> None:
        super().__init__()
        self.radius = ZOMBIE_RADIUS
        self.facing_bin = 0
        self.kind = kind
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
        self.vitals = ZombieVitals(
            max_health=100,
            decay_duration_frames=decay_duration_frames,
            decay_min_speed_ratio=ZOMBIE_DECAY_MIN_SPEED_RATIO,
            carbonize_decay_frames=ZOMBIE_CARBONIZE_DECAY_FRAMES,
            on_health_ratio=self._apply_speed_ratio,
            on_kill=self.kill,
            on_carbonize=self._apply_carbonize_visuals,
        )
        if movement_strategy is None:
            if self.kind == ZombieKind.TRACKER:
                movement_strategy = _zombie_tracker_movement
            elif self.kind == ZombieKind.WALL_HUGGER:
                movement_strategy = _zombie_wall_hug_movement
            elif self.kind == ZombieKind.LINEFORMER:
                movement_strategy = _zombie_lineformer_train_head_movement
            else:
                movement_strategy = _zombie_normal_movement
        self.movement_strategy = movement_strategy
        self.lineformer_id = Zombie._next_lineformer_id
        Zombie._next_lineformer_id += 1
        self.lineformer_follow_target_id: int | None = None
        self.lineformer_target_pos: tuple[float, float] | None = None
        self.lineformer_last_target_seen_ms: int | None = None
        self.tracker_target_pos: tuple[float, float] | None = None
        self.tracker_target_time: int | None = None
        self.tracker_last_scan_time = 0
        self.tracker_scan_interval_ms = ZOMBIE_TRACKER_SCAN_INTERVAL_MS
        self.tracker_relock_after_time: int | None = None
        self.tracker_force_wander = False
        if self.kind == ZombieKind.WALL_HUGGER:
            self.wall_hug_side = RNG.choice([-1.0, 1.0])
            self.wall_hug_angle = RNG.uniform(0, math.tau)
        else:
            self.wall_hug_side = 0.0
            self.wall_hug_angle = None
        self.wall_hug_last_wall_time: int | None = None
        self.wall_hug_last_side_has_wall = False
        self.wall_hug_stuck_flag = False
        self.wander_angle = RNG.uniform(0, math.tau)
        self.wander_interval_ms = (
            ZOMBIE_TRACKER_WANDER_INTERVAL_MS
            if self.kind == ZombieKind.TRACKER
            else ZOMBIE_WANDER_INTERVAL_MS
        )
        self.last_wander_change_time = 0
        self.wander_change_interval = max(
            0, self.wander_interval_ms + RNG.randint(-500, 500)
        )
        self.last_move_dx = 0.0
        self.last_move_dy = 0.0
        self.collision_radius = float(self.radius)

    @property
    def max_health(self: Self) -> int:
        return self.vitals.max_health

    @property
    def health(self: Self) -> int:
        return self.vitals.health

    @property
    def decay_duration_frames(self: Self) -> float:
        return self.vitals.decay_duration_frames

    @property
    def carbonized(self: Self) -> bool:
        return self.vitals.carbonized

    @property
    def last_damage_ms(self: Self) -> int | None:
        return self.vitals.last_damage_ms

    @property
    def last_damage_source(self: Self) -> str | None:
        return self.vitals.last_damage_source

    @property
    def patrol_paralyze_until_ms(self: Self) -> int:
        return self.vitals.patrol_paralyze_until_ms

    @property
    def patrol_damage_frame_counter(self: Self) -> int:
        return self.vitals.patrol_damage_frame_counter

    def _apply_speed_ratio(self: Self, ratio: float) -> None:
        self.speed = self.initial_speed * ratio

    def _apply_carbonize_visuals(self: Self) -> None:
        self.image = build_grayscale_image(self.image)

    def _update_mode(
        self: Self, player_center: tuple[float, float], sight_range: float
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
            collides = _circle_wall_collision(
                (next_x, self.y), self.collision_radius, wall
            )
            if collides:
                if wall.alive():
                    wall._take_damage(amount=ZOMBIE_WALL_DAMAGE)
                if wall.alive():
                    final_x = self.x
                    break

        for wall in possible_walls:
            collides = _circle_wall_collision(
                (final_x, next_y), self.collision_radius, wall
            )
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
        zombies: Iterable[pygame.sprite.Sprite],
    ) -> tuple[float, float]:
        """If another zombie is too close, steer directly away from the closest one."""
        orig_move_x, orig_move_y = move_x, move_y
        next_x = self.x + move_x
        next_y = self.y + move_y

        closest: pygame.sprite.Sprite | None = None
        closest_dist_sq = ZOMBIE_SEPARATION_DISTANCE * ZOMBIE_SEPARATION_DISTANCE
        for other in zombies:
            if other is self or not other.alive():
                continue
            
            # Lineformer logic: non-lineformers ignore lineformers
            other_kind = getattr(other, "kind", None)
            if self.kind != ZombieKind.LINEFORMER and other_kind == ZombieKind.LINEFORMER:
                continue
            
            # Attributes check (TrappedZombie has x,y but is a different class)
            ox = getattr(other, "x", None)
            oy = getattr(other, "y", None)
            if ox is None or oy is None:
                continue

            dx = ox - next_x
            dy = oy - next_y
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

        if self.kind == ZombieKind.WALL_HUGGER:
            other_radius = float(getattr(closest, "collision_radius", self.collision_radius))
            bump_dist_sq = (self.collision_radius + other_radius) ** 2
            if closest_dist_sq < bump_dist_sq and RNG.random() < 0.1:
                if self.wall_hug_angle is None:
                    self.wall_hug_angle = self.wander_angle
                self.wall_hug_angle = (self.wall_hug_angle + math.pi) % math.tau
                self.wall_hug_side *= -1.0
                return (
                    math.cos(self.wall_hug_angle) * self.speed,
                    math.sin(self.wall_hug_angle) * self.speed,
                )

        away_dx = next_x - getattr(closest, "x", next_x)
        away_dy = next_y - getattr(closest, "y", next_y)
        away_dist = math.hypot(away_dx, away_dy)
        if away_dist == 0:
            angle = RNG.uniform(0, 2 * math.pi)
            away_dx, away_dy = math.cos(angle), math.sin(angle)
            away_dist = 1

        move_x = (away_dx / away_dist) * self.speed
        move_y = (away_dy / away_dist) * self.speed
        if self.kind == ZombieKind.WALL_HUGGER:
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
        self.vitals.apply_decay()

    def take_damage(
        self: Self,
        amount: int,
        *,
        source: str | None = None,
        now_ms: int,
    ) -> None:
        if amount <= 0 or not self.alive():
            return
        self.vitals.take_damage(amount, source=source, now_ms=now_ms)

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
        needs_overlay = self.kind == ZombieKind.TRACKER or (
            self.kind == ZombieKind.WALL_HUGGER
            and self.wall_hug_side != 0
            and self.wall_hug_last_side_has_wall
        ) or self.kind == ZombieKind.LINEFORMER
        if not needs_overlay:
            self.image = base_surface
            return
        self.image = base_surface.copy()
        angle_rad = (self.facing_bin % ANGLE_BINS) * (math.tau / ANGLE_BINS)
        if self.kind == ZombieKind.TRACKER:
            draw_humanoid_nose(
                self.image,
                radius=self.collision_radius,
                angle_rad=angle_rad,
                color=ZOMBIE_NOSE_COLOR,
            )
        if (
            self.kind == ZombieKind.WALL_HUGGER
            and self.wall_hug_side != 0
            and self.wall_hug_last_side_has_wall
        ):
            side_sign = 1.0 if self.wall_hug_side > 0 else -1.0
            hand_angle = angle_rad + side_sign * (math.pi / 2.0)
            draw_humanoid_hand(
                self.image,
                radius=self.collision_radius,
                angle_rad=hand_angle,
                color=ZOMBIE_NOSE_COLOR,
            )
        if self.kind == ZombieKind.LINEFORMER:
            target_angle = angle_rad
            if self.lineformer_target_pos is not None:
                target_dx = self.lineformer_target_pos[0] - self.x
                target_dy = self.lineformer_target_pos[1] - self.y
                target_angle = math.atan2(target_dy, target_dx)
            draw_lineformer_direction_arm(
                self.image,
                radius=int(self.collision_radius),
                angle_rad=target_angle,
                color=ZOMBIE_OUTLINE_COLOR,
            )

    def _apply_paralyze_overlay(self: Self, now_ms: int) -> None:
        self._apply_render_overlays()
        self.image = self.image.copy()
        center = self.image.get_rect().center
        marker_size = max(6, int(self.radius * 0.8))
        draw_paralyze_marker(
            surface=self.image,
            now_ms=now_ms,
            blink_ms=PATROL_BOT_PARALYZE_BLINK_MS,
            center=center,
            size=marker_size,
            color=PATROL_BOT_PARALYZE_MARKER_COLOR,
            offset=int(self.radius * 0.4),
            width=2,
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
        player_center: tuple[float, float],
        walls: list[Wall],
        nearby_zombies: Iterable[Zombie],
        nearby_patrol_bots: Iterable["PatrolBot"],
        electrified_cells: set[tuple[int, int]] | None = None,
        footprints: list[Footprint] | None = None,
        *,
        cell_size: int,
        layout: LevelLayout,
        now_ms: int,
        drift: tuple[float, float] = (0.0, 0.0),
    ) -> None:
        if self.vitals.carbonized:
            self._apply_decay()
            return
        now = now_ms
        drift_x, drift_y = drift
        level_width = layout.field_rect.width
        level_height = layout.field_rect.height
        self._apply_decay()
        if not self.alive():
            return

        _ = nearby_patrol_bots
        on_electrified_floor = False
        if cell_size > 0 and electrified_cells:
            current_cell = (int(self.x // cell_size), int(self.y // cell_size))
            on_electrified_floor = current_cell in electrified_cells
        if self.vitals.update_patrol_floor_paralyze(
            on_electrified_floor=on_electrified_floor,
            now_ms=now,
            paralyze_duration_ms=PATROL_BOT_PARALYZE_MS,
            damage_interval_frames=PATROL_BOT_ZOMBIE_DAMAGE_INTERVAL_FRAMES,
            damage_amount=PATROL_BOT_ZOMBIE_DAMAGE,
            apply_damage=lambda amount: self.take_damage(
                amount, source="patrol_bot", now_ms=now
            ),
        ):
            self.last_move_dx = 0.0
            self.last_move_dy = 0.0
            self._apply_paralyze_overlay(now)
            return
        dx_player = player_center[0] - self.x
        dy_player = player_center[1] - self.y
        dist_to_player_sq = dx_player * dx_player + dy_player * dy_player
        avoid_radius = max(SCREEN_WIDTH, SCREEN_HEIGHT) * 2
        avoid_radius_sq = avoid_radius * avoid_radius
        move_x, move_y = self.movement_strategy(
            self,
            walls,
            cell_size,
            layout,
            player_center,
            nearby_zombies,
            footprints or [],
            now_ms=now,
        )
        move_x += drift_x
        move_y += drift_y
        if dist_to_player_sq <= avoid_radius_sq or self.kind == ZombieKind.WALL_HUGGER:
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

        final_x = self.x
        final_y = self.y
        if move_x:
            next_x = final_x + move_x
            for wall in possible_walls:
                if _circle_wall_collision(
                    (next_x, final_y), self.collision_radius, wall
                ):
                    if wall.alive():
                        wall._take_damage(amount=ZOMBIE_WALL_DAMAGE)
                    if wall.alive():
                        next_x = final_x
                        break
            final_x = next_x
        if move_y:
            next_y = final_y + move_y
            for wall in possible_walls:
                if _circle_wall_collision(
                    (final_x, next_y), self.collision_radius, wall
                ):
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

    def carbonize(self: Self) -> None:
        self.vitals.carbonize()


class TrappedZombie(pygame.sprite.Sprite):
    """A zombie or dog that has been trapped by a houseplant."""

    def __init__(
        self: Self,
        x: float,
        y: float,
        kind: ZombieKind,
        health: int,
        max_health: int,
        facing_bin: int,
        radius: float,
        collision_radius: float,
        decay_duration_frames: float,
    ) -> None:
        super().__init__()
        self.x = x
        self.y = y
        self.kind = kind
        self.facing_bin = facing_bin
        self.radius = radius
        self.collision_radius = collision_radius
        self.is_trapped = True

        if self.kind == ZombieKind.DOG:
            base_size = ZOMBIE_RADIUS * 2.0
            long_axis = base_size * ZOMBIE_DOG_LONG_AXIS_RATIO
            short_axis = base_size * ZOMBIE_DOG_SHORT_AXIS_RATIO
            self.directional_images = build_zombie_dog_directional_surfaces(
                long_axis, short_axis, is_trapped=True
            )
        else:
            self.directional_images = build_zombie_directional_surfaces(
                int(self.radius), draw_hands=False, is_trapped=True
            )

        self.image = self.directional_images[self.facing_bin]
        self.rect = self.image.get_rect(center=(int(x), int(y)))

        self.vitals = ZombieVitals(
            max_health=max_health,
            decay_duration_frames=decay_duration_frames,
            decay_min_speed_ratio=ZOMBIE_DECAY_MIN_SPEED_RATIO,
            carbonize_decay_frames=ZOMBIE_CARBONIZE_DECAY_FRAMES,
            on_health_ratio=lambda r: None,  # No speed change needed
            on_kill=self.kill,
            on_carbonize=self._apply_carbonize_visuals,
        )
        self.vitals.health = health
        self.frame_counter = 0

    @property
    def health(self: Self) -> int:
        return self.vitals.health

    @property
    def max_health(self: Self) -> int:
        return self.vitals.max_health

    @property
    def carbonized(self: Self) -> bool:
        return self.vitals.carbonized

    def _apply_carbonize_visuals(self: Self) -> None:
        self.image = build_grayscale_image(self.image)

    def take_damage(
        self: Self,
        amount: int,
        *,
        source: str | None = None,
        now_ms: int = 0,
    ) -> None:
        if amount <= 0 or not self.alive():
            return
        self.vitals.take_damage(amount, source=source, now_ms=now_ms)

    def update(self: Self, *args: Any, **kwargs: Any) -> None:
        """Handle decay and jittering visuals."""
        self.vitals.apply_decay()
        if not self.alive():
            return

        # Jitter visuals at 1/4 speed
        if self.frame_counter % 4 == 0:
            ox = random.uniform(-1.0, 1.0)
            oy = random.uniform(-1.0, 1.0)
            self.rect.center = (int(self.x + ox), int(self.y + oy))
        self.frame_counter += 1

    def carbonize(self: Self) -> None:
        self.vitals.carbonize()
