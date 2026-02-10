from __future__ import annotations

import math
from enum import Enum

import pygame

try:
    from typing import Self
except ImportError:  # pragma: no cover - Python 3.10 fallback
    from typing_extensions import Self

from ..entities_constants import (
    ZombieKind,
    ZOMBIE_DOG_ASSAULT_SPEED,
    ZOMBIE_DOG_BITE_DAMAGE,
    ZOMBIE_DOG_BITE_INTERVAL_FRAMES,
    ZOMBIE_CARBONIZE_DECAY_FRAMES,
    ZOMBIE_DOG_DECAY_DURATION_FRAMES,
    ZOMBIE_DOG_DECAY_MIN_SPEED_RATIO,
    ZOMBIE_DOG_HEAD_RADIUS_RATIO,
    ZOMBIE_DOG_LONG_AXIS_RATIO,
    ZOMBIE_DOG_PATROL_SPEED,
    ZOMBIE_DOG_PACK_CHASE_RANGE,
    ZOMBIE_DOG_SHORT_AXIS_RATIO,
    ZOMBIE_DOG_SIGHT_RANGE,
    ZOMBIE_DOG_WANDER_INTERVAL_MS,
    PATROL_BOT_ZOMBIE_DAMAGE,
    PATROL_BOT_ZOMBIE_DAMAGE_INTERVAL_FRAMES,
    PATROL_BOT_PARALYZE_MS,
    PATROL_BOT_PARALYZE_BLINK_MS,
    PATROL_BOT_PARALYZE_MARKER_COLOR,
    ZOMBIE_RADIUS,
    ZOMBIE_SEPARATION_DISTANCE,
)
from ..rng import get_rng
from ..render_assets import (
    angle_bin_from_vector,
    build_zombie_dog_directional_surfaces,
)
from ..render_constants import ANGLE_BINS
from ..screen_constants import FPS
from ..world_grid import apply_cell_edge_nudge
from .patrol_paralyze import draw_paralyze_marker
from .zombie import Zombie
from .movement import _circle_wall_collision
from .walls import Wall
from .zombie_visuals import build_grayscale_image
from .zombie_vitals import ZombieVitals


RNG = get_rng()


class ZombieDogMode(Enum):
    WANDER = "wander"
    CHARGE = "charge"
    CHASE = "chase"


