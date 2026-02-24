from __future__ import annotations

import math
from enum import Enum
from typing import Protocol

import pygame

try:
    from typing import Self
except ImportError:  # pragma: no cover - Python 3.10 fallback
    from typing_extensions import Self

from ..entities_constants import (
    ZombieKind,
    ZOMBIE_DOG_ASSAULT_SPEED,
    ZOMBIE_DOG_CHARGE_COOLDOWN_MS_NIMBLE,
    ZOMBIE_DOG_CHARGE_COOLDOWN_MS_NORMAL,
    ZOMBIE_DOG_CHARGE_DISTANCE_NIMBLE,
    ZOMBIE_DOG_CHARGE_DISTANCE_NORMAL,
    ZOMBIE_DOG_CHARGE_WINDUP_FRAMES,
    ZOMBIE_DOG_CHARGE_OFFSET_MAX_NIMBLE,
    ZOMBIE_DOG_CHARGE_OFFSET_MAX_NORMAL,
    ZOMBIE_DOG_CHARGE_OFFSET_MIN_NIMBLE,
    ZOMBIE_DOG_CHARGE_OFFSET_MIN_NORMAL,
    ZOMBIE_CARBONIZE_DECAY_FRAMES,
    ZOMBIE_DOG_DECAY_DURATION_FRAMES,
    ZOMBIE_DOG_DECAY_MIN_SPEED_RATIO,
    ZOMBIE_DOG_LONG_AXIS_RATIO,
    ZOMBIE_DOG_PATROL_SPEED,
    ZOMBIE_DOG_PACK_CHASE_RANGE,
    ZOMBIE_DOG_SHORT_AXIS_RATIO,
    ZOMBIE_DOG_SIGHT_RANGE,
    ZOMBIE_DOG_TRACKER_FOLLOW_SPEED_MULTIPLIER,
    ZOMBIE_DOG_TRACKER_SIGHT_RANGE,
    ZOMBIE_DOG_WANDER_INTERVAL_MS,
    ZOMBIE_DOG_WANDER_HEADING_PLAYER_RANGE,
    PATROL_BOT_ZOMBIE_DAMAGE,
    PATROL_BOT_ZOMBIE_DAMAGE_INTERVAL_FRAMES,
    PATROL_BOT_PARALYZE_MS,
    PATROL_BOT_PARALYZE_BLINK_MS,
    PATROL_BOT_PARALYZE_MARKER_COLOR,
    PUDDLE_SPEED_FACTOR,
    TRAPPED_ZOMBIE_SLOW_FACTOR,
    TRAPPED_ZOMBIE_REPEL_MAX_MULT,
    TRAPPED_ZOMBIE_REPEL_PER_STACK,
    TRAPPED_ZOMBIE_REPEL_RADIUS_CELLS,
    ZOMBIE_CONTAMINATED_SPEED_FACTOR,
    ZOMBIE_RADIUS,
    ZOMBIE_SEPARATION_DISTANCE,
)
from ..rng import get_rng
from ..surface_effects import SpikyPlantLike, is_in_contaminated_cell, is_in_puddle_cell
from ..render.entity_overlays import draw_paralyze_marker_overlay
from ..render_constants import ENTITY_SHADOW_RADIUS_MULT, ZOMBIE_NOSE_COLOR
from ..render_assets import (
    angle_bin_from_vector,
    build_zombie_dog_directional_surfaces,
    draw_tracker_nose,
)
from ..world_grid import apply_cell_edge_nudge
from .zombie import Zombie
from .movement_helpers import separate_circle_from_blockers
from .tracker_scent import TrackerScentState, update_tracker_target_from_footprints
from .zombie_visuals import build_grayscale_image
from .zombie_vitals import ZombieVitals


RNG = get_rng()


class ZombieDogMode(Enum):
    WANDER = "wander"
    CHARGE = "charge"
    CHASE = "chase"


class ZombieDogVariant(str, Enum):
    NORMAL = "normal"
    NIMBLE = "nimble"
    TRACKER = "tracker"


