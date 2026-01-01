"""Sprite and entity definitions for zombie_escape."""

from __future__ import annotations

import math
from enum import Enum
from typing import Callable, Iterable, Self

import pygame
from pygame import rect

from .colors import (
    BLACK,
    BLUE,
    DARK_RED,
    INTERNAL_WALL_BORDER_COLOR,
    INTERNAL_WALL_COLOR,
    ORANGE,
    RED,
    STEEL_BEAM_COLOR,
    STEEL_BEAM_LINE_COLOR,
    YELLOW,
)
from .constants import (
    CAR_HEIGHT,
    CAR_HEALTH,
    CAR_SPEED,
    CAR_WIDTH,
    CAR_WALL_DAMAGE,
    COMPANION_COLOR,
    COMPANION_FOLLOW_SPEED,
    COMPANION_RADIUS,
    FAST_ZOMBIE_SPEED_JITTER,
    FLASHLIGHT_HEIGHT,
    FLASHLIGHT_WIDTH,
    FUEL_CAN_HEIGHT,
    FUEL_CAN_WIDTH,
    INTERNAL_WALL_HEALTH,
    LEVEL_HEIGHT,
    LEVEL_WIDTH,
    NORMAL_ZOMBIE_SPEED_JITTER,
    PLAYER_RADIUS,
    PLAYER_SPEED,
    PLAYER_WALL_DAMAGE,
    SCREEN_HEIGHT,
    SCREEN_WIDTH,
    STEEL_BEAM_HEALTH,
    SURVIVOR_APPROACH_RADIUS,
    SURVIVOR_APPROACH_SPEED,
    SURVIVOR_COLOR,
    SURVIVOR_RADIUS,
    ZOMBIE_MODE_CHANGE_INTERVAL_MS,
    ZOMBIE_RADIUS,
    ZOMBIE_SEPARATION_DISTANCE,
    ZOMBIE_AGING_DURATION_FRAMES,
    ZOMBIE_AGING_MIN_SPEED_RATIO,
    ZOMBIE_SIGHT_RANGE,
    ZOMBIE_SPEED,
    ZOMBIE_WALL_DAMAGE,
    car_body_radius,
)
from .rng import get_rng

RNG = get_rng()


def circle_rect_collision(center: tuple[float, float], radius: float, rect_obj: rect.Rect) -> bool:
    """Return True if a circle overlaps the provided rectangle."""
    cx, cy = center
    closest_x = max(rect_obj.left, min(cx, rect_obj.right))
    closest_y = max(rect_obj.top, min(cy, rect_obj.bottom))
    dx = cx - closest_x
    dy = cy - closest_y
    return dx * dx + dy * dy <= radius * radius