class ZombieDog(pygame.sprite.Sprite):
    def __init__(self: Self, x: float, y: float) -> None:
        super().__init__()
        base_size = ZOMBIE_RADIUS * 2.0
        self.long_axis = base_size * ZOMBIE_DOG_LONG_AXIS_RATIO
        self.short_axis = base_size * ZOMBIE_DOG_SHORT_AXIS_RATIO
        self.radius = self.short_axis * 0.5
        self.head_radius = self.short_axis * ZOMBIE_DOG_HEAD_RADIUS_RATIO
        self.speed_patrol = ZOMBIE_DOG_PATROL_SPEED
        self.speed_assault = ZOMBIE_DOG_ASSAULT_SPEED
        self.initial_speed_patrol = self.speed_patrol
        self.initial_speed_assault = self.speed_assault
        self.sight_range = ZOMBIE_DOG_SIGHT_RANGE
        self.mode = ZombieDogMode.WANDER
        self.charge_direction = (0.0, 0.0)
        self.wander_angle = RNG.uniform(0.0, math.tau)
        self.wander_change_time = pygame.time.get_ticks()
        self.kind = ZombieKind.DOG
        self.facing_bin = 0
        self.directional_images = build_zombie_dog_directional_surfaces(
            self.long_axis,
            self.short_axis,
        )
        self.image = self.directional_images[self.facing_bin]
        self.rect = self.image.get_rect(center=(x, y))
        self.x = float(self.rect.centerx)
        self.y = float(self.rect.centery)
        self.last_move_dx = 0.0
        self.last_move_dy = 0.0
        self.bite_frame_counter = 0
        self.vitals = ZombieVitals(
            max_health=100,
            decay_duration_frames=ZOMBIE_DOG_DECAY_DURATION_FRAMES,
            decay_min_speed_ratio=ZOMBIE_DOG_DECAY_MIN_SPEED_RATIO,
            carbonize_decay_frames=ZOMBIE_CARBONIZE_DECAY_FRAMES,
            on_health_ratio=self._apply_speed_ratio,
            on_kill=self.kill,
            on_carbonize=self._apply_carbonize_visuals,
        )

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
        self.speed_patrol = self.initial_speed_patrol * ratio
        self.speed_assault = self.initial_speed_assault * ratio

    def _apply_carbonize_visuals(self: Self) -> None:
        self.image = build_grayscale_image(self.image)

    def get_collision_circle(self: Self) -> tuple[tuple[int, int], float]:
        head_x, head_y = self._head_center()
        return (int(round(head_x)), int(round(head_y))), float(self.head_radius)

    def _head_center(self: Self) -> tuple[float, float]:
        angle = (self.facing_bin % ANGLE_BINS) * (math.tau / ANGLE_BINS)
        offset = self.long_axis * 0.5
        return (
            self.x + math.cos(angle) * offset,
            self.y + math.sin(angle) * offset,
        )

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

    def _in_sight(self: Self, player_center: tuple[float, float]) -> bool:
        dx = player_center[0] - self.x
        dy = player_center[1] - self.y
        return dx * dx + dy * dy <= self.sight_range * self.sight_range

    def _nearest_zombie_target(
        self: Self, nearby_zombies: list[pygame.sprite.Sprite]
    ) -> pygame.sprite.Sprite | None:
        best: pygame.sprite.Sprite | None = None
        best_dist_sq = ZOMBIE_DOG_PACK_CHASE_RANGE * ZOMBIE_DOG_PACK_CHASE_RANGE
        for candidate in nearby_zombies:
            if not isinstance(candidate, Zombie):
                continue
            if candidate is self or not candidate.alive():
                continue
            if not hasattr(candidate, "carbonized"):
                continue
            if getattr(candidate, "carbonized", False):
                continue
            dx = candidate.rect.centerx - self.x
            dy = candidate.rect.centery - self.y
            dist_sq = dx * dx + dy * dy
            if dist_sq <= best_dist_sq:
                best = candidate
                best_dist_sq = dist_sq
        return best

    def _set_charge_direction(self: Self, player_center: tuple[float, float]) -> None:
        dx = player_center[0] - self.x
        dy = player_center[1] - self.y
        dist = math.hypot(dx, dy)
        if dist <= 0:
            self.charge_direction = (0.0, 0.0)
            return
        self.charge_direction = (dx / dist, dy / dist)

    def _avoid_other_zombies(
        self: Self,
        move_x: float,
        move_y: float,
        zombies: list[pygame.sprite.Sprite],
    ) -> tuple[float, float]:
        """If another zombie is too close, steer directly away from the closest one."""
        next_x = self.x + move_x
        next_y = self.y + move_y

        closest: pygame.sprite.Sprite | None = None
        closest_dist_sq = ZOMBIE_SEPARATION_DISTANCE * ZOMBIE_SEPARATION_DISTANCE
        for other in zombies:
            if other is self or not other.alive():
                continue
            if isinstance(other, Zombie) and not isinstance(other, ZombieDog):
                continue
            dx = other.x - next_x  # type: ignore[attr-defined]
            dy = other.y - next_y  # type: ignore[attr-defined]
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

        away_dx = next_x - closest.x  # type: ignore[attr-defined]
        away_dy = next_y - closest.y  # type: ignore[attr-defined]
        away_dist = math.hypot(away_dx, away_dy)
        if away_dist == 0:
            angle = RNG.uniform(0, 2 * math.pi)
            away_dx, away_dy = math.cos(angle), math.sin(angle)
            away_dist = 1

        speed = math.hypot(move_x, move_y)
        if speed <= 0:
            speed = self.speed_patrol
        move_x = (away_dx / away_dist) * speed
        move_y = (away_dy / away_dist) * speed
        return move_x, move_y

    def _apply_pack_damage(
        self: Self,
        nearby_zombies: list[pygame.sprite.Sprite],
        *,
        allow_bite: bool,
    ) -> None:
        if not allow_bite:
            return
        head_x, head_y = self._head_center()
        for candidate in nearby_zombies:
            if not isinstance(candidate, Zombie):
                continue
            if candidate is self or not candidate.alive():
                continue
            dx = candidate.x - head_x
            dy = candidate.y - head_y
            combined = self.head_radius + candidate.radius
            if dx * dx + dy * dy <= combined * combined:
                candidate.take_damage(ZOMBIE_DOG_BITE_DAMAGE)
                if (
                    candidate.alive()
                    and getattr(candidate, "decay_duration_frames", 0) > 0
                    and getattr(candidate, "max_health", 0) > 0
                ):
                    frames_to_zero = (
                        candidate.health
                        * candidate.decay_duration_frames
                        / candidate.max_health
                    )
                    if frames_to_zero <= FPS:
                        candidate.take_damage(candidate.health)

    def _apply_decay(self: Self) -> None:
        self.vitals.apply_decay()

    def _apply_wall_collision(
        self: Self,
        next_x: float,
        next_y: float,
        walls: list[Wall],
    ) -> tuple[float, float, bool, bool]:
        hit_x = False
        hit_y = False
        possible_walls = [
            w
            for w in walls
            if abs(w.rect.centerx - self.x) < 100 and abs(w.rect.centery - self.y) < 100
        ]
        final_x = self.x
        final_y = self.y
        if next_x != self.x:
            for wall in possible_walls:
                if _circle_wall_collision((next_x, final_y), self.radius, wall):
                    hit_x = True
                    next_x = self.x
                    break
            final_x = next_x
        if next_y != self.y:
            for wall in possible_walls:
                if _circle_wall_collision((final_x, next_y), self.radius, wall):
                    hit_y = True
                    next_y = self.y
                    break
            final_y = next_y
        return final_x, final_y, hit_x, hit_y

    def _apply_paralyze_overlay(self: Self, now_ms: int) -> None:
        base_surface = self.directional_images[self.facing_bin]
        image = base_surface.copy()
        center = image.get_rect().center
        marker_size = max(6, int(self.short_axis * 0.8))
        draw_paralyze_marker(
            surface=image,
            now_ms=now_ms,
            blink_ms=PATROL_BOT_PARALYZE_BLINK_MS,
            center=center,
            size=marker_size,
            color=PATROL_BOT_PARALYZE_MARKER_COLOR,
            offset=int(self.short_axis * 0.4),
            width=2,
        )
        self.image = image

    def update(
        self: Self,
        player_center: tuple[float, float],
        walls: list[Wall],
        nearby_zombies: list[pygame.sprite.Sprite],
        nearby_patrol_bots: list[pygame.sprite.Sprite] | None = None,
        footprints: list | None = None,
        *,
        cell_size: int,
        layout,
        drift_x: float = 0.0,
        drift_y: float = 0.0,
    ) -> None:
        if self.vitals.carbonized:
            self._apply_decay()
            return
        self._apply_decay()
        if not self.alive():
            return
        _ = nearby_zombies, footprints
        possible_bots = []
        if nearby_patrol_bots:
            possible_bots = [
                b
                for b in nearby_patrol_bots
                if abs(b.x - self.x) < 100 and abs(b.y - self.y) < 100
            ]
        now = pygame.time.get_ticks()
        if self.vitals.update_patrol_paralyze(
            entity_center=(self.x, self.y),
            entity_radius=self.radius,
            patrol_bots=possible_bots,
            now_ms=now,
            paralyze_duration_ms=PATROL_BOT_PARALYZE_MS,
            damage_interval_frames=PATROL_BOT_ZOMBIE_DAMAGE_INTERVAL_FRAMES,
            damage_amount=PATROL_BOT_ZOMBIE_DAMAGE,
            apply_damage=self.take_damage,
        ):
            self.last_move_dx = 0.0
            self.last_move_dy = 0.0
            self._apply_paralyze_overlay(now)
            return
        level_width = layout.field_rect.width
        level_height = layout.field_rect.height

        chase_target = self._nearest_zombie_target(list(nearby_zombies))
        if chase_target is not None:
            if self.mode != ZombieDogMode.CHASE:
                self.mode = ZombieDogMode.CHASE
        elif self.mode == ZombieDogMode.CHASE:
            self.mode = ZombieDogMode.WANDER

        if self.mode == ZombieDogMode.WANDER and self._in_sight(player_center):
            self.mode = ZombieDogMode.CHARGE
            self._set_charge_direction(player_center)
            if self.charge_direction == (0.0, 0.0):
                self.wander_angle = RNG.uniform(0.0, math.tau)
                self.charge_direction = (
                    math.cos(self.wander_angle),
                    math.sin(self.wander_angle),
                )
        elif self.mode == ZombieDogMode.CHARGE and not self._in_sight(player_center):
            self.mode = ZombieDogMode.WANDER

        move_x = 0.0
        move_y = 0.0
        if self.mode == ZombieDogMode.WANDER:
            now = pygame.time.get_ticks()
            if now - self.wander_change_time > ZOMBIE_DOG_WANDER_INTERVAL_MS:
                self.wander_change_time = now
                self.wander_angle = RNG.uniform(0.0, math.tau)
            move_x = math.cos(self.wander_angle) * self.speed_patrol
            move_y = math.sin(self.wander_angle) * self.speed_patrol
        elif self.mode == ZombieDogMode.CHARGE:
            if self.charge_direction == (0.0, 0.0):
                self.wander_angle = RNG.uniform(0.0, math.tau)
                self.charge_direction = (
                    math.cos(self.wander_angle),
                    math.sin(self.wander_angle),
                )
            move_x = self.charge_direction[0] * self.speed_assault
            move_y = self.charge_direction[1] * self.speed_assault
        elif self.mode == ZombieDogMode.CHASE and chase_target is not None:
            dx = chase_target.rect.centerx - self.x
            dy = chase_target.rect.centery - self.y
            dist = math.hypot(dx, dy)
            if dist > 0:
                move_x = (dx / dist) * self.speed_patrol
                move_y = (dy / dist) * self.speed_patrol
            else:
                self.mode = ZombieDogMode.WANDER
                self.wander_angle = RNG.uniform(0.0, math.tau)
                self.wander_change_time = pygame.time.get_ticks()

        move_x += drift_x
        move_y += drift_y
        if nearby_zombies:
            move_x, move_y = self._avoid_other_zombies(
                move_x, move_y, list(nearby_zombies)
            )
        move_x, move_y = apply_cell_edge_nudge(
            self.x,
            self.y,
            move_x,
            move_y,
            layout=layout,
            cell_size=cell_size,
        )
        self._update_facing_from_movement(move_x, move_y)
        self.image = self.directional_images[self.facing_bin]
        self.last_move_dx = move_x
        self.last_move_dy = move_y

        next_x = self.x + move_x
        next_y = self.y + move_y
        final_x, final_y, hit_x, hit_y = self._apply_wall_collision(
            next_x, next_y, walls
        )

        if self.mode == ZombieDogMode.WANDER and (hit_x or hit_y):
            self.wander_angle = (self.wander_angle + math.pi) % math.tau
        elif self.mode in (ZombieDogMode.CHARGE, ZombieDogMode.CHASE) and (
            hit_x or hit_y
        ):
            self.mode = ZombieDogMode.WANDER
            self.wander_angle = RNG.uniform(0.0, math.tau)
            self.wander_change_time = pygame.time.get_ticks()

        if (
            self.mode == ZombieDogMode.WANDER
            and self.last_move_dx == 0.0
            and self.last_move_dy == 0.0
        ):
            self.wander_angle = RNG.uniform(0.0, math.tau)
            self.wander_change_time = pygame.time.get_ticks()
        if final_x == self.x and final_y == self.y:
            self.wander_angle = RNG.uniform(0.0, math.tau)
            try_dx = math.cos(self.wander_angle) * self.speed_patrol
            try_dy = math.sin(self.wander_angle) * self.speed_patrol
            try_dx, try_dy = apply_cell_edge_nudge(
                self.x,
                self.y,
                try_dx,
                try_dy,
                layout=layout,
                cell_size=cell_size,
            )
            retry_x, retry_y, _, _ = self._apply_wall_collision(
                self.x + try_dx, self.y + try_dy, walls
            )
            if retry_x != self.x or retry_y != self.y:
                final_x = retry_x
                final_y = retry_y

        if not (0 <= final_x < level_width and 0 <= final_y < level_height):
            self.kill()
            return

        self.x = final_x
        self.y = final_y
        self.rect.center = (int(self.x), int(self.y))

        if nearby_zombies:
            self.bite_frame_counter = (
                self.bite_frame_counter + 1
            ) % ZOMBIE_DOG_BITE_INTERVAL_FRAMES
            self._apply_pack_damage(
                list(nearby_zombies),
                allow_bite=self.bite_frame_counter == 0,
            )

    def carbonize(self: Self) -> None:
        self.vitals.carbonize()

    def take_damage(self: Self, amount: int) -> None:
        if amount <= 0 or not self.alive():
            return
        self.vitals.take_damage(amount)