class MovementStrategy(Protocol):
    def __call__(
        self,
        zombie_dog: "ZombieDog",
        cell_size: int,
        layout,
        player_center: tuple[float, float],
        nearby_zombies: list[pygame.sprite.Sprite],
        footprints: list,
        *,
        now_ms: int,
) -> tuple[float, float]: ...


def _set_wander_heading_toward_player_if_close(
    zombie_dog: "ZombieDog",
    player_center: tuple[float, float],
) -> None:
    dx = player_center[0] - zombie_dog.x
    dy = player_center[1] - zombie_dog.y
    dist_sq = dx * dx + dy * dy
    threshold = ZOMBIE_DOG_WANDER_HEADING_PLAYER_RANGE
    if dist_sq > threshold * threshold or dist_sq <= 1e-6:
        return
    zombie_dog.wander_angle = math.atan2(dy, dx)


def _pick_charge_target_around_player(
    zombie_dog: "ZombieDog",
    *,
    cell_size: int,
    layout,
    player_center: tuple[float, float],
) -> tuple[float, float] | None:
    for _ in range(8):
        angle = RNG.uniform(0.0, math.tau)
        offset = RNG.uniform(zombie_dog.charge_offset_min, zombie_dog.charge_offset_max)
        tx = player_center[0] + math.cos(angle) * offset
        ty = player_center[1] + math.sin(angle) * offset
        if not (0 <= tx < layout.field_rect.width and 0 <= ty < layout.field_rect.height):
            continue
        if cell_size > 0:
            target_cell = (int(tx // cell_size), int(ty // cell_size))
            if target_cell in layout.wall_cells or target_cell in layout.material_cells:
                continue
        # Avoid micro-charge that looks like jitter.
        if math.hypot(tx - zombie_dog.x, ty - zombie_dog.y) < zombie_dog.speed_assault * 6.0:
            continue
        return (tx, ty)
    return None


def _reset_charge_to_wander(zombie_dog: "ZombieDog", *, now_ms: int) -> None:
    zombie_dog._set_mode(ZombieDogMode.WANDER)
    zombie_dog.next_charge_available_ms = now_ms + zombie_dog.charge_cooldown_ms
    zombie_dog.charge_direction = None


def _update_charge_state(
    zombie_dog: "ZombieDog",
    *,
    in_sight: bool,
    cell_size: int,
    layout,
    player_center: tuple[float, float],
    now_ms: int,
) -> None:
    if (
        zombie_dog.mode == ZombieDogMode.WANDER
        and in_sight
        and now_ms >= zombie_dog.next_charge_available_ms
    ):
        candidate = _pick_charge_target_around_player(
            zombie_dog,
            cell_size=cell_size,
            layout=layout,
            player_center=player_center,
        )
        if candidate is not None:
            zombie_dog._enter_charge(
                candidate=candidate,
                player_center=player_center,
                now_ms=now_ms,
            )
    elif zombie_dog.mode == ZombieDogMode.CHARGE and not in_sight:
        _reset_charge_to_wander(zombie_dog, now_ms=now_ms)


def _charge_step(zombie_dog: "ZombieDog", *, now_ms: int) -> tuple[float, float] | None:
    if zombie_dog.mode != ZombieDogMode.CHARGE:
        return None
    if zombie_dog.charge_windup_frames_remaining > 0:
        zombie_dog.charge_windup_frames_remaining -= 1
        return (0.0, 0.0)
    if zombie_dog.charge_target is None:
        _reset_charge_to_wander(zombie_dog, now_ms=now_ms)
        return (0.0, 0.0)
    if zombie_dog.charge_distance_remaining <= 0.0:
        _reset_charge_to_wander(zombie_dog, now_ms=now_ms)
        return (0.0, 0.0)
    charge_direction = zombie_dog.charge_direction
    if charge_direction is None:
        dx = zombie_dog.charge_target[0] - zombie_dog.x
        dy = zombie_dog.charge_target[1] - zombie_dog.y
        dist = math.hypot(dx, dy)
        if dist <= 1e-6:
            _reset_charge_to_wander(zombie_dog, now_ms=now_ms)
            return (0.0, 0.0)
        charge_direction = (dx / dist, dy / dist)
        zombie_dog.charge_direction = charge_direction
    step = min(zombie_dog.speed_assault, zombie_dog.charge_distance_remaining)
    zombie_dog.charge_distance_remaining = max(0.0, zombie_dog.charge_distance_remaining - step)
    return (charge_direction[0] * step, charge_direction[1] * step)


def _wander_step_avoiding_fire_floor(
    zombie_dog: "ZombieDog",
    *,
    cell_size: int,
    layout,
) -> tuple[float, float]:
    move_x = math.cos(zombie_dog.wander_angle) * zombie_dog.speed_patrol
    move_y = math.sin(zombie_dog.wander_angle) * zombie_dog.speed_patrol
    if cell_size > 0 and layout.fire_floor_cells:
        next_cell = (
            int((zombie_dog.x + move_x) // cell_size),
            int((zombie_dog.y + move_y) // cell_size),
        )
        if next_cell in layout.fire_floor_cells:
            zombie_dog.wander_angle = (zombie_dog.wander_angle + math.pi) % math.tau
            move_x = math.cos(zombie_dog.wander_angle) * zombie_dog.speed_patrol
            move_y = math.sin(zombie_dog.wander_angle) * zombie_dog.speed_patrol
            retry_cell = (
                int((zombie_dog.x + move_x) // cell_size),
                int((zombie_dog.y + move_y) // cell_size),
            )
            if retry_cell in layout.fire_floor_cells:
                return (0.0, 0.0)
    return (move_x, move_y)


def _zombie_dog_default_movement(
    zombie_dog: "ZombieDog",
    cell_size: int,
    layout,
    player_center: tuple[float, float],
    nearby_zombies: list[pygame.sprite.Sprite],
    _footprints: list,
    *,
    now_ms: int,
) -> tuple[float, float]:
    nearby = list(nearby_zombies)
    chase_target = zombie_dog._nearest_zombie_target(nearby)
    if chase_target is not None:
        zombie_dog._set_mode(ZombieDogMode.CHASE)
    else:
        if zombie_dog.mode == ZombieDogMode.CHASE:
            zombie_dog._set_mode(ZombieDogMode.WANDER)
        chase_target = None

    _update_charge_state(
        zombie_dog,
        in_sight=zombie_dog._in_sight(player_center),
        cell_size=cell_size,
        layout=layout,
        player_center=player_center,
        now_ms=now_ms,
    )

    if zombie_dog.mode == ZombieDogMode.WANDER:
        if zombie_dog.just_entered_wander:
            _set_wander_heading_toward_player_if_close(zombie_dog, player_center)
            zombie_dog.just_entered_wander = False
            zombie_dog.wander_change_time = now_ms
        elif now_ms - zombie_dog.wander_change_time > ZOMBIE_DOG_WANDER_INTERVAL_MS:
            zombie_dog.wander_change_time = now_ms
            zombie_dog.wander_angle = RNG.uniform(0.0, math.tau)
        return _wander_step_avoiding_fire_floor(
            zombie_dog,
            cell_size=cell_size,
            layout=layout,
        )
    charge_move = _charge_step(zombie_dog, now_ms=now_ms)
    if charge_move is not None:
        return charge_move
    if zombie_dog.mode == ZombieDogMode.CHASE and chase_target is not None:
        dx = chase_target.rect.centerx - zombie_dog.x
        dy = chase_target.rect.centery - zombie_dog.y
        dist = math.hypot(dx, dy)
        if dist > 0:
            return (
                (dx / dist) * zombie_dog.speed_patrol,
                (dy / dist) * zombie_dog.speed_patrol,
            )
    zombie_dog._set_mode(ZombieDogMode.WANDER)
    if zombie_dog.just_entered_wander:
        _set_wander_heading_toward_player_if_close(zombie_dog, player_center)
        zombie_dog.just_entered_wander = False
        zombie_dog.wander_change_time = now_ms
    if zombie_dog.wander_change_time != now_ms:
        zombie_dog.wander_angle = RNG.uniform(0.0, math.tau)
        zombie_dog.wander_change_time = now_ms
    return (
        math.cos(zombie_dog.wander_angle) * zombie_dog.speed_patrol,
        math.sin(zombie_dog.wander_angle) * zombie_dog.speed_patrol,
    )


def _zombie_dog_move_toward(
    zombie_dog: "ZombieDog",
    target: tuple[float, float],
    *,
    speed_multiplier: float = 1.0,
) -> tuple[float, float]:
    dx = target[0] - zombie_dog.x
    dy = target[1] - zombie_dog.y
    dist = math.hypot(dx, dy)
    if dist <= 1e-6:
        return (0.0, 0.0)
    speed = zombie_dog.speed_patrol * max(0.0, speed_multiplier)
    return (
        (dx / dist) * speed,
        (dy / dist) * speed,
    )


def _zombie_dog_tracker_movement(
    zombie_dog: "ZombieDog",
    cell_size: int,
    layout,
    player_center: tuple[float, float],
    _nearby_zombies: list[pygame.sprite.Sprite],
    footprints: list,
    *,
    now_ms: int,
) -> tuple[float, float]:
    in_sight = zombie_dog._in_sight(player_center)
    _update_charge_state(
        zombie_dog,
        in_sight=in_sight,
        cell_size=cell_size,
        layout=layout,
        player_center=player_center,
        now_ms=now_ms,
    )
    charge_move = _charge_step(zombie_dog, now_ms=now_ms)
    if charge_move is not None:
        return charge_move

    update_tracker_target_from_footprints(
        zombie_dog.tracker_state,
        origin=(zombie_dog.x, zombie_dog.y),
        footprints=footprints or [],
        layout=layout,
        cell_size=cell_size,
        now_ms=now_ms,
    )
    if zombie_dog.tracker_target_pos is not None:
        zombie_dog._set_mode(ZombieDogMode.WANDER)
        zombie_dog.just_entered_wander = False
        zombie_dog.wander_change_time = now_ms
        return _zombie_dog_move_toward(
            zombie_dog,
            zombie_dog.tracker_target_pos,
            speed_multiplier=ZOMBIE_DOG_TRACKER_FOLLOW_SPEED_MULTIPLIER,
        )

    zombie_dog._set_mode(ZombieDogMode.WANDER)
    if zombie_dog.just_entered_wander:
        _set_wander_heading_toward_player_if_close(zombie_dog, player_center)
        zombie_dog.just_entered_wander = False
        zombie_dog.wander_change_time = now_ms
    elif now_ms - zombie_dog.wander_change_time > ZOMBIE_DOG_WANDER_INTERVAL_MS:
        zombie_dog.wander_change_time = now_ms
        zombie_dog.wander_angle = RNG.uniform(0.0, math.tau)
    return _wander_step_avoiding_fire_floor(
        zombie_dog,
        cell_size=cell_size,
        layout=layout,
    )


class ZombieDog(pygame.sprite.Sprite):
    def __init__(
        self: Self,
        x: float,
        y: float,
        *,
        movement_strategy: MovementStrategy | None = None,
        variant: ZombieDogVariant = ZombieDogVariant.NORMAL,
    ) -> None:
        super().__init__()
        base_size = ZOMBIE_RADIUS * 2.0
        self.long_axis = base_size * ZOMBIE_DOG_LONG_AXIS_RATIO
        self.short_axis = base_size * ZOMBIE_DOG_SHORT_AXIS_RATIO
        self.radius = self.short_axis * 0.5
        self.speed_patrol = ZOMBIE_DOG_PATROL_SPEED
        self.speed_assault = ZOMBIE_DOG_ASSAULT_SPEED
        self.initial_speed_patrol = self.speed_patrol
        self.initial_speed_assault = self.speed_assault
        self.sight_range = ZOMBIE_DOG_SIGHT_RANGE
        self.mode = ZombieDogMode.WANDER
        self.just_entered_wander = True
        self.charge_target: tuple[float, float] | None = None
        self.charge_direction: tuple[float, float] | None = None
        self.charge_windup_frames_remaining = 0
        self.charge_distance_remaining = 0.0
        self.next_charge_available_ms = 0
        self.wander_angle = RNG.uniform(0.0, math.tau)
        self.wander_change_time = 0
        self.variant = (
            variant
            if isinstance(variant, ZombieDogVariant)
            else ZombieDogVariant(str(variant))
        )
        self.tracker_state = TrackerScentState()
        self.nimble_tail_side = RNG.choice([-1.0, 1.0])
        if self.variant == ZombieDogVariant.NIMBLE:
            self.charge_offset_min = ZOMBIE_DOG_CHARGE_OFFSET_MIN_NIMBLE
            self.charge_offset_max = ZOMBIE_DOG_CHARGE_OFFSET_MAX_NIMBLE
            self.charge_distance_max = ZOMBIE_DOG_CHARGE_DISTANCE_NIMBLE
            self.charge_cooldown_ms = ZOMBIE_DOG_CHARGE_COOLDOWN_MS_NIMBLE
            self.movement_strategy = movement_strategy or _zombie_dog_default_movement
        elif self.variant == ZombieDogVariant.TRACKER:
            self.charge_offset_min = ZOMBIE_DOG_CHARGE_OFFSET_MIN_NORMAL
            self.charge_offset_max = ZOMBIE_DOG_CHARGE_OFFSET_MAX_NORMAL
            self.charge_distance_max = ZOMBIE_DOG_CHARGE_DISTANCE_NORMAL
            self.charge_cooldown_ms = ZOMBIE_DOG_CHARGE_COOLDOWN_MS_NORMAL
            self.sight_range = ZOMBIE_DOG_TRACKER_SIGHT_RANGE
            self.movement_strategy = movement_strategy or _zombie_dog_tracker_movement
        else:
            self.charge_offset_min = ZOMBIE_DOG_CHARGE_OFFSET_MIN_NORMAL
            self.charge_offset_max = ZOMBIE_DOG_CHARGE_OFFSET_MAX_NORMAL
            self.charge_distance_max = ZOMBIE_DOG_CHARGE_DISTANCE_NORMAL
            self.charge_cooldown_ms = ZOMBIE_DOG_CHARGE_COOLDOWN_MS_NORMAL
            self.movement_strategy = movement_strategy or _zombie_dog_default_movement
        self.kind = ZombieKind.DOG
        self.facing_bin = 0
        self.directional_images = build_zombie_dog_directional_surfaces(
            self.long_axis,
            self.short_axis,
        )
        if self.variant == ZombieDogVariant.NIMBLE:
            self.directional_images = self._build_nimble_directional_images(
                self.directional_images
            )
        elif self.variant == ZombieDogVariant.TRACKER:
            self.directional_images = self._build_tracker_directional_images(
                self.directional_images
            )
        self.image = self.directional_images[self.facing_bin]
        self.rect = self.image.get_rect(center=(x, y))
        self.x = float(self.rect.centerx)
        self.y = float(self.rect.centery)
        self.last_move_dx = 0.0
        self.last_move_dy = 0.0
        self.vitals = ZombieVitals(
            max_health=100,
            decay_duration_frames=ZOMBIE_DOG_DECAY_DURATION_FRAMES,
            decay_min_speed_ratio=ZOMBIE_DOG_DECAY_MIN_SPEED_RATIO,
            carbonize_decay_frames=ZOMBIE_CARBONIZE_DECAY_FRAMES,
            on_health_ratio=self._apply_speed_ratio,
            on_kill=self.kill,
            on_carbonize=self._apply_carbonize_visuals,
        )
        self.collision_radius = float(self.radius)
        self.shadow_radius = max(
            1, int(self.collision_radius * ENTITY_SHADOW_RADIUS_MULT)
        )
        self.shadow_offset_scale = 1.0
        self._refresh_variant_image()

    def _build_nimble_directional_images(
        self: Self, base_images: list[pygame.Surface]
    ) -> list[pygame.Surface]:
        if not base_images:
            return base_images
        bins = max(1, len(base_images))
        tail_fill = (230, 40, 40)
        tail_radius = max(1, int(round(self.short_axis / 3.0)))
        rear_offset = max(1, int(round(self.long_axis * 0.35)))
        side_offset = max(1, int(round(tail_radius * 0.9)))
        side_sign = self.nimble_tail_side
        nimble_images: list[pygame.Surface] = []
        for idx, image in enumerate(base_images):
            surf = image.copy()
            center = pygame.Vector2(surf.get_rect().center)
            angle = (idx % bins) * (math.tau / bins)
            forward = pygame.Vector2(math.cos(angle), math.sin(angle))
            right = pygame.Vector2(-forward.y, forward.x)
            tail_center = (
                center - (forward * rear_offset) + (right * side_sign * side_offset)
            )
            tail_pos = (int(round(tail_center.x)), int(round(tail_center.y)))
            pygame.draw.circle(surf, tail_fill, tail_pos, tail_radius)
            nimble_images.append(surf)
        return nimble_images

    def _build_tracker_directional_images(
        self: Self, base_images: list[pygame.Surface]
    ) -> list[pygame.Surface]:
        if not base_images:
            return base_images
        bins = max(1, len(base_images))
        tracker_images: list[pygame.Surface] = []
        for idx, image in enumerate(base_images):
            surf = image.copy()
            angle_rad = (idx % bins) * (math.tau / bins)
            draw_tracker_nose(
                surf,
                radius=max(1, int(round(self.radius))),
                angle_rad=angle_rad,
                color=ZOMBIE_NOSE_COLOR,
                offset_scale=0.55,
            )
            tracker_images.append(surf)
        return tracker_images

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

    @property
    def tracker_target_pos(self: Self) -> tuple[float, float] | None:
        return self.tracker_state.target_pos

    @tracker_target_pos.setter
    def tracker_target_pos(self: Self, value: tuple[float, float] | None) -> None:
        self.tracker_state.target_pos = value

    @property
    def tracker_target_time(self: Self) -> int | None:
        return self.tracker_state.target_time

    @tracker_target_time.setter
    def tracker_target_time(self: Self, value: int | None) -> None:
        self.tracker_state.target_time = value

    def _apply_speed_ratio(self: Self, ratio: float) -> None:
        self.speed_patrol = self.initial_speed_patrol * ratio
        self.speed_assault = self.initial_speed_assault * ratio

    def _apply_carbonize_visuals(self: Self) -> None:
        self.image = build_grayscale_image(self.image)

    def _set_mode(self: Self, new_mode: ZombieDogMode) -> None:
        if self.mode == new_mode:
            return
        if new_mode == ZombieDogMode.WANDER:
            self.just_entered_wander = True
        elif self.mode == ZombieDogMode.WANDER:
            self.just_entered_wander = False
        self.mode = new_mode

    def _enter_charge(
        self: Self,
        *,
        candidate: tuple[float, float],
        player_center: tuple[float, float],
        now_ms: int,
    ) -> None:
        self._set_mode(ZombieDogMode.CHARGE)
        self.wander_change_time = now_ms
        self.charge_target = candidate
        dir_dx = candidate[0] - self.x
        dir_dy = candidate[1] - self.y
        dir_dist = math.hypot(dir_dx, dir_dy)
        if dir_dist > 1e-6:
            self.charge_direction = (dir_dx / dir_dist, dir_dy / dir_dist)
        else:
            self.charge_direction = None
        self.charge_distance_remaining = self.charge_distance_max
        self.charge_windup_frames_remaining = ZOMBIE_DOG_CHARGE_WINDUP_FRAMES
        # Telegraph charge intent: face toward player before starting movement.
        self._update_facing_from_movement(
            player_center[0] - self.x,
            player_center[1] - self.y,
        )

    def _set_facing_bin(self: Self, new_bin: int) -> None:
        if new_bin == self.facing_bin:
            return
        center = self.rect.center
        self.facing_bin = new_bin
        self._refresh_variant_image()
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
            if getattr(candidate, "is_trapped", False):
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
            if getattr(other, "is_trapped", False):
                continue

            ox = other.x  # type: ignore[attr-defined]
            oy = other.y  # type: ignore[attr-defined]

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

    def _slow_near_trapped_zombies(
        self: Self,
        move_x: float,
        move_y: float,
        zombies: list[pygame.sprite.Sprite],
    ) -> tuple[float, float]:
        next_x = self.x + move_x
        next_y = self.y + move_y
        for other in zombies:
            if other is self or not other.alive():
                continue
            if not getattr(other, "is_trapped", False):
                continue
            ox = float(getattr(other, "x", other.rect.centerx))
            oy = float(getattr(other, "y", other.rect.centery))
            other_radius = float(getattr(other, "collision_radius", 0.0))
            dx = ox - next_x
            dy = oy - next_y
            touch_radius = self.collision_radius + other_radius
            if dx * dx + dy * dy <= touch_radius * touch_radius:
                return (
                    move_x * TRAPPED_ZOMBIE_SLOW_FACTOR,
                    move_y * TRAPPED_ZOMBIE_SLOW_FACTOR,
                )
        return move_x, move_y

    def _repel_from_loaded_spiky_plants(
        self: Self,
        move_x: float,
        move_y: float,
        *,
        cell_size: int,
        spiky_plants: dict[tuple[int, int], SpikyPlantLike] | None,
        trapped_spiky_plant_counts: dict[tuple[int, int], int] | None,
    ) -> tuple[float, float]:
        if cell_size <= 0 or not spiky_plants or not trapped_spiky_plant_counts:
            return move_x, move_y
        next_x = self.x + move_x
        next_y = self.y + move_y
        effect_radius = max(
            self.collision_radius * 2.0,
            float(cell_size) * TRAPPED_ZOMBIE_REPEL_RADIUS_CELLS,
        )
        repel_x = 0.0
        repel_y = 0.0
        for cell, trapped_count in trapped_spiky_plant_counts.items():
            if trapped_count <= 0:
                continue
            hp = spiky_plants.get(cell)
            if hp is None or not hp.alive():
                continue
            dx = next_x - hp.x
            dy = next_y - hp.y
            dist = math.hypot(dx, dy)
            if dist > effect_radius:
                continue
            if dist <= 0.001:
                angle = RNG.uniform(0.0, math.tau)
                dx = math.cos(angle)
                dy = math.sin(angle)
                dist = 1.0
            falloff = 1.0 - (dist / effect_radius)
            count_mult = min(
                TRAPPED_ZOMBIE_REPEL_MAX_MULT,
                trapped_count * TRAPPED_ZOMBIE_REPEL_PER_STACK,
            )
            repel_mag = self.speed_patrol * count_mult * falloff
            repel_x += (dx / dist) * repel_mag
            repel_y += (dy / dist) * repel_mag
        return move_x + repel_x, move_y + repel_y

    def _apply_decay(self: Self) -> None:
        self.vitals.apply_decay()

    def _apply_wall_collision(
        self: Self,
        next_x: float,
        next_y: float,
        *,
        walls: list[pygame.sprite.Sprite],
        cell_size: int,
        layout,
    ) -> tuple[float, float, bool, bool]:
        if cell_size <= 0 or layout.grid_cols <= 0 or layout.grid_rows <= 0:
            return next_x, next_y, False, False
        attempted_dx = next_x - self.x
        attempted_dy = next_y - self.y
        separation = separate_circle_from_blockers(
            x=next_x,
            y=next_y,
            radius=self.collision_radius,
            walls=walls,
            cell_size=cell_size,
            blocked_cells=layout.material_cells,
            grid_cols=layout.grid_cols,
            grid_rows=layout.grid_rows,
            max_attempts=5,
        )
        resolved_dx = separation.x - self.x
        resolved_dy = separation.y - self.y
        hit_x = abs(attempted_dx - resolved_dx) > 1e-6 and abs(attempted_dx) > 0.0
        hit_y = abs(attempted_dy - resolved_dy) > 1e-6 and abs(attempted_dy) > 0.0
        return separation.x, separation.y, hit_x, hit_y

    def _refresh_variant_image(self: Self) -> None:
        self.image = self.directional_images[self.facing_bin]

    def refresh_image(self: Self) -> None:
        self._refresh_variant_image()

    def _apply_paralyze_overlay(self: Self, now_ms: int) -> None:
        self._refresh_variant_image()
        image = self.image.copy()
        center = image.get_rect().center
        marker_size = max(6, int(self.short_axis * 0.8))
        draw_paralyze_marker_overlay(
            surface_out=image,
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
        walls: list[pygame.sprite.Sprite],
        nearby_zombies: list[pygame.sprite.Sprite],
        electrified_cells: set[tuple[int, int]] | None = None,
        footprints: list | None = None,
        *,
        cell_size: int,
        layout,
        now_ms: int,
        drift: tuple[float, float] = (0.0, 0.0),
        spiky_plants: dict[tuple[int, int], SpikyPlantLike] | None = None,
        trapped_spiky_plant_counts: dict[tuple[int, int], int] | None = None,
    ) -> None:
        if self.vitals.carbonized:
            self._apply_decay()
            return
        self._apply_decay()
        if not self.alive():
            return

        now = now_ms
        drift_x, drift_y = drift
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
            apply_damage=lambda amount: self.take_damage(amount, now_ms=now),
        ):
            self.last_move_dx = 0.0
            self.last_move_dy = 0.0
            self._apply_paralyze_overlay(now)
            return
        level_width = layout.field_rect.width
        level_height = layout.field_rect.height

        move_x, move_y = self.movement_strategy(
            self,
            cell_size,
            layout,
            player_center,
            list(nearby_zombies),
            footprints or [],
            now_ms=now,
        )

        move_x += drift_x
        move_y += drift_y

        # Puddle slow-down
        if is_in_puddle_cell(
            self.x,
            self.y,
            cell_size=cell_size,
            puddle_cells=layout.puddle_cells,
        ):
            move_x *= PUDDLE_SPEED_FACTOR
            move_y *= PUDDLE_SPEED_FACTOR
        if is_in_contaminated_cell(
            self.x,
            self.y,
            cell_size=cell_size,
            contaminated_cells=layout.zombie_contaminated_cells,
        ):
            move_x *= ZOMBIE_CONTAMINATED_SPEED_FACTOR
            move_y *= ZOMBIE_CONTAMINATED_SPEED_FACTOR
        if nearby_zombies:
            move_x, move_y = self._slow_near_trapped_zombies(
                move_x, move_y, list(nearby_zombies)
            )
        move_x, move_y = self._repel_from_loaded_spiky_plants(
            move_x,
            move_y,
            cell_size=cell_size,
            spiky_plants=spiky_plants,
            trapped_spiky_plant_counts=trapped_spiky_plant_counts,
        )

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
        if self.patrol_paralyze_until_ms > now:
            self._apply_paralyze_overlay(now)
        else:
            self._refresh_variant_image()
        self.last_move_dx = move_x
        self.last_move_dy = move_y

        next_x = self.x + move_x
        next_y = self.y + move_y
        final_x, final_y, hit_x, hit_y = self._apply_wall_collision(
            next_x,
            next_y,
            walls=walls,
            cell_size=cell_size,
            layout=layout,
        )

        if self.mode == ZombieDogMode.WANDER and (hit_x or hit_y):
            self.wander_angle = (self.wander_angle + math.pi) % math.tau
        elif self.mode in (ZombieDogMode.CHARGE, ZombieDogMode.CHASE) and (
            hit_x or hit_y
        ):
            was_charge = self.mode == ZombieDogMode.CHARGE
            self._set_mode(ZombieDogMode.WANDER)
            if was_charge:
                self.next_charge_available_ms = now + self.charge_cooldown_ms
                self.charge_direction = None
            _set_wander_heading_toward_player_if_close(self, player_center)
            self.just_entered_wander = False
            self.wander_change_time = now

        if (
            self.mode == ZombieDogMode.WANDER
            and self.last_move_dx == 0.0
            and self.last_move_dy == 0.0
        ):
            self.wander_angle = RNG.uniform(0.0, math.tau)
            self.wander_change_time = now
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
                self.x + try_dx,
                self.y + try_dy,
                walls=walls,
                cell_size=cell_size,
                layout=layout,
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

    def carbonize(self: Self) -> None:
        self.vitals.carbonize()

    def take_damage(self: Self, amount: int, *, now_ms: int) -> None:
        if amount <= 0 or not self.alive():
            return
        self.vitals.take_damage(amount, now_ms=now_ms)