# --- Camera Class ---
class Wall(pygame.sprite.Sprite):
    def __init__(
        self: Self,
        x: int,
        y: int,
        width: int,
        height: int,
        *,
        health: int = INTERNAL_WALL_HEALTH,
        color: tuple[int, int, int] = INTERNAL_WALL_COLOR,
        border_color: tuple[int, int, int] = INTERNAL_WALL_BORDER_COLOR,
        palette_category: str = "inner_wall",
        on_destroy: Callable[[Self], None] | None = None,
    ) -> None:
        super().__init__()
        safe_width = max(1, width)
        safe_height = max(1, height)
        self.image = pygame.Surface((safe_width, safe_height))
        self.base_color = color
        self.border_base_color = border_color
        self.palette_category = palette_category
        self.health = health
        self.max_health = max(1, health)
        self.on_destroy = on_destroy
        self.update_color()
        self.rect = self.image.get_rect(topleft=(x, y))

    def take_damage(self: Self, *, amount: int = 1) -> None:
        if self.health > 0:
            self.health -= amount
            self.update_color()
            if self.health <= 0:
                if self.on_destroy:
                    try:
                        self.on_destroy(self)
                    except Exception as exc:
                        print(f"Wall destroy callback failed: {exc}")
                self.kill()

    def update_color(self: Self) -> None:
        if self.health <= 0:
            self.image.fill((40, 40, 40))
            health_ratio = 0
        else:
            health_ratio = max(0, self.health / self.max_health)
            mix = (
                0.6 + 0.4 * health_ratio
            )  # keep at least 60% of the base color even when nearly destroyed
            r = int(self.base_color[0] * mix)
            g = int(self.base_color[1] * mix)
            b = int(self.base_color[2] * mix)
            self.image.fill((r, g, b))
        # Bright edge to separate walls from floor
        br = int(self.border_base_color[0] * (0.6 + 0.4 * health_ratio))
        bg = int(self.border_base_color[1] * (0.6 + 0.4 * health_ratio))
        bb = int(self.border_base_color[2] * (0.6 + 0.4 * health_ratio))
        pygame.draw.rect(self.image, (br, bg, bb), self.image.get_rect(), width=9)

    def set_palette_colors(
        self: Self,
        *,
        color: tuple[int, int, int],
        border_color: tuple[int, int, int],
        force: bool = False,
    ) -> None:
        """Update the wall's base colors to match the current ambient palette."""

        if not force and self.base_color == color and self.border_base_color == border_color:
            return
        self.base_color = color
        self.border_base_color = border_color
        self.update_color()


class SteelBeam(pygame.sprite.Sprite):
    """Single-cell obstacle that behaves like a tougher internal wall."""

    def __init__(
        self: Self, x: int, y: int, size: int, *, health: int = STEEL_BEAM_HEALTH
    ) -> None:
        super().__init__()
        # Slightly inset from the cell size so it reads as a separate object.
        margin = max(3, size // 14)
        inset_size = max(4, size - margin * 2)
        self.image = pygame.Surface((inset_size, inset_size), pygame.SRCALPHA)
        self.health = health
        self.max_health = max(1, health)
        self.base_color = STEEL_BEAM_COLOR
        self.line_color = STEEL_BEAM_LINE_COLOR
        self.update_color()
        self.rect = self.image.get_rect(center=(x + size // 2, y + size // 2))

    def take_damage(self: Self, *, amount: int = 1) -> None:
        if self.health > 0:
            self.health -= amount
            self.update_color()
            if self.health <= 0:
                self.kill()

    def update_color(self: Self) -> None:
        """Render a simple square with crossed diagonals that darkens as damaged."""
        self.image.fill((0, 0, 0, 0))
        if self.health <= 0:
            return
        health_ratio = max(0, self.health / self.max_health)
        fill_mix = 0.55 + 0.45 * health_ratio
        fill_color = tuple(int(c * fill_mix) for c in self.base_color)
        rect_obj = self.image.get_rect()
        pygame.draw.rect(self.image, fill_color, rect_obj)
        line_mix = 0.7 + 0.3 * health_ratio
        line_color = tuple(int(c * line_mix) for c in self.line_color)
        pygame.draw.rect(self.image, line_color, rect_obj, width=6)
        pygame.draw.line(
            self.image, line_color, rect_obj.topleft, rect_obj.bottomright, width=6
        )
        pygame.draw.line(
            self.image, line_color, rect_obj.topright, rect_obj.bottomleft, width=6
        )


class Camera:
    def __init__(self: Self, width: int, height: int) -> None:
        self.camera = pygame.Rect(0, 0, width, height)
        self.width = width
        self.height = height

    def apply(self: Self, entity: pygame.sprite.Sprite) -> rect.Rect:
        return entity.rect.move(self.camera.topleft)

    def apply_rect(self: Self, rect: rect.Rect) -> rect.Rect:
        return rect.move(self.camera.topleft)

    def update(self: Self, target: pygame.sprite.Sprite) -> None:
        x = -target.rect.centerx + int(SCREEN_WIDTH / 2)
        y = -target.rect.centery + int(SCREEN_HEIGHT / 2)
        x = max(-(self.width - SCREEN_WIDTH), min(0, x))
        y = max(-(self.height - SCREEN_HEIGHT), min(0, y))
        self.camera = pygame.Rect(x, y, self.width, self.height)


# --- Enums ---
class ZombieMode(Enum):
    CHASE = 1
    FLANK_X = 4
    FLANK_Y = 5


# --- Game Classes ---
class Player(pygame.sprite.Sprite):
    def __init__(self: Self, x: float, y: float) -> None:
        super().__init__()
        self.radius = PLAYER_RADIUS
        self.image = pygame.Surface(
            (self.radius * 2 + 2, self.radius * 2 + 2), pygame.SRCALPHA
        )
        pygame.draw.circle(
            self.image, BLUE, (self.radius + 1, self.radius + 1), self.radius
        )
        self.rect = self.image.get_rect(center=(x, y))
        self.speed = PLAYER_SPEED
        self.in_car = False
        self.x = float(self.rect.centerx)
        self.y = float(self.rect.centery)

    def move(self: Self, dx: float, dy: float, walls: pygame.sprite.Group) -> None:
        if self.in_car:
            return

        if dx != 0:
            self.x += dx
            self.x = min(LEVEL_WIDTH, max(0, self.x))
            self.rect.centerx = int(self.x)
            hit_list_x = pygame.sprite.spritecollide(self, walls, False)
            if hit_list_x:
                damage = max(1, PLAYER_WALL_DAMAGE // len(hit_list_x))
                for wall in hit_list_x:
                    if wall.alive():
                        wall.take_damage(amount=damage)
                self.x -= dx * 1.5
                self.rect.centerx = int(self.x)

        if dy != 0:
            self.y += dy
            self.y = min(LEVEL_HEIGHT, max(0, self.y))
            self.rect.centery = int(self.y)
            hit_list_y = pygame.sprite.spritecollide(self, walls, False)
            if hit_list_y:
                damage = max(1, PLAYER_WALL_DAMAGE // len(hit_list_y))
                for wall in hit_list_y:
                    if wall.alive():
                        wall.take_damage(amount=damage)
                self.y -= dy * 1.5
                self.rect.centery = int(self.y)

        self.rect.center = (int(self.x), int(self.y))


class Companion(pygame.sprite.Sprite):
    """Simple survivor sprite used in Stage 3."""

    def __init__(self: Self, x: float, y: float) -> None:
        super().__init__()
        self.radius = COMPANION_RADIUS
        self.image = pygame.Surface((self.radius * 2, self.radius * 2), pygame.SRCALPHA)
        pygame.draw.circle(
            self.image, COMPANION_COLOR, (self.radius, self.radius), self.radius
        )
        self.rect = self.image.get_rect(center=(int(x), int(y)))
        self.x = float(self.rect.centerx)
        self.y = float(self.rect.centery)
        self.following = False
        self.rescued = False

    def set_following(self: Self) -> None:
        if not self.rescued:
            self.following = True

    def mark_rescued(self: Self) -> None:
        self.following = False
        self.rescued = True

    def teleport(self: Self, pos: tuple[int, int]) -> None:
        """Reposition the companion (used for quiet respawns)."""
        self.x, self.y = float(pos[0]), float(pos[1])
        self.rect.center = (int(self.x), int(self.y))
        self.following = False

    def update_follow(
        self: Self, target_pos: tuple[float, float], walls: pygame.sprite.Group
    ) -> None:
        """Follow the target at a slightly slower speed than the player."""
        if self.rescued or not self.following:
            self.rect.center = (int(self.x), int(self.y))
            return

        dx = target_pos[0] - self.x
        dy = target_pos[1] - self.y
        dist = math.hypot(dx, dy)
        if dist <= 0:
            self.rect.center = (int(self.x), int(self.y))
            return

        move_x = (dx / dist) * COMPANION_FOLLOW_SPEED
        move_y = (dy / dist) * COMPANION_FOLLOW_SPEED

        if move_x != 0:
            self.x += move_x
            self.rect.centerx = int(self.x)
            if pygame.sprite.spritecollideany(self, walls):
                self.x -= move_x
                self.rect.centerx = int(self.x)
        if move_y != 0:
            self.y += move_y
            self.rect.centery = int(self.y)
            if pygame.sprite.spritecollideany(self, walls):
                self.y -= move_y
                self.rect.centery = int(self.y)

        # Avoid fully overlapping the player target
        overlap_radius = (self.radius + PLAYER_RADIUS) * 1.05
        dx_after = target_pos[0] - self.x
        dy_after = target_pos[1] - self.y
        dist_after = math.hypot(dx_after, dy_after)
        if dist_after > 0 and dist_after < overlap_radius:
            push_dist = overlap_radius - dist_after
            self.x -= (dx_after / dist_after) * push_dist
            self.y -= (dy_after / dist_after) * push_dist
            self.rect.center = (int(self.x), int(self.y))

        self.x = min(LEVEL_WIDTH, max(0, self.x))
        self.y = min(LEVEL_HEIGHT, max(0, self.y))
        self.rect.center = (int(self.x), int(self.y))


class Survivor(pygame.sprite.Sprite):
    """Civilians that gather near the player during Stage 4."""

    def __init__(self: Self, x: float, y: float) -> None:
        super().__init__()
        self.radius = SURVIVOR_RADIUS
        self.image = pygame.Surface((self.radius * 2, self.radius * 2), pygame.SRCALPHA)
        pygame.draw.circle(
            self.image, SURVIVOR_COLOR, (self.radius, self.radius), self.radius
        )
        self.rect = self.image.get_rect(center=(int(x), int(y)))
        self.x = float(self.rect.centerx)
        self.y = float(self.rect.centery)

    def update_behavior(
        self: Self, player_pos: tuple[int, int], walls: pygame.sprite.Group
    ) -> None:
        dx = player_pos[0] - self.x
        dy = player_pos[1] - self.y
        dist = math.hypot(dx, dy)
        if dist <= 0 or dist > SURVIVOR_APPROACH_RADIUS:
            return

        move_x = (dx / dist) * SURVIVOR_APPROACH_SPEED
        move_y = (dy / dist) * SURVIVOR_APPROACH_SPEED

        if move_x:
            self.x += move_x
            self.rect.centerx = int(self.x)
            if pygame.sprite.spritecollideany(self, walls):
                self.x -= move_x
                self.rect.centerx = int(self.x)
        if move_y:
            self.y += move_y
            self.rect.centery = int(self.y)
            if pygame.sprite.spritecollideany(self, walls):
                self.y -= move_y
                self.rect.centery = int(self.y)

        self.rect.center = (int(self.x), int(self.y))


def random_position_outside_building() -> tuple[int, int]:
    side = RNG.choice(["top", "bottom", "left", "right"])
    margin = 0
    if side == "top":
        x, y = RNG.randint(0, LEVEL_WIDTH), -margin
    elif side == "bottom":
        x, y = RNG.randint(0, LEVEL_WIDTH), LEVEL_HEIGHT + margin
    elif side == "left":
        x, y = -margin, RNG.randint(0, LEVEL_HEIGHT)
    else:
        x, y = LEVEL_WIDTH + margin, RNG.randint(0, LEVEL_HEIGHT)
    return x, y


class Zombie(pygame.sprite.Sprite):
    def __init__(
        self: Self,
        *,
        start_pos: tuple[int, int] | None = None,
        hint_pos: tuple[float, float] | None = None,
        speed: float = ZOMBIE_SPEED,
    ) -> None:
        super().__init__()
        self.radius = ZOMBIE_RADIUS
        self.image = pygame.Surface((self.radius * 2, self.radius * 2), pygame.SRCALPHA)
        pygame.draw.circle(self.image, RED, (self.radius, self.radius), self.radius)
        if start_pos:
            x, y = start_pos
        elif hint_pos:
            points = [random_position_outside_building() for _ in range(5)]
            points.sort(
                key=lambda p: math.hypot(p[0] - hint_pos[0], p[1] - hint_pos[1])
            )
            x, y = points[0]
        else:
            x, y = random_position_outside_building()
        self.rect = self.image.get_rect(center=(x, y))
        jitter = (
            FAST_ZOMBIE_SPEED_JITTER
            if speed > ZOMBIE_SPEED
            else NORMAL_ZOMBIE_SPEED_JITTER
        )
        base_speed = speed + RNG.uniform(-jitter, jitter)
        self.initial_speed = base_speed
        self.speed = base_speed
        self.x = float(self.rect.centerx)
        self.y = float(self.rect.centery)
        self.mode = RNG.choice(list(ZombieMode))
        self.last_mode_change_time = pygame.time.get_ticks()
        self.mode_change_interval = ZOMBIE_MODE_CHANGE_INTERVAL_MS + RNG.randint(
            -1000, 1000
        )
        self.was_in_sight = False
        self.carbonized = False
        self.age_frames = 0

    def change_mode(self: Self, *, force_mode: ZombieMode | None = None) -> None:
        if force_mode:
            self.mode = force_mode
        else:
            possible_modes = list(ZombieMode)
            self.mode = RNG.choice(possible_modes)
        self.last_mode_change_time = pygame.time.get_ticks()
        self.mode_change_interval = ZOMBIE_MODE_CHANGE_INTERVAL_MS + RNG.randint(
            -1000, 1000
        )

    def _calculate_movement(
        self: Self, player_center: tuple[int, int]
    ) -> tuple[float, float]:
        move_x, move_y = 0, 0
        dx_target = player_center[0] - self.x
        dy_target = player_center[1] - self.y
        dist = math.hypot(dx_target, dy_target)
        if self.mode == ZombieMode.CHASE:
            if dist > 0:
                move_x, move_y = (
                    (dx_target / dist) * self.speed,
                    (dy_target / dist) * self.speed,
                )
        elif self.mode == ZombieMode.FLANK_X:
            if dist > 0:
                move_x = (
                    (dx_target / abs(dx_target) if dx_target != 0 else 0)
                    * self.speed
                    * 0.8
                )
            move_y = RNG.uniform(-self.speed * 0.6, self.speed * 0.6)
        elif self.mode == ZombieMode.FLANK_Y:
            move_x = RNG.uniform(-self.speed * 0.6, self.speed * 0.6)
            if dist > 0:
                move_y = (
                    (dy_target / abs(dy_target) if dy_target != 0 else 0)
                    * self.speed
                    * 0.8
                )
        return move_x, move_y

    def _handle_wall_collision(
        self: Self, next_x: float, next_y: float, walls: list[Wall]
    ) -> tuple[float, float]:
        final_x, final_y = next_x, next_y

        possible_walls = [
            w
            for w in walls
            if abs(w.rect.centerx - self.x) < 100 and abs(w.rect.centery - self.y) < 100
        ]

        temp_rect = self.rect.copy()
        temp_rect.centerx = int(next_x)
        temp_rect.centery = int(self.y)
        for wall in possible_walls:
            if temp_rect.colliderect(wall.rect):
                if wall.alive():
                    wall.take_damage(amount=ZOMBIE_WALL_DAMAGE)
                if wall.alive():
                    final_x = self.x
                    break

        temp_rect.centerx = int(final_x)
        temp_rect.centery = int(next_y)
        for wall in possible_walls:
            if temp_rect.colliderect(wall.rect):
                if wall.alive():
                    wall.take_damage(amount=ZOMBIE_WALL_DAMAGE)
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
        next_x = self.x + move_x
        next_y = self.y + move_y

        closest: Zombie | None = None
        closest_dist = ZOMBIE_SEPARATION_DISTANCE
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
            dist = math.hypot(dx, dy)
            if dist < closest_dist:
                closest = other
                closest_dist = dist

        if closest is None:
            return move_x, move_y

        away_dx = next_x - closest.x
        away_dy = next_y - closest.y
        away_dist = math.hypot(away_dx, away_dy)
        if away_dist == 0:
            angle = RNG.uniform(0, 2 * math.pi)
            away_dx, away_dy = math.cos(angle), math.sin(angle)
            away_dist = 1

        move_x = (away_dx / away_dist) * self.speed
        move_y = (away_dy / away_dist) * self.speed
        return move_x, move_y

    def _apply_aging(self: Self) -> None:
        """Slowly reduce zombie speed over time to simulate decay."""
        if ZOMBIE_AGING_DURATION_FRAMES <= 0:
            return
        if self.age_frames < ZOMBIE_AGING_DURATION_FRAMES:
            self.age_frames += 1
        progress = min(1.0, self.age_frames / ZOMBIE_AGING_DURATION_FRAMES)
        slowdown_ratio = 1.0 - progress * (1.0 - ZOMBIE_AGING_MIN_SPEED_RATIO)
        self.speed = self.initial_speed * slowdown_ratio

    def update(
        self: Self,
        player_center: tuple[int, int],
        walls: list[Wall],
        nearby_zombies: Iterable[Zombie],
    ) -> None:
        if self.carbonized:
            return
        self._apply_aging()
        now = pygame.time.get_ticks()
        dx_target = player_center[0] - self.x
        dy_target = player_center[1] - self.y
        dist_to_player = math.hypot(dx_target, dy_target)
        is_in_sight = dist_to_player <= ZOMBIE_SIGHT_RANGE
        if is_in_sight:
            if self.mode != ZombieMode.CHASE:
                self.change_mode(force_mode=ZombieMode.CHASE)
            self.was_in_sight = True
        elif self.was_in_sight:
            self.change_mode()
            self.was_in_sight = False
        elif now - self.last_mode_change_time > self.mode_change_interval:
            self.change_mode()
        move_x, move_y = self._calculate_movement(player_center)
        move_x, move_y = self._avoid_other_zombies(move_x, move_y, nearby_zombies)
        final_x, final_y = self._handle_wall_collision(
            self.x + move_x, self.y + move_y, walls
        )

        if not (0 <= final_x < LEVEL_WIDTH and 0 <= final_y < LEVEL_HEIGHT):
            final_x, final_y = random_position_outside_building()

        self.x = final_x
        self.y = final_y
        self.rect.center = (int(self.x), int(self.y))

    def carbonize(self: Self) -> None:
        if self.carbonized:
            return
        self.carbonized = True
        self.speed = 0
        self.image.fill((0, 0, 0, 0))
        color = (80, 80, 80)
        pygame.draw.circle(self.image, color, (self.radius, self.radius), self.radius)
        pygame.draw.circle(self.image, (30, 30, 30), (self.radius, self.radius), self.radius, width=2)


class Car(pygame.sprite.Sprite):
    def __init__(self: Self, x: int, y: int) -> None:
        super().__init__()
        self.original_image = pygame.Surface((CAR_WIDTH, CAR_HEIGHT), pygame.SRCALPHA)
        self.base_color = YELLOW
        self.image = self.original_image.copy()
        self.rect = self.image.get_rect(center=(x, y))
        self.speed = CAR_SPEED
        self.angle = 0
        self.x = float(self.rect.centerx)
        self.y = float(self.rect.centery)
        self.health = CAR_HEALTH
        self.max_health = CAR_HEALTH
        self.collision_radius = car_body_radius(CAR_WIDTH, CAR_HEIGHT)
        self.update_color()

    def take_damage(self: Self, amount: int) -> None:
        if self.health > 0:
            self.health -= amount
            self.update_color()

    def update_color(self: Self) -> None:
        health_ratio = max(0, self.health / self.max_health)
        color = YELLOW
        if health_ratio < 0.6:
            color = ORANGE
        if health_ratio < 0.3:
            color = DARK_RED
        self.original_image.fill((0, 0, 0, 0))

        body_rect = pygame.Rect(1, 4, CAR_WIDTH - 2, CAR_HEIGHT - 8)
        front_cap_height = max(8, body_rect.height // 3)
        front_cap = pygame.Rect(
            body_rect.left, body_rect.top, body_rect.width, front_cap_height
        )
        windshield_rect = pygame.Rect(
            body_rect.left + 4,
            body_rect.top + 3,
            body_rect.width - 8,
            front_cap_height - 5,
        )

        trim_color = tuple(int(c * 0.55) for c in color)
        front_cap_color = tuple(min(255, int(c * 1.08)) for c in color)
        body_color = color
        window_color = (70, 110, 150)
        wheel_color = (35, 35, 35)

        wheel_width = CAR_WIDTH // 3
        wheel_height = 6
        for y in (body_rect.top + 4, body_rect.bottom - wheel_height - 4):
            left_wheel = pygame.Rect(2, y, wheel_width, wheel_height)
            right_wheel = pygame.Rect(
                CAR_WIDTH - wheel_width - 2, y, wheel_width, wheel_height
            )
            pygame.draw.rect(
                self.original_image, wheel_color, left_wheel, border_radius=3
            )
            pygame.draw.rect(
                self.original_image, wheel_color, right_wheel, border_radius=3
            )

        pygame.draw.rect(self.original_image, body_color, body_rect, border_radius=4)
        pygame.draw.rect(
            self.original_image, trim_color, body_rect, width=2, border_radius=4
        )
        pygame.draw.rect(
            self.original_image, front_cap_color, front_cap, border_radius=10
        )
        pygame.draw.rect(
            self.original_image, trim_color, front_cap, width=2, border_radius=10
        )
        pygame.draw.rect(
            self.original_image, window_color, windshield_rect, border_radius=4
        )

        headlight_color = (245, 245, 200)
        for x in (front_cap.left + 5, front_cap.right - 5):
            pygame.draw.circle(
                self.original_image, headlight_color, (x, body_rect.top + 5), 2
            )
        grille_rect = pygame.Rect(front_cap.centerx - 6, front_cap.top + 2, 12, 6)
        pygame.draw.rect(self.original_image, trim_color, grille_rect, border_radius=2)
        tail_light_color = (255, 80, 50)
        for x in (body_rect.left + 5, body_rect.right - 5):
            pygame.draw.rect(
                self.original_image,
                tail_light_color,
                (x - 2, body_rect.bottom - 5, 4, 3),
                border_radius=1,
            )
        self.image = pygame.transform.rotate(self.original_image, self.angle)
        old_center = self.rect.center
        self.rect = self.image.get_rect(center=old_center)

    def move(self: Self, dx: float, dy: float, walls: Iterable[Wall]) -> None:
        if self.health <= 0:
            return
        if dx == 0 and dy == 0:
            self.rect.center = (int(self.x), int(self.y))
            return
        target_angle = math.degrees(math.atan2(-dy, dx)) - 90
        self.angle = target_angle
        self.image = pygame.transform.rotate(self.original_image, self.angle)
        old_center = (self.x, self.y)
        self.rect = self.image.get_rect(center=old_center)
        new_x = self.x + dx
        new_y = self.y + dy

        hit_walls = []
        possible_walls = [
            w
            for w in walls
            if abs(w.rect.centery - self.y) < 100 and abs(w.rect.centerx - new_x) < 100
        ]
        car_center = (new_x, new_y)
        for wall in possible_walls:
            if circle_rect_collision(car_center, self.collision_radius, wall.rect):
                hit_walls.append(wall)
        if hit_walls:
            self.take_damage(CAR_WALL_DAMAGE)
            hit_walls.sort(
                key=lambda w: (w.rect.centery - self.y) ** 2
                + (w.rect.centerx - self.x) ** 2
            )
            nearest_wall = hit_walls[0]
            new_x += (self.x - nearest_wall.rect.centerx) * 1.2
            new_y += (self.y - nearest_wall.rect.centery) * 1.2

        self.x = new_x
        self.y = new_y
        self.rect.center = (int(self.x), int(self.y))


class FuelCan(pygame.sprite.Sprite):
    """Simple fuel can collectible used in Stage 2."""

    def __init__(self: Self, x: int, y: int) -> None:
        super().__init__()
        self.image = pygame.Surface((FUEL_CAN_WIDTH, FUEL_CAN_HEIGHT), pygame.SRCALPHA)

        # Jerrycan silhouette with cut corner
        w, h = FUEL_CAN_WIDTH, FUEL_CAN_HEIGHT
        body_pts = [
            (1, 4),
            (w - 2, 4),
            (w - 2, h - 2),
            (1, h - 2),
            (1, 8),
            (4, 4),
        ]
        pygame.draw.polygon(self.image, YELLOW, body_pts)
        pygame.draw.polygon(self.image, BLACK, body_pts, width=2)

        cap_size = max(2, w // 4)
        cap_rect = pygame.Rect(w - cap_size - 2, 1, cap_size, 3)
        pygame.draw.rect(self.image, YELLOW, cap_rect, border_radius=1)
        pygame.draw.rect(self.image, BLACK, cap_rect, width=1, border_radius=1)

        # Cross brace accent
        brace_color = (240, 200, 40)
        pygame.draw.line(self.image, brace_color, (3, h // 2), (w - 4, h // 2), width=2)
        pygame.draw.line(self.image, BLACK, (3, h // 2), (w - 4, h // 2), width=1)

        self.rect = self.image.get_rect(center=(x, y))


class Flashlight(pygame.sprite.Sprite):
    """Flashlight pickup that expands the player's visible radius when collected."""

    def __init__(self: Self, x: int, y: int) -> None:
        super().__init__()
        self.image = pygame.Surface(
            (FLASHLIGHT_WIDTH, FLASHLIGHT_HEIGHT), pygame.SRCALPHA
        )

        body_color = (230, 200, 70)
        trim_color = (80, 70, 40)
        head_color = (200, 180, 90)
        beam_color = (255, 240, 180, 150)

        body_rect = pygame.Rect(1, 2, FLASHLIGHT_WIDTH - 4, FLASHLIGHT_HEIGHT - 4)
        head_rect = pygame.Rect(
            body_rect.right - 3, body_rect.top - 1, 4, body_rect.height + 2
        )
        beam_points = [
            (head_rect.right + 4, head_rect.centery),
            (head_rect.right + 2, head_rect.top),
            (head_rect.right + 2, head_rect.bottom),
        ]

        pygame.draw.rect(self.image, body_color, body_rect, border_radius=2)
        pygame.draw.rect(self.image, trim_color, body_rect, width=1, border_radius=2)
        pygame.draw.rect(self.image, head_color, head_rect, border_radius=2)
        pygame.draw.rect(self.image, trim_color, head_rect, width=1, border_radius=2)
        pygame.draw.polygon(self.image, beam_color, beam_points)

        self.rect = self.image.get_rect(center=(x, y))


__all__ = [
    "Wall",
    "SteelBeam",
    "Camera",
    "ZombieMode",
    "Player",
    "Companion",
    "Survivor",
    "Zombie",
    "Car",
    "FuelCan",
    "Flashlight",
    "random_position_outside_building",
]
