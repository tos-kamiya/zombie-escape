from typing import Iterable, List, Optional, Self, Tuple
from dataclasses import dataclass
import random
import copy
import math
import sys
import traceback  # For error reporting
from enum import Enum  # For Zombie Modes

import pygame
from pygame import rect, sprite, surface, time

from .level_blueprints import GRID_COLS, GRID_ROWS, TILE_SIZE, choose_blueprint
from .config import DEFAULT_CONFIG, load_config, save_config
try:
    from .__about__ import __version__
except:
    __version__ = "0.0.0-unknown"

# --- Constants ---
DEFAULT_SCREEN_WIDTH = 800
DEFAULT_SCREEN_HEIGHT = 600
WINDOW_SCALE_MIN = 0.5
WINDOW_SCALE_MAX = 2.0
SCREEN_WIDTH = DEFAULT_SCREEN_WIDTH  # Logical render width
SCREEN_HEIGHT = DEFAULT_SCREEN_HEIGHT  # Logical render height
current_window_scale = 1.0  # Applied to the OS window only
FPS = 60
STATUS_BAR_HEIGHT = 28

# Level dimensions are driven by the blueprint grid.
LEVEL_GRID_COLS = GRID_COLS
LEVEL_GRID_ROWS = GRID_ROWS
CELL_SIZE = TILE_SIZE
LEVEL_WIDTH = LEVEL_GRID_COLS * CELL_SIZE
LEVEL_HEIGHT = LEVEL_GRID_ROWS * CELL_SIZE

# Colors
WHITE = (255, 255, 255)
BLACK = (0, 0, 0)
RED = (255, 0, 0)
GREEN = (0, 255, 0)
BLUE = (0, 0, 255)
GRAY = (100, 100, 100)
LIGHT_GRAY = (200, 200, 200)
YELLOW = (255, 255, 0)
ORANGE = (255, 165, 0)
DARK_RED = (139, 0, 0)

# Player settings
PLAYER_RADIUS = 11
PLAYER_SPEED = 2.8
FOV_RADIUS = 180
FOG_RADIUS_SCALE = 1.2
FOG_MAX_RADIUS_FACTOR = 1.55
FOG_HATCH_THICKNESS = 9
FOG_HATCH_PIXEL_SCALE = 3


@dataclass(frozen=True)
class FogRing:
    radius_factor: float
    thickness: int = FOG_HATCH_THICKNESS


class AttrMapMixin:
    """Mixin to offer dict-like access to dataclass attributes."""

    def __getitem__(self, key):
        return getattr(self, key)

    def __setitem__(self, key, value):
        setattr(self, key, value)

    def get(self, key, default=None):
        return getattr(self, key, default)

    def items(self):
        return self.__dict__.items()


@dataclass
class Areas(AttrMapMixin):
    """Container for level area rectangles with dict-like access."""

    outer_rect: Tuple[int, int, int, int]
    inner_rect: Tuple[int, int, int, int]
    outside_rects: list[pygame.Rect]
    walkable_cells: list[pygame.Rect]

    def __getitem__(self, key):
        return getattr(self, key)

    def __setitem__(self, key, value):
        setattr(self, key, value)

    def get(self, key, default=None):
        return getattr(self, key, default)


@dataclass
class ProgressState(AttrMapMixin):
    """Game progress/state flags."""

    game_over: bool
    game_won: bool
    overview_surface: surface.Surface | None
    scaled_overview: surface.Surface | None
    overview_created: bool
    last_zombie_spawn_time: int
    footprints: list
    last_footprint_pos: tuple | None
    elapsed_play_ms: int
    has_fuel: bool
    hint_expires_at: int
    hint_target_type: str | None
    fuel_message_until: int


@dataclass
class Groups(AttrMapMixin):
    """Sprite groups container with dict-like access."""

    all_sprites: sprite.LayeredUpdates
    wall_group: sprite.Group
    zombie_group: sprite.Group


@dataclass
class GameData:
    """Lightweight container for game state with dict-like access for compatibility."""

    state: "ProgressState"
    groups: Groups
    camera: "Camera"
    areas: "Areas"
    fog: dict
    config: dict
    stage: "Stage"
    fuel: Optional["FuelCan"] = None
    player: Optional["Player"] = None
    car: Optional["Car"] = None

    def __getitem__(self, key):
        return getattr(self, key)

    def __setitem__(self, key, value):
        setattr(self, key, value)

    def get(self, key, default=None):
        return getattr(self, key, default)

    def __contains__(self, key):
        return hasattr(self, key)


FOG_RINGS = [
    FogRing(radius_factor=0.82, thickness=2),
    FogRing(radius_factor=0.99, thickness=4),
    FogRing(radius_factor=1.16, thickness=6),
    FogRing(radius_factor=1.33, thickness=8),
    FogRing(radius_factor=1.5, thickness=12),
]
FOG_COLOR = (0, 0, 0, 255)

# Footprint settings
FOOTPRINT_RADIUS = 5
FOOTPRINT_OVERVIEW_RADIUS = 8
FOOTPRINT_COLOR = (110, 200, 255)
FOOTPRINT_STEP_DISTANCE = 80
FOOTPRINT_LIFETIME_MS = 135000
FOOTPRINT_MAX = 320
FOOTPRINT_MIN_FADE = 0.3

# Zombie settings
ZOMBIE_RADIUS = 11
ZOMBIE_SPEED = 1.2
NORMAL_ZOMBIE_SPEED_JITTER = 0.3
ZOMBIE_SPAWN_DELAY_MS = 5000
MAX_ZOMBIES = 200
INITIAL_ZOMBIES_INSIDE = 15
ZOMBIE_MODE_CHANGE_INTERVAL_MS = 5000
ZOMBIE_SIGHT_RANGE = FOV_RADIUS * 2.0
FAST_ZOMBIE_RATIO_DEFAULT = 0.1
FAST_ZOMBIE_BASE_SPEED = PLAYER_SPEED * 0.85
FAST_ZOMBIE_SPEED_JITTER = 0.15
ZOMBIE_SEPARATION_DISTANCE = ZOMBIE_RADIUS * 2.2


@dataclass(frozen=True)
class Stage:
    id: str
    name: str
    description: str
    available: bool = True
    requires_fuel: bool = False


# Stage metadata (stage 2 placeholder for fuel flow coming soon)
STAGES = [
    Stage(
        id="stage1",
        name="Stage 1: Find the Car",
        description="Locate the car and drive out to escape.",
        available=True,
        requires_fuel=False,
    ),
    Stage(
        id="stage2",
        name="Stage 2: Fuel Run",
        description="Find fuel, bring it to the car, then escape.",
        available=True,
        requires_fuel=True,
    ),
]
DEFAULT_STAGE_ID = "stage1"

# Car settings
CAR_WIDTH = 30
CAR_HEIGHT = 50
CAR_SPEED = 4
CAR_HEALTH = 20
CAR_WALL_DAMAGE = 1
CAR_ZOMBIE_DAMAGE = 1
CAR_HINT_DELAY_MS_DEFAULT = 180000

# Fuel settings (Stage 2)
FUEL_CAN_WIDTH = 22
FUEL_CAN_HEIGHT = 30
FUEL_PICKUP_RADIUS = 24
FUEL_HINT_DURATION_MS = 1600

# Wall settings
INTERNAL_WALL_GRID_SNAP = CELL_SIZE
INTERNAL_WALL_HEALTH = 40
INTERNAL_WALL_COLOR = (99, 88, 70)
INTERNAL_WALL_BORDER_COLOR = (105, 93, 74)
OUTER_WALL_HEALTH = 9999
OUTER_WALL_COLOR = (122, 114, 102)
OUTER_WALL_BORDER_COLOR = (120, 112, 100)
FLOOR_COLOR_PRIMARY = (41, 46, 51)
FLOOR_COLOR_SECONDARY = (48, 54, 61)
FLOOR_COLOR_OUTSIDE = (30, 45, 30)


# --- Window scaling helpers ---
def apply_window_scale(scale: float, game_data: Optional[GameData] = None) -> surface.Surface:
    """Resize the OS window; the logical render surface stays at the default size."""
    global current_window_scale

    clamped_scale = max(WINDOW_SCALE_MIN, min(WINDOW_SCALE_MAX, scale))
    current_window_scale = clamped_scale

    window_width = max(1, int(DEFAULT_SCREEN_WIDTH * current_window_scale))
    window_height = max(1, int(DEFAULT_SCREEN_HEIGHT * current_window_scale))

    new_window = pygame.display.set_mode((window_width, window_height))
    pygame.display.set_caption(f"Zombie Escape v{__version__} ({window_width}x{window_height})")

    if game_data is not None:
        # Invalidate cached overview so it can be re-scaled next time it's drawn
        game_data.state.overview_created = False

    return new_window


def nudge_window_scale(multiplier: float, game_data: Optional[dict] = None) -> surface.Surface:
    """Change window scale relative to the current setting."""
    target_scale = current_window_scale * multiplier
    return apply_window_scale(target_scale, game_data)


def present(logical_surface: surface.Surface) -> None:
    """Scale the logical surface to the current window and flip buffers."""
    window = pygame.display.get_surface()
    if window is None:
        return
    window_size = window.get_size()
    if window_size == logical_surface.get_size():
        window.blit(logical_surface, (0, 0))
    else:
        pygame.transform.smoothscale(logical_surface, window_size, window)
    pygame.display.flip()


# --- Camera Class ---
class Wall(pygame.sprite.Sprite):
    def __init__(
        self: Self,
        x: int,
        y: int,
        width: int,
        height: int,
        health: int = INTERNAL_WALL_HEALTH,
        color: Tuple[int, int, int] = INTERNAL_WALL_COLOR,
        border_color: Tuple[int, int, int] = INTERNAL_WALL_BORDER_COLOR,
    ) -> None:
        super().__init__()
        safe_width = max(1, width)
        safe_height = max(1, height)
        self.image = pygame.Surface((safe_width, safe_height))
        self.base_color = color
        self.border_base_color = border_color
        self.health = health
        self.max_health = max(1, health)
        self.update_color()
        self.rect = self.image.get_rect(topleft=(x, y))

    def take_damage(self: Self, amount: int = 1) -> None:
        if self.health > 0:
            self.health -= amount
            self.update_color()
            if self.health <= 0:
                self.kill()

    def update_color(self: Self) -> None:
        if self.health <= 0:
            self.image.fill((40, 40, 40))
            health_ratio = 0
        else:
            health_ratio = max(0, self.health / self.max_health)
            mix = 0.6 + 0.4 * health_ratio  # keep at least 60% of the base color even when nearly destroyed
            r = int(self.base_color[0] * mix)
            g = int(self.base_color[1] * mix)
            b = int(self.base_color[2] * mix)
            self.image.fill((r, g, b))
        # Bright edge to separate walls from floor
        br = int(self.border_base_color[0] * (0.6 + 0.4 * health_ratio))
        bg = int(self.border_base_color[1] * (0.6 + 0.4 * health_ratio))
        bb = int(self.border_base_color[2] * (0.6 + 0.4 * health_ratio))
        pygame.draw.rect(self.image, (br, bg, bb), self.image.get_rect(), width=18)


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
        self.image = pygame.Surface((self.radius * 2 + 2, self.radius * 2 + 2), pygame.SRCALPHA)
        pygame.draw.circle(self.image, BLUE, (self.radius + 1, self.radius + 1), self.radius)
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
                damage = max(1, 4 // len(hit_list_x))
                for wall in hit_list_x:
                    wall.take_damage(damage)
                self.x -= dx * 1.5
                self.rect.centerx = int(self.x)

        if dy != 0:
            self.y += dy
            self.y = min(LEVEL_HEIGHT, max(0, self.y))
            self.rect.centery = int(self.y)
            hit_list_y = pygame.sprite.spritecollide(self, walls, False)
            if hit_list_y:
                damage = max(1, 4 // len(hit_list_y))
                for wall in hit_list_y:
                    if wall.alive():
                        wall.take_damage()
                self.y -= dy * 1.5
                self.rect.centery = int(self.y)

        self.rect.center = (int(self.x), int(self.y))


def random_position_outside_building() -> Tuple[int, int]:
    side = random.choice(["top", "bottom", "left", "right"])
    margin = 0
    if side == "top":
        x, y = random.randint(0, LEVEL_WIDTH), -margin
    elif side == "bottom":
        x, y = random.randint(0, LEVEL_WIDTH), LEVEL_HEIGHT + margin
    elif side == "left":
        x, y = -margin, random.randint(0, LEVEL_HEIGHT)
    else:
        x, y = LEVEL_WIDTH + margin, random.randint(0, LEVEL_HEIGHT)
    return x, y


def create_zombie(config, start_pos: Optional[Tuple[int, int]] = None, hint_pos: Optional[Tuple[float, float]] = None) -> "Zombie":
    """Factory to create zombies with optional fast variants."""
    fast_conf = config.get("fast_zombies", {}) if config else {}
    fast_enabled = fast_conf.get("enabled", True)
    ratio = fast_conf.get("ratio", FAST_ZOMBIE_RATIO_DEFAULT)
    ratio = max(0.0, min(1.0, ratio))
    is_fast = fast_enabled and random.random() < ratio
    base_speed = FAST_ZOMBIE_BASE_SPEED if is_fast else ZOMBIE_SPEED
    base_speed = min(base_speed, PLAYER_SPEED - 0.05)
    return Zombie(start_pos=start_pos, hint_pos=hint_pos, speed_override=base_speed, is_fast=is_fast)


class Zombie(pygame.sprite.Sprite):
    def __init__(
        self: Self,
        start_pos: Optional[Tuple[int, int]] = None,
        hint_pos: Optional[Tuple[float, float]] = None,
        speed_override: Optional[float] = None,
        is_fast: bool = False,
    ) -> None:
        super().__init__()
        self.radius = ZOMBIE_RADIUS
        self.image = pygame.Surface((self.radius * 2, self.radius * 2), pygame.SRCALPHA)
        pygame.draw.circle(self.image, RED, (self.radius, self.radius), self.radius)
        if start_pos:
            x, y = start_pos
        elif hint_pos:
            points = [random_position_outside_building() for _ in range(5)]
            points.sort(key=lambda p: math.hypot(p[0] - hint_pos[0], p[1] - hint_pos[1]))
            x, y = points[0]
        else:
            x, y = random_position_outside_building()
        self.rect = self.image.get_rect(center=(x, y))
        base_speed = speed_override if speed_override is not None else ZOMBIE_SPEED
        jitter = FAST_ZOMBIE_SPEED_JITTER if is_fast else NORMAL_ZOMBIE_SPEED_JITTER
        self.speed = base_speed + random.uniform(-jitter, jitter)
        self.x = float(self.rect.centerx)
        self.y = float(self.rect.centery)
        self.mode = random.choice(list(ZombieMode))
        self.last_mode_change_time = pygame.time.get_ticks()
        self.mode_change_interval = ZOMBIE_MODE_CHANGE_INTERVAL_MS + random.randint(-1000, 1000)
        self.was_in_sight = False

    def change_mode(self: Self, force_mode: Optional[ZombieMode] = None) -> None:
        if force_mode:
            self.mode = force_mode
        else:
            possible_modes = list(ZombieMode)
            self.mode = random.choice(possible_modes)
        self.last_mode_change_time = pygame.time.get_ticks()
        self.mode_change_interval = ZOMBIE_MODE_CHANGE_INTERVAL_MS + random.randint(-1000, 1000)

    def _calculate_movement(self: Self, player_center: Tuple[int, int]) -> Tuple[float, float]:
        move_x, move_y = 0, 0
        dx_target = player_center[0] - self.x
        dy_target = player_center[1] - self.y
        dist = math.hypot(dx_target, dy_target)
        if self.mode == ZombieMode.CHASE:
            if dist > 0:
                move_x, move_y = (dx_target / dist) * self.speed, (dy_target / dist) * self.speed
        elif self.mode == ZombieMode.FLANK_X:
            if dist > 0:
                move_x = (dx_target / abs(dx_target) if dx_target != 0 else 0) * self.speed * 0.8
            move_y = random.uniform(-self.speed * 0.6, self.speed * 0.6)
        elif self.mode == ZombieMode.FLANK_Y:
            move_x = random.uniform(-self.speed * 0.6, self.speed * 0.6)
            if dist > 0:
                move_y = (dy_target / abs(dy_target) if dy_target != 0 else 0) * self.speed * 0.8
        return move_x, move_y

    def _handle_wall_collision(self: Self, next_x: float, next_y: float, walls: List[Wall]) -> Tuple[float, float]:
        final_x, final_y = next_x, next_y

        possible_walls = [w for w in walls if abs(w.rect.centerx - self.x) < 100 and abs(w.rect.centery - self.y) < 100]

        temp_rect = self.rect.copy()
        temp_rect.centerx = int(next_x)
        temp_rect.centery = int(self.y)
        for wall in possible_walls:
            if temp_rect.colliderect(wall.rect):
                final_x = self.x
                break

        temp_rect.centerx = int(final_x)
        temp_rect.centery = int(next_y)
        for wall in possible_walls:
            if temp_rect.colliderect(wall.rect):
                final_y = self.y
                break

        return final_x, final_y

    def _avoid_other_zombies(
        self: Self, move_x: float, move_y: float, zombies: Iterable["Zombie"]
    ) -> Tuple[float, float]:
        """If another zombie is too close, steer directly away from the closest one."""
        next_x = self.x + move_x
        next_y = self.y + move_y

        closest: Optional["Zombie"] = None
        closest_dist = ZOMBIE_SEPARATION_DISTANCE
        for other in zombies:
            if other is self or not other.alive():
                continue
            dx = other.x - next_x
            dy = other.y - next_y
            if abs(dx) > ZOMBIE_SEPARATION_DISTANCE or abs(dy) > ZOMBIE_SEPARATION_DISTANCE:
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
            angle = random.uniform(0, 2 * math.pi)
            away_dx, away_dy = math.cos(angle), math.sin(angle)
            away_dist = 1

        move_x = (away_dx / away_dist) * self.speed
        move_y = (away_dy / away_dist) * self.speed
        return move_x, move_y

    def update(self: Self, player_center: Tuple[int, int], walls: List[Wall], zombies: Iterable["Zombie"]) -> None:
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
        move_x, move_y = self._avoid_other_zombies(move_x, move_y, zombies)
        final_x, final_y = self._handle_wall_collision(self.x + move_x, self.y + move_y, walls)

        if not (0 <= final_x < LEVEL_WIDTH and 0 <= final_y < LEVEL_HEIGHT):
            final_x, final_y = random_position_outside_building()

        self.x = final_x
        self.y = final_y
        self.rect.center = (int(self.x), int(self.y))


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
        self.update_color()

    def take_damage(self, amount):
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
        front_cap = pygame.Rect(body_rect.left, body_rect.top, body_rect.width, front_cap_height)
        windshield_rect = pygame.Rect(body_rect.left + 4, body_rect.top + 3, body_rect.width - 8, front_cap_height - 5)

        trim_color = tuple(int(c * 0.55) for c in color)
        front_cap_color = tuple(min(255, int(c * 1.08)) for c in color)
        body_color = color
        window_color = (70, 110, 150)
        wheel_color = (35, 35, 35)

        wheel_width = CAR_WIDTH // 3
        wheel_height = 6
        for y in (body_rect.top + 4, body_rect.bottom - wheel_height - 4):
            left_wheel = pygame.Rect(2, y, wheel_width, wheel_height)
            right_wheel = pygame.Rect(CAR_WIDTH - wheel_width - 2, y, wheel_width, wheel_height)
            pygame.draw.rect(self.original_image, wheel_color, left_wheel, border_radius=3)
            pygame.draw.rect(self.original_image, wheel_color, right_wheel, border_radius=3)

        pygame.draw.rect(self.original_image, body_color, body_rect, border_radius=4)
        pygame.draw.rect(self.original_image, trim_color, body_rect, width=2, border_radius=4)
        pygame.draw.rect(self.original_image, front_cap_color, front_cap, border_radius=10)
        pygame.draw.rect(self.original_image, trim_color, front_cap, width=2, border_radius=10)
        pygame.draw.rect(self.original_image, window_color, windshield_rect, border_radius=4)

        headlight_color = (245, 245, 200)
        for x in (front_cap.left + 5, front_cap.right - 5):
            pygame.draw.circle(self.original_image, headlight_color, (x, body_rect.top + 5), 2)
        grille_rect = pygame.Rect(front_cap.centerx - 6, front_cap.top + 2, 12, 6)
        pygame.draw.rect(self.original_image, trim_color, grille_rect, border_radius=2)
        tail_light_color = (255, 80, 50)
        for x in (body_rect.left + 5, body_rect.right - 5):
            pygame.draw.rect(self.original_image, tail_light_color, (x - 2, body_rect.bottom - 5, 4, 3), border_radius=1)
        self.image = pygame.transform.rotate(self.original_image, self.angle)
        old_center = self.rect.center
        self.rect = self.image.get_rect(center=old_center)

    def move(self, dx, dy, walls):
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

        temp_rect = self.rect.copy()
        temp_rect.centerx = int(new_x)
        temp_rect.centery = int(new_y)
        hit_walls = []
        possible_walls = [w for w in walls if abs(w.rect.centery - self.y) < 100 and abs(w.rect.centerx - new_x) < 100]
        for wall in possible_walls:
            if temp_rect.colliderect(wall.rect):
                hit_walls.append(wall)
        if hit_walls:
            self.take_damage(CAR_WALL_DAMAGE)
            hit_walls.sort(key=lambda w: (w.rect.centery - self.y) ** 2 + (w.rect.centerx - self.x) ** 2)
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

        body_rect = pygame.Rect(2, 6, FUEL_CAN_WIDTH - 4, FUEL_CAN_HEIGHT - 8)
        pygame.draw.rect(self.image, YELLOW, body_rect, border_radius=4)
        pygame.draw.rect(self.image, BLACK, body_rect, width=2, border_radius=4)

        handle_rect = pygame.Rect(FUEL_CAN_WIDTH // 2, 2, FUEL_CAN_WIDTH // 3, 6)
        pygame.draw.rect(self.image, YELLOW, handle_rect, border_radius=2)
        pygame.draw.rect(self.image, BLACK, handle_rect, width=1, border_radius=2)

        spout_points = [(4, 8), (9, 3), (14, 6), (9, 10)]
        pygame.draw.polygon(self.image, YELLOW, spout_points)
        pygame.draw.lines(self.image, BLACK, False, spout_points, width=2)

        # Diagonal accent to read like a can
        pygame.draw.line(
            self.image,
            (240, 200, 40),
            (FUEL_CAN_WIDTH // 2 - 4, FUEL_CAN_HEIGHT // 2 + 5),
            (FUEL_CAN_WIDTH - 6, FUEL_CAN_HEIGHT // 2 - 6),
            width=3,
        )

        self.rect = self.image.get_rect(center=(x, y))

def rect_for_cell(x_idx: int, y_idx: int) -> pygame.Rect:
    return pygame.Rect(x_idx * CELL_SIZE, y_idx * CELL_SIZE, CELL_SIZE, CELL_SIZE)


def generate_level_from_blueprint(game_data):
    """Build walls/spawn candidates/outside area from a blueprint grid."""
    wall_group = game_data.groups.wall_group
    all_sprites = game_data.groups.all_sprites

    blueprint = choose_blueprint()
    outside_rects: List[pygame.Rect] = []
    walkable_cells: List[pygame.Rect] = []
    player_cells: List[pygame.Rect] = []
    car_cells: List[pygame.Rect] = []
    zombie_cells: List[pygame.Rect] = []

    for y, row in enumerate(blueprint):
        if len(row) != LEVEL_GRID_COLS:
            raise ValueError(f"Blueprint width mismatch at row {y}: {len(row)} != {LEVEL_GRID_COLS}")
        for x, ch in enumerate(row):
            cell_rect = rect_for_cell(x, y)
            if ch == "O":
                outside_rects.append(cell_rect)
                continue
            if ch == "B":
                wall = Wall(
                    cell_rect.x,
                    cell_rect.y,
                    cell_rect.width,
                    cell_rect.height,
                    health=OUTER_WALL_HEALTH,
                    color=OUTER_WALL_COLOR,
                    border_color=OUTER_WALL_BORDER_COLOR,
                )
                wall_group.add(wall)
                all_sprites.add(wall, layer=0)
                continue
            if ch == "E":
                walkable_cells.append(cell_rect)
            elif ch == "1":
                wall = Wall(
                    cell_rect.x,
                    cell_rect.y,
                    cell_rect.width,
                    cell_rect.height,
                    health=INTERNAL_WALL_HEALTH,
                    color=INTERNAL_WALL_COLOR,
                    border_color=INTERNAL_WALL_BORDER_COLOR,
                )
                wall_group.add(wall)
                all_sprites.add(wall, layer=0)
            else:
                walkable_cells.append(cell_rect)

            if ch == "P":
                player_cells.append(cell_rect)
            if ch == "C":
                car_cells.append(cell_rect)
            if ch == "Z":
                zombie_cells.append(cell_rect)

    game_data.areas.outer_rect = (0, 0, LEVEL_WIDTH, LEVEL_HEIGHT)
    game_data.areas.inner_rect = (0, 0, LEVEL_WIDTH, LEVEL_HEIGHT)
    game_data.areas.outside_rects = outside_rects
    game_data.areas.walkable_cells = walkable_cells
    # level_rect no longer used

    return {
        "player_cells": player_cells,
        "car_cells": car_cells,
        "zombie_cells": zombie_cells,
        "walkable_cells": walkable_cells,
    }


# --- Helper Functions ---
def show_message(
    screen: surface.Surface, text: str, size: int, color: Tuple[int, int, int], position: Tuple[int, int]
) -> None:
    try:
        font = pygame.font.Font(None, size)
        text_surface = font.render(text, True, color)
        text_rect = text_surface.get_rect(center=position)

        # Add a semi-transparent background rectangle for better visibility
        bg_padding = 15
        bg_rect = text_rect.inflate(bg_padding * 2, bg_padding * 2)
        bg_surface = pygame.Surface((bg_rect.width, bg_rect.height), pygame.SRCALPHA)
        bg_surface.fill((0, 0, 0, 180))  # Black with 180 alpha (out of 255)
        screen.blit(bg_surface, bg_rect.topleft)

        screen.blit(text_surface, text_rect)
    except pygame.error as e:
        print(f"Error rendering font or surface: {e}")


def draw_level_overview(
    surface: surface.Surface,
    wall_group: sprite.Group,
    player: Player,
    car: Car,
    footprints,
    fuel: FuelCan | None = None,
    stage: Stage | None = None,
) -> None:
    surface.fill(BLACK)
    for wall in wall_group:
        pygame.draw.rect(surface, INTERNAL_WALL_COLOR, wall.rect)
    now = pygame.time.get_ticks()
    for fp in footprints:
        age = now - fp["time"]
        fade = 1 - (age / FOOTPRINT_LIFETIME_MS)
        fade = max(FOOTPRINT_MIN_FADE, fade)
        color = tuple(int(c * fade) for c in FOOTPRINT_COLOR)
        pygame.draw.circle(surface, color, (int(fp["pos"][0]), int(fp["pos"][1])), FOOTPRINT_OVERVIEW_RADIUS)
    if fuel and fuel.alive():
        pygame.draw.rect(surface, YELLOW, fuel.rect, border_radius=3)
        pygame.draw.rect(surface, BLACK, fuel.rect, width=2, border_radius=3)
    if player:
        pygame.draw.circle(surface, BLUE, player.rect.center, PLAYER_RADIUS * 2)
    if car and car.alive():
        car_rect = car.image.get_rect(center=car.rect.center)
        surface.blit(car.image, car_rect)


def place_new_car(wall_group, player, walkable_cells: List[pygame.Rect]):
    if not walkable_cells:
        return None

    max_attempts = 150
    for _ in range(max_attempts):
        cell = random.choice(walkable_cells)
        c_x, c_y = cell.center
        temp_car = Car(c_x, c_y)
        temp_rect = temp_car.rect.inflate(30, 30)
        nearby_walls = pygame.sprite.Group()
        nearby_walls.add([w for w in wall_group if abs(w.rect.centerx - c_x) < 150 and abs(w.rect.centery - c_y) < 150])
        collides_wall = pygame.sprite.spritecollideany(temp_car, nearby_walls, collided=lambda s1, s2: s1.rect.colliderect(s2.rect))
        collides_player = temp_rect.colliderect(player.rect.inflate(50, 50))
        if not collides_wall and not collides_player:
            return temp_car
    return None


def place_fuel_can(walkable_cells: List[pygame.Rect], player: Player, car: Car | None = None) -> FuelCan | None:
    """Pick a spawn spot for the fuel can away from the player (and car if given)."""
    if not walkable_cells:
        return None

    min_player_dist = 250
    min_car_dist = 200

    for _ in range(200):
        cell = random.choice(walkable_cells)
        if math.hypot(cell.centerx - player.x, cell.centery - player.y) < min_player_dist:
            continue
        if car and math.hypot(cell.centerx - car.rect.centerx, cell.centery - car.rect.centery) < min_car_dist:
            continue
        return FuelCan(cell.centerx, cell.centery)

    # Fallback: drop near a random walkable cell
    cell = random.choice(walkable_cells)
    return FuelCan(cell.centerx, cell.centery)


def get_shrunk_sprite(sprite: pygame.sprite.Sprite, scale_x: float, scale_y: Optional[float] = None) -> sprite.Sprite:
    if scale_y is None:
        scale_y = scale_x

    original_rect = sprite.rect
    shrunk_width = int(original_rect.width * scale_x)
    shrunk_height = int(original_rect.height * scale_y)

    shrunk_width = max(1, shrunk_width)
    shrunk_height = max(1, shrunk_height)

    rect = pygame.Rect(0, 0, shrunk_width, shrunk_height)
    rect.center = original_rect.center

    sprite = pygame.sprite.Sprite()
    sprite.rect = rect

    return sprite


def get_hatch_pattern(fog_data, thickness: int, pixel_scale: int = 1) -> surface.Surface:
    """Return cached ordered-dither tile surface (Bayer-style, optionally chunky)."""
    cache = fog_data.setdefault("hatch_patterns", {})
    pixel_scale = max(1, pixel_scale)
    key = (thickness, pixel_scale)
    if key in cache:
        return cache[key]

    spacing = 20
    density = max(1, min(thickness, 16))
    pattern = pygame.Surface((spacing, spacing), pygame.SRCALPHA)

    # 8x8 Bayer matrix values 0..63 for ordered dithering
    bayer = [
        [0, 32, 8, 40, 2, 34, 10, 42],
        [48, 16, 56, 24, 50, 18, 58, 26],
        [12, 44, 4, 36, 14, 46, 6, 38],
        [60, 28, 52, 20, 62, 30, 54, 22],
        [3, 35, 11, 43, 1, 33, 9, 41],
        [51, 19, 59, 27, 49, 17, 57, 25],
        [15, 47, 7, 39, 13, 45, 5, 37],
        [63, 31, 55, 23, 61, 29, 53, 21],
    ]
    # Density controls threshold (higher = more filled)
    threshold = int((density / 16) * 64)
    for y in range(spacing):
        for x in range(spacing):
            if bayer[y % 8][x % 8] < threshold:
                pattern.set_at((x, y), (0, 0, 0, 255))

    if pixel_scale > 1:
        scaled_size = (spacing * pixel_scale, spacing * pixel_scale)
        pattern = pygame.transform.scale(pattern, scaled_size)

    cache[key] = pattern
    return pattern


def update_footprints(game_data) -> None:
    """Record player steps and clean up old footprints."""
    state = game_data.state
    player: Player = game_data.player
    config = game_data.get("config", DEFAULT_CONFIG)

    footprints_enabled = config.get("footprints", {}).get("enabled", True)
    if not footprints_enabled:
        state.footprints = []
        state.last_footprint_pos = None
        return

    now = pygame.time.get_ticks()

    footprints = state.footprints
    if not player.in_car:
        last_pos = state.last_footprint_pos
        dist = math.hypot(player.x - last_pos[0], player.y - last_pos[1]) if last_pos else None
        if last_pos is None or (dist is not None and dist >= FOOTPRINT_STEP_DISTANCE):
            footprints.append({"pos": (player.x, player.y), "time": now})
            state.last_footprint_pos = (player.x, player.y)

    if len(footprints) > FOOTPRINT_MAX:
        footprints = footprints[-FOOTPRINT_MAX:]

    state.footprints = footprints


def _blit_hatch_ring(screen, overlay: surface.Surface, pattern: surface.Surface, clear_center, radius: float):
    """Draw a single hatched fog ring using pattern transparency only (no global alpha)."""
    overlay.fill((0, 0, 0, 0))
    p_w, p_h = pattern.get_size()
    for y in range(0, SCREEN_HEIGHT, p_h):
        for x in range(0, SCREEN_WIDTH, p_w):
            overlay.blit(pattern, (x, y))
    pygame.draw.circle(overlay, (0, 0, 0, 0), clear_center, int(radius))
    screen.blit(overlay, (0, 0))


def _draw_status_bar(screen, config, stage: Stage | None = None):
    """Render a compact status bar with current config flags and stage info."""
    bar_rect = pygame.Rect(0, SCREEN_HEIGHT - STATUS_BAR_HEIGHT, SCREEN_WIDTH, STATUS_BAR_HEIGHT)
    overlay = pygame.Surface((bar_rect.width, bar_rect.height), pygame.SRCALPHA)
    overlay.fill((0, 0, 0, 140))
    screen.blit(overlay, bar_rect.topleft)

    footprints_on = config.get("footprints", {}).get("enabled", True)
    fast_on = config.get("fast_zombies", {}).get("enabled", True)
    hint_on = config.get("car_hint", {}).get("enabled", True)
    stage_label = stage.name if stage else "Stage 1"

    parts = [
        f"Stage: {stage_label}",
        f"Footprints: {'ON' if footprints_on else 'OFF'}",
        f"Fast Z: {'ON' if fast_on else 'OFF'}",
        f"Car Hint: {'ON' if hint_on else 'OFF'}",
    ]

    status_text = " | ".join(parts)
    color = GREEN if all([footprints_on, fast_on, hint_on]) else LIGHT_GRAY

    try:
        font = pygame.font.Font(None, 20)
        text_surface = font.render(status_text, True, color)
        text_rect = text_surface.get_rect(left=12, centery=bar_rect.centery)
        screen.blit(text_surface, text_rect)
    except pygame.error as e:
        print(f"Error rendering status bar: {e}")


def _draw_hint_arrow(screen, camera, player: Player, target_pos: Tuple[int, int], color=YELLOW) -> None:
    """Draw a soft directional hint from player to a target position."""
    player_screen = camera.apply(player).center
    target_rect = pygame.Rect(target_pos[0], target_pos[1], 0, 0)
    target_screen = camera.apply_rect(target_rect).center
    dx = target_screen[0] - player_screen[0]
    dy = target_screen[1] - player_screen[1]
    dist = math.hypot(dx, dy)
    if dist < 10:
        return
    dir_x = dx / dist
    dir_y = dy / dist
    ring_radius = FOV_RADIUS * 0.5
    center_x = player_screen[0] + dir_x * ring_radius
    center_y = player_screen[1] + dir_y * ring_radius
    arrow_len = 12
    tip = (center_x + dir_x * arrow_len, center_y + dir_y * arrow_len)
    base = (center_x - dir_x * 12, center_y - dir_y * 12)
    left = (
        base[0] - dir_y * 10,
        base[1] + dir_x * 10,
    )
    right = (
        base[0] + dir_y * 10,
        base[1] - dir_x * 10,
    )
    pygame.draw.polygon(screen, color, [tip, left, right])


def draw(
    screen,
    outer_rect,
    camera,
    all_sprites,
    fov_target,
    fog_surfaces,
    footprints,
    config,
    player,
    hint_target: Tuple[int, int] | None,
    hint_color=YELLOW,
    do_flip: bool = True,
    outside_rects: List[pygame.Rect] | None = None,
    stage: Stage | None = None,
    has_fuel: bool = False,
    elapsed_play_ms: int = 0,
    fuel_message_until: int = 0,
):
    # Drawing
    screen.fill(FLOOR_COLOR_OUTSIDE)

    # floor tiles
    xs, ys, xe, ye = outer_rect
    xs //= INTERNAL_WALL_GRID_SNAP
    ys //= INTERNAL_WALL_GRID_SNAP
    xe //= INTERNAL_WALL_GRID_SNAP
    ye //= INTERNAL_WALL_GRID_SNAP

    # Base fill for play area
    play_area_rect = pygame.Rect(xs * INTERNAL_WALL_GRID_SNAP, ys * INTERNAL_WALL_GRID_SNAP, (xe - xs) * INTERNAL_WALL_GRID_SNAP, (ye - ys) * INTERNAL_WALL_GRID_SNAP)
    play_area_screen_rect = camera.apply_rect(play_area_rect)
    pygame.draw.rect(screen, FLOOR_COLOR_PRIMARY, play_area_screen_rect)

    # Mask out designated outside cells (non-playable) with outside floor color
    outside_rects = outside_rects or []
    outside_cells = {(r.x // INTERNAL_WALL_GRID_SNAP, r.y // INTERNAL_WALL_GRID_SNAP) for r in outside_rects}
    for rect_obj in outside_rects:
        sr = camera.apply_rect(rect_obj)
        if sr.colliderect(screen.get_rect()):
            pygame.draw.rect(screen, FLOOR_COLOR_OUTSIDE, sr)

    for y in range(ys, ye):
        for x in range(xs, xe):
            if (x, y) in outside_cells:
                continue
            if (x + y) % 2 == 0:
                lx, ly = x * INTERNAL_WALL_GRID_SNAP, y * INTERNAL_WALL_GRID_SNAP
                r = pygame.Rect(lx, ly, INTERNAL_WALL_GRID_SNAP, INTERNAL_WALL_GRID_SNAP)
                sr = camera.apply_rect(r)
                if sr.colliderect(screen.get_rect()):
                    pygame.draw.rect(screen, FLOOR_COLOR_SECONDARY, sr)

    # footprints
    if config.get("footprints", {}).get("enabled", True):
        now = pygame.time.get_ticks()
        for fp in footprints:
            age = now - fp["time"]
            fade = 1 - (age / FOOTPRINT_LIFETIME_MS)
            fade = max(FOOTPRINT_MIN_FADE, fade)
            color = tuple(int(c * fade) for c in FOOTPRINT_COLOR)
            fp_rect = pygame.Rect(fp["pos"][0] - FOOTPRINT_RADIUS, fp["pos"][1] - FOOTPRINT_RADIUS, FOOTPRINT_RADIUS * 2, FOOTPRINT_RADIUS * 2)
            sr = camera.apply_rect(fp_rect)
            if sr.colliderect(screen.get_rect().inflate(30, 30)):
                pygame.draw.circle(screen, color, sr.center, FOOTPRINT_RADIUS)

    # player, car, zombies, walls
    for sprite in all_sprites:
        sprite_screen_rect = camera.apply_rect(sprite.rect)
        if sprite_screen_rect.colliderect(screen.get_rect().inflate(100, 100)):
            screen.blit(sprite.image, sprite_screen_rect)

    if hint_target and player:
        _draw_hint_arrow(screen, camera, player, hint_target, color=hint_color)

    # fog with hatched rings
    if fov_target is not None:
        fov_center_on_screen = camera.apply(fov_target).center
        fog_hard = fog_surfaces["hard"]
        fog_soft = fog_surfaces["soft"]

        # Base solid darkness outside max radius
        fog_hard.fill(FOG_COLOR)
        max_radius = int(FOV_RADIUS * FOG_MAX_RADIUS_FACTOR * FOG_RADIUS_SCALE)
        pygame.draw.circle(fog_hard, (0, 0, 0, 0), fov_center_on_screen, max_radius)
        screen.blit(fog_hard, (0, 0))

        # Hatched rings layered from near to far
        for ring in FOG_RINGS:
            radius = int(FOV_RADIUS * ring.radius_factor * FOG_RADIUS_SCALE)
            thickness = ring.thickness
            pattern = get_hatch_pattern(fog_surfaces, thickness, FOG_HATCH_PIXEL_SCALE)
            _blit_hatch_ring(screen, fog_soft, pattern, fov_center_on_screen, radius)

    # HUD prompts for fuel flow: show immediately after failed car entry, not time-gated hint
    if not has_fuel:
        if fuel_message_until > elapsed_play_ms:
            show_message(screen, "Need fuel to drive!", 32, ORANGE, (SCREEN_WIDTH // 2, SCREEN_HEIGHT // 2))

    # Objective banner at top (drawn last so it stays above fog/hatch)
    def _render_objective(text: str):
        try:
            font = pygame.font.Font(None, 30)
            text_surface = font.render(text, True, YELLOW)
            text_rect = text_surface.get_rect(topleft=(16, 16))
            screen.blit(text_surface, text_rect)
        except pygame.error as e:
            print(f"Error rendering objective: {e}")

    objective_text = None
    if not has_fuel:
        objective_text = "Find the fuel can"
    elif not player.in_car:
        objective_text = "Find the car"
    else:
        objective_text = "Escape the building"

    if objective_text:
        _render_objective(objective_text)

    _draw_status_bar(screen, config, stage=stage)
    if do_flip:
        present(screen)


# --- Game State Function (Contains the main game loop) ---
def initialize_game_state(config, stage: Stage):
    """Initialize and return the base game state objects."""
    starts_with_fuel = not stage.requires_fuel
    game_state = ProgressState(
        game_over=False,
        game_won=False,
        overview_surface=None,
        scaled_overview=None,
        overview_created=False,
        last_zombie_spawn_time=0,
        footprints=[],
        last_footprint_pos=None,
        elapsed_play_ms=0,
        has_fuel=starts_with_fuel,
        hint_expires_at=0,
        hint_target_type=None,
        fuel_message_until=0,
    )

    # Create sprite groups
    all_sprites = pygame.sprite.LayeredUpdates()
    wall_group = pygame.sprite.Group()
    zombie_group = pygame.sprite.Group()

    # Create camera
    camera = Camera(LEVEL_WIDTH, LEVEL_HEIGHT)

    # Define level areas (will be filled by blueprint generation)
    outer_rect = 0, 0, LEVEL_WIDTH, LEVEL_HEIGHT
    inner_rect = outer_rect

    # Create fog surfaces
    fog_surface_hard = pygame.Surface((SCREEN_WIDTH, SCREEN_HEIGHT), pygame.SRCALPHA)
    fog_surface_soft = pygame.Surface((SCREEN_WIDTH, SCREEN_HEIGHT), pygame.SRCALPHA)

    return GameData(
        state=game_state,
        groups=Groups(all_sprites=all_sprites, wall_group=wall_group, zombie_group=zombie_group),
        camera=camera,
        areas=Areas(
            outer_rect=outer_rect,
            inner_rect=inner_rect,
            outside_rects=[],
            walkable_cells=[],
        ),
        fog={"hard": fog_surface_hard, "soft": fog_surface_soft, "hatch_patterns": {}},
        config=config,
        stage=stage,
        fuel=None,
    )


def setup_player_and_car(game_data, layout_data):
    """Create and position the player and car using blueprint candidates."""
    all_sprites = game_data.groups.all_sprites
    walkable_cells: List[pygame.Rect] = layout_data["walkable_cells"]

    def pick_center(cells: List[pygame.Rect]) -> Tuple[int, int]:
        return random.choice(cells).center if cells else (LEVEL_WIDTH // 2, LEVEL_HEIGHT // 2)

    player_pos = pick_center(layout_data["player_cells"] or walkable_cells)
    player = Player(*player_pos)

    # Place car away from player
    car_candidates = layout_data["car_cells"] or walkable_cells
    car_pos = None
    for _ in range(200):
        candidate = random.choice(car_candidates)
        if math.hypot(candidate.centerx - player_pos[0], candidate.centery - player_pos[1]) >= 400:
            car_pos = candidate.center
            break
    if car_pos is None and car_candidates:
        car_pos = random.choice(car_candidates).center
    elif car_pos is None:
        car_pos = (player_pos[0] + 200, player_pos[1])  # Fallback

    car = Car(*car_pos)

    # Add to sprite groups
    all_sprites.add(player, layer=2)
    all_sprites.add(car, layer=1)

    return player, car


def spawn_initial_zombies(game_data, player, layout_data):
    """Spawn initial zombies using blueprint candidate cells."""
    config = game_data.get("config", DEFAULT_CONFIG)
    wall_group = game_data.groups.wall_group
    zombie_group = game_data.groups.zombie_group
    all_sprites = game_data.groups.all_sprites

    spawn_cells = layout_data["zombie_cells"] or layout_data["walkable_cells"]
    if not spawn_cells:
        return

    initial_zombies_placed = 0
    placement_attempts = 0
    max_placement_attempts = INITIAL_ZOMBIES_INSIDE * 20

    while initial_zombies_placed < INITIAL_ZOMBIES_INSIDE and placement_attempts < max_placement_attempts:
        placement_attempts += 1
        cell = random.choice(spawn_cells)
        z_pos = cell.center
        temp_zombie = create_zombie(config, start_pos=z_pos)
        temp_sprite = pygame.sprite.Sprite()
        temp_sprite.rect = temp_zombie.rect.inflate(5, 5)

        collides_with_wall = pygame.sprite.spritecollideany(temp_sprite, wall_group)
        collides_with_player = temp_sprite.rect.colliderect(player.rect.inflate(ZOMBIE_SIGHT_RANGE, ZOMBIE_SIGHT_RANGE))

        if not collides_with_wall and not collides_with_player:
            new_zombie = temp_zombie
            zombie_group.add(new_zombie)
            all_sprites.add(new_zombie, layer=1)
            initial_zombies_placed += 1

    game_data.state.last_zombie_spawn_time = pygame.time.get_ticks() - ZOMBIE_SPAWN_DELAY_MS


def handle_game_over_state(screen, game_data):
    """Handle rendering and input when game is over or won."""
    state = game_data.state
    wall_group = game_data.groups["wall_group"]
    config = game_data.config
    footprints_enabled = config.get("footprints", {}).get("enabled", True)

    # Create overview map if needed
    if not state.overview_created:
        state.overview_surface = pygame.Surface((LEVEL_WIDTH, LEVEL_HEIGHT))
        footprints_to_draw = state.footprints if footprints_enabled else []
        draw_level_overview(
            state.overview_surface,
            wall_group,
            game_data.player,
            game_data.car,
            footprints_to_draw,
            fuel=game_data.fuel,
            stage=game_data.stage,
        )

        level_aspect = LEVEL_WIDTH / LEVEL_HEIGHT
        screen_aspect = SCREEN_WIDTH / SCREEN_HEIGHT
        if level_aspect > screen_aspect:
            scaled_w = SCREEN_WIDTH - 40
            scaled_h = int(scaled_w / level_aspect)
        else:
            scaled_h = SCREEN_HEIGHT - 40
            scaled_w = int(scaled_h * level_aspect)

        # Ensure scaled dimensions are at least 1
        scaled_w = max(1, scaled_w)
        scaled_h = max(1, scaled_h)

        state.scaled_overview = pygame.transform.smoothscale(state.overview_surface, (scaled_w, scaled_h))
        state.overview_created = True

    # Display overview map and messages
    screen.fill(BLACK)
    if state.scaled_overview:
        screen.blit(state.scaled_overview, state.scaled_overview.get_rect(center=(SCREEN_WIDTH // 2, SCREEN_HEIGHT // 2)))

        if state.get("game_won"):
            show_message(screen, "YOU ESCAPED!", 40, GREEN, (SCREEN_WIDTH // 2, SCREEN_HEIGHT // 2 - 40))

    show_message(
        screen,
        "Press ESC or SPACE to return to Title",
        30,
        WHITE,
        (SCREEN_WIDTH // 2, SCREEN_HEIGHT // 2 + 30),
    )

    present(screen)

    # Check for restart input
    for event in pygame.event.get():
        if event.type == pygame.QUIT:
            return False
        if event.type == pygame.KEYDOWN:
            if event.key in (pygame.K_ESCAPE, pygame.K_SPACE):
                return True

    return None  # Continue in current state


def process_player_input(keys, player, car):
    """Process keyboard input and return movement deltas."""
    dx_input, dy_input = 0, 0
    if keys[pygame.K_w] or keys[pygame.K_UP]:
        dy_input -= 1
    if keys[pygame.K_s] or keys[pygame.K_DOWN]:
        dy_input += 1
    if keys[pygame.K_a] or keys[pygame.K_LEFT]:
        dx_input -= 1
    if keys[pygame.K_d] or keys[pygame.K_RIGHT]:
        dx_input += 1

    player_dx, player_dy, car_dx, car_dy = 0, 0, 0, 0

    if player.in_car and car.alive():
        target_speed = CAR_SPEED
        move_len = math.hypot(dx_input, dy_input)
        if move_len > 0:
            car_dx, car_dy = (dx_input / move_len) * target_speed, (dy_input / move_len) * target_speed
    elif not player.in_car:
        target_speed = PLAYER_SPEED
        move_len = math.hypot(dx_input, dy_input)
        if move_len > 0:
            player_dx, player_dy = (dx_input / move_len) * target_speed, (dy_input / move_len) * target_speed

    return player_dx, player_dy, car_dx, car_dy


def update_entities(game_data, player_dx, player_dy, car_dx, car_dy):
    """Update positions and states of game entities."""
    player = game_data.player
    car = game_data.car
    wall_group = game_data.groups.wall_group
    all_sprites = game_data.groups.all_sprites
    zombie_group = game_data.groups.zombie_group
    camera = game_data.camera
    config = game_data.config

    # Update player/car movement
    if player.in_car and car.alive():
        car.move(car_dx, car_dy, wall_group)
        player.rect.center = car.rect.center
        player.x, player.y = car.x, car.y
    elif not player.in_car:
        # Ensure player is in all_sprites if not in car
        if player not in all_sprites:
            all_sprites.add(player, layer=2)
        player.move(player_dx, player_dy, wall_group)

    # Update camera
    target_for_camera = car if player.in_car and car.alive() else player
    camera.update(target_for_camera)

    # Spawn new zombies if needed
    current_time = pygame.time.get_ticks()
    if len(zombie_group) < MAX_ZOMBIES and current_time - game_data.state.last_zombie_spawn_time > ZOMBIE_SPAWN_DELAY_MS:
        new_zombie = create_zombie(config, hint_pos=(player.x, player.y))
        zombie_group.add(new_zombie)
        all_sprites.add(new_zombie, layer=1)
        game_data.state.last_zombie_spawn_time = current_time

    # Update zombies
    target_center = car.rect.center if player.in_car and car.alive() else player.rect.center
    for zombie in zombie_group:
        zombie.update(target_center, wall_group, zombie_group)


def check_interactions(game_data):
    """Check and handle interactions between entities."""
    player = game_data.player
    car = game_data.car
    zombie_group = game_data.groups.zombie_group
    wall_group = game_data.groups.wall_group
    all_sprites = game_data.groups.all_sprites
    state = game_data.state
    walkable_cells = game_data.areas.walkable_cells
    outside_rects = game_data.areas.outside_rects
    fuel = game_data.fuel

    # Fuel pickup
    if fuel and fuel.alive() and not state.get("has_fuel") and not player.in_car:
        dist_to_fuel = math.hypot(fuel.rect.centerx - player.x, fuel.rect.centery - player.y)
        if dist_to_fuel <= max(FUEL_PICKUP_RADIUS, PLAYER_RADIUS + 6):
            state.has_fuel = True
            state.fuel_message_until = 0
            state.hint_expires_at = 0
            state.hint_target_type = None
            fuel.kill()
            game_data.fuel = None
            print("Fuel acquired!")

    # Player entering car
    shrunk_car = get_shrunk_sprite(car, 0.8)
    if not player.in_car and car.alive() and car.health > 0:
        g = pygame.sprite.Group()
        g.add(player)
        if pygame.sprite.spritecollide(shrunk_car, g, False):
            if state.has_fuel:
                player.in_car = True
                all_sprites.remove(player)
                state.hint_expires_at = 0
                state.hint_target_type = None
                print("Player entered car!")
            else:
                now_ms = state.elapsed_play_ms
                state.fuel_message_until = now_ms + FUEL_HINT_DURATION_MS
                state.hint_expires_at = now_ms + FUEL_HINT_DURATION_MS
                state.hint_target_type = "fuel"

    # Car hitting zombies
    if player.in_car and car.alive() and car.health > 0:
        zombies_hit = pygame.sprite.spritecollide(shrunk_car, zombie_group, True)
        if zombies_hit:
            car.take_damage(CAR_ZOMBIE_DAMAGE * len(zombies_hit))

    # Handle car destruction
    if car.alive() and car.health <= 0:
        car_destroyed_pos = car.rect.center
        car.kill()
        if player.in_car:
            player.in_car = False
            player.x, player.y = car_destroyed_pos[0], car_destroyed_pos[1]
            player.rect.center = (int(player.x), int(player.y))
            if player not in all_sprites:
                all_sprites.add(player, layer=2)
            print("Car destroyed! Player ejected.")

        # Respawn car
        new_car = place_new_car(wall_group, player, walkable_cells)
        if new_car is None:
            # Fallback: Try original car position or other strategies
            new_car = Car(car.rect.centerx, car.rect.centery)

        if new_car is not None:
            game_data.car = new_car  # Update car reference
            all_sprites.add(new_car, layer=1)
        else:
            print("Error: Failed to respawn car anywhere!")

    # Player getting caught by zombies
    if not player.in_car and player in all_sprites:
        shrunk_player = get_shrunk_sprite(player, 0.8)
        if pygame.sprite.spritecollide(shrunk_player, zombie_group, False, pygame.sprite.collide_circle):
            state.game_over = True

    # Player escaping the level
    if player.in_car and car.alive() and state.get("has_fuel"):
        if any(outside.collidepoint(car.rect.center) for outside in outside_rects):
            state.game_won = True

    # Return fog of view target
    if not state.game_over and not state.game_won:
        return car if player.in_car and car.alive() else player
    return None


def run_game(screen: surface.Surface, clock: time.Clock, config, stage: Stage, show_pause_overlay: bool = True) -> bool:
    """Main game loop function, now using smaller helper functions."""
    # Initialize game components
    game_data = initialize_game_state(config, stage)
    paused_manual = False
    paused_focus = False
    last_fov_target = None

    # Generate level from blueprint and set up player/car
    layout_data = generate_level_from_blueprint(game_data)
    player, car = setup_player_and_car(game_data, layout_data)
    game_data.player = player
    game_data.car = car

    # Stage-specific collectibles (fuel for Stage 2)
    if stage.requires_fuel:
        fuel_can = place_fuel_can(layout_data["walkable_cells"], player, car)
        if fuel_can:
            game_data.fuel = fuel_can
            game_data.groups.all_sprites.add(fuel_can, layer=1)

    # Spawn initial zombies
    spawn_initial_zombies(game_data, player, layout_data)
    update_footprints(game_data)
    last_fov_target = player

    # Game loop
    running = True
    while running:
        dt = clock.tick(FPS) / 1000.0
        # Refresh references (car can be respawned)
        player = game_data.player
        car = game_data.car

        # Handle game over state
        if game_data.state.get("game_over") or game_data.state.get("game_won"):
            result = handle_game_over_state(screen, game_data)
            if result is not None:  # If restart or quit was selected
                return result
            continue

        # Check for quit events
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                return False
            if event.type == pygame.WINDOWFOCUSLOST:
                paused_focus = True
            if event.type == pygame.MOUSEBUTTONDOWN:
                paused_focus = False
                paused_manual = False
            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_s and (pygame.key.get_mods() & pygame.KMOD_CTRL):
                    state_snapshot = {k: v for k, v in game_data.state.items() if k != "footprints"}
                    print("STATE DEBUG:", state_snapshot)
                    continue
                if event.key == pygame.K_ESCAPE:
                    return True
                if event.key == pygame.K_p:
                    paused_manual = not paused_manual

        paused = paused_manual or paused_focus
        if paused:
            draw(
                screen,
                game_data.areas.outer_rect,
                game_data.camera,
                game_data.groups.all_sprites,
                last_fov_target,
                game_data.fog,
                game_data.state.footprints,
                config,
                player,
                None,
                do_flip=not show_pause_overlay,
                outside_rects=game_data.areas.outside_rects,
                stage=stage,
                has_fuel=game_data.state.has_fuel,
                elapsed_play_ms=game_data.state.elapsed_play_ms,
                fuel_message_until=game_data.state.fuel_message_until,
            )
            if show_pause_overlay:
                overlay = pygame.Surface((SCREEN_WIDTH, SCREEN_HEIGHT), pygame.SRCALPHA)
                overlay.fill((0, 0, 0, 150))
                pygame.draw.circle(overlay, LIGHT_GRAY, (SCREEN_WIDTH // 2, SCREEN_HEIGHT // 2), 70, width=6)
                bar_width = 16
                bar_height = 60
                gap = 18
                cx, cy = SCREEN_WIDTH // 2, SCREEN_HEIGHT // 2
                pygame.draw.rect(overlay, LIGHT_GRAY, (cx - gap - bar_width, cy - bar_height // 2, bar_width, bar_height))
                pygame.draw.rect(overlay, LIGHT_GRAY, (cx + gap, cy - bar_height // 2, bar_width, bar_height))
                screen.blit(overlay, (0, 0))
                show_message(screen, "PAUSED", 64, WHITE, (SCREEN_WIDTH // 2, SCREEN_HEIGHT // 2 + 90))
                show_message(
                    screen,
                    "Press P or click to resume",
                    32,
                    LIGHT_GRAY,
                    (SCREEN_WIDTH // 2, SCREEN_HEIGHT // 2 + 140),
                )
                present(screen)
            continue

        # Process input
        keys = pygame.key.get_pressed()
        player_dx, player_dy, car_dx, car_dy = process_player_input(keys, player, car)

        # Update game entities
        update_entities(game_data, player_dx, player_dy, car_dx, car_dy)
        update_footprints(game_data)
        game_data.state.elapsed_play_ms += int(dt * 1000)

        # Handle interactions
        fov_target = check_interactions(game_data)
        last_fov_target = fov_target or last_fov_target

        # Draw everything
        car_hint_conf = config.get("car_hint", {})
        hint_delay = car_hint_conf.get("delay_ms", CAR_HINT_DELAY_MS_DEFAULT)
        elapsed_ms = game_data.state.get("elapsed_play_ms", 0)
        has_fuel = game_data.state.get("has_fuel")
        hint_enabled = car_hint_conf.get("enabled", True)
        hint_target = None
        hint_color = YELLOW
        hint_expires_at = game_data.state.get("hint_expires_at", 0)
        hint_target_type = game_data.state.get("hint_target_type")

        if hint_enabled:
            if not has_fuel and game_data.fuel and game_data.fuel.alive():
                target_type = "fuel"
            elif not player.in_car and game_data.car.alive():
                target_type = "car"
            else:
                target_type = None

            if target_type != hint_target_type:
                game_data.state.hint_target_type = target_type
                game_data.state.hint_expires_at = elapsed_ms + hint_delay if target_type else 0
                hint_expires_at = game_data.state.hint_expires_at
                hint_target_type = target_type

            if target_type and hint_expires_at and elapsed_ms >= hint_expires_at and not player.in_car:
                if target_type == "fuel" and game_data.fuel and game_data.fuel.alive():
                    hint_target = game_data.fuel.rect.center
                elif target_type == "car" and game_data.car.alive():
                    hint_target = game_data.car.rect.center

        draw(
            screen,
            game_data.areas.outer_rect,
            game_data.camera,
            game_data.groups.all_sprites,
            fov_target,
            game_data.fog,
            game_data.state.footprints,
            config,
            player,
            hint_target,
            hint_color,
            outside_rects=game_data.areas.outside_rects,
            stage=stage,
            has_fuel=game_data.state.has_fuel,
            elapsed_play_ms=game_data.state.elapsed_play_ms,
            fuel_message_until=game_data.state.fuel_message_until,
        )

    return False


# --- Splash & Menu Functions ---
def title_screen(screen: surface.Surface, clock: time.Clock, config) -> dict:
    """Title menu with inline stage selection. Returns action dict: {'action': 'stage'|'settings'|'quit', 'stage': Stage|None}."""
    options = [{"type": "stage", "stage": s, "available": s.available} for s in STAGES]
    options += [{"type": "settings"}, {"type": "quit"}]
    selected = next(
        (i for i, opt in enumerate(options) if opt["type"] == "stage" and opt["stage"].id == DEFAULT_STAGE_ID), 0
    )

    while True:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                return {"action": "quit", "stage": None}
            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_LEFTBRACKET:
                    nudge_window_scale(0.5)
                    continue
                if event.key == pygame.K_RIGHTBRACKET:
                    nudge_window_scale(2.0)
                    continue
                if event.key in (pygame.K_UP, pygame.K_w):
                    selected = (selected - 1) % len(options)
                elif event.key in (pygame.K_DOWN, pygame.K_s):
                    selected = (selected + 1) % len(options)
                elif event.key in (pygame.K_RETURN, pygame.K_SPACE):
                    current = options[selected]
                    if current["type"] == "stage" and current.get("available"):
                        return {"action": "stage", "stage": current["stage"]}
                    if current["type"] == "settings":
                        return {"action": "settings", "stage": None}
                    if current["type"] == "quit":
                        return {"action": "quit", "stage": None}

        screen.fill(BLACK)
        show_message(screen, "Zombie Escape", 72, LIGHT_GRAY, (SCREEN_WIDTH // 2, SCREEN_HEIGHT // 2 - 140))

        try:
            font = pygame.font.Font(None, 34)
            for idx, option in enumerate(options):
                if option["type"] == "stage":
                    label = option["stage"].name
                    if not option.get("available"):
                        label += " [Locked]"
                    color = YELLOW if idx == selected else (WHITE if option.get("available") else GRAY)
                elif option["type"] == "settings":
                    label = "Settings"
                    color = YELLOW if idx == selected else WHITE
                else:
                    label = "Quit"
                    color = YELLOW if idx == selected else WHITE

                text_surface = font.render(label, True, color)
                text_rect = text_surface.get_rect(center=(SCREEN_WIDTH // 2, SCREEN_HEIGHT // 2 - 20 + idx * 46))
                screen.blit(text_surface, text_rect)

            # Selected stage description (if a stage is highlighted)
            current = options[selected]
            if current["type"] == "stage":
                desc_font = pygame.font.Font(None, 24)
                desc_color = LIGHT_GRAY if current.get("available") else GRAY
                desc_surface = desc_font.render(current["stage"].description, True, desc_color)
                desc_rect = desc_surface.get_rect(center=(SCREEN_WIDTH // 2, SCREEN_HEIGHT // 2 + 170))
                screen.blit(desc_surface, desc_rect)

            # Quick config summary
            fast_on = config.get("fast_zombies", {}).get("enabled", True)
            hint_on = config.get("car_hint", {}).get("enabled", True)

            hint_font = pygame.font.Font(None, 24)
            hint_text = "Resize window: [ to shrink, ] to enlarge (menu only)"
            hint_surface = hint_font.render(hint_text, True, LIGHT_GRAY)
            hint_rect = hint_surface.get_rect(center=(SCREEN_WIDTH // 2, SCREEN_HEIGHT - 50))
            screen.blit(hint_surface, hint_rect)
        except pygame.error as e:
            print(f"Error rendering title screen: {e}")

        present(screen)
        clock.tick(FPS)


def settings_screen(screen: surface.Surface, clock: time.Clock, config, config_path) -> dict:
    """Settings menu shown from the title screen."""
    working = copy.deepcopy(config)
    selected = 0

    def toggle_footprints():
        enabled = working.get("footprints", {}).get("enabled", True)
        working.setdefault("footprints", {})["enabled"] = not enabled

    def toggle_fast_zombies():
        enabled = working.get("fast_zombies", {}).get("enabled", True)
        working.setdefault("fast_zombies", {})["enabled"] = not enabled

    def toggle_car_hint():
        enabled = working.get("car_hint", {}).get("enabled", True)
        working.setdefault("car_hint", {})["enabled"] = not enabled

    while True:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                return working
            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_LEFTBRACKET:
                    nudge_window_scale(0.5)
                    continue
                if event.key == pygame.K_RIGHTBRACKET:
                    nudge_window_scale(2.0)
                    continue
                if event.key in (pygame.K_ESCAPE, pygame.K_BACKSPACE):
                    save_config(working, config_path)
                    return working
                if event.key in (pygame.K_UP, pygame.K_w):
                    selected = (selected - 1) % 3
                if event.key in (pygame.K_DOWN, pygame.K_s):
                    selected = (selected + 1) % 3
                if event.key in (pygame.K_SPACE, pygame.K_RETURN, pygame.K_LEFT, pygame.K_RIGHT):
                    if selected == 0:
                        toggle_footprints()
                    elif selected == 1:
                        toggle_fast_zombies()
                    else:
                        toggle_car_hint()
                if event.key == pygame.K_r:
                    working = copy.deepcopy(DEFAULT_CONFIG)

        screen.fill(BLACK)
        show_message(screen, "Settings", 64, LIGHT_GRAY, (SCREEN_WIDTH // 2, SCREEN_HEIGHT // 2 - 120))

        try:
            panel_width = SCREEN_WIDTH - 140
            panel_height = SCREEN_HEIGHT - 200
            panel_rect = pygame.Rect(0, 0, panel_width, panel_height)
            panel_rect.center = (SCREEN_WIDTH // 2, SCREEN_HEIGHT // 2)
            pygame.draw.rect(screen, (20, 20, 20), panel_rect)
            pygame.draw.rect(screen, LIGHT_GRAY, panel_rect, width=2)

            label_font = pygame.font.Font(None, 28)
            value_font = pygame.font.Font(None, 28)
            highlight_color = (70, 70, 70)

            row_x_label = panel_rect.left + 40
            row_x_value = panel_rect.left + panel_width // 2 + 20
            row_height = 28
            start_y = panel_rect.top + 60

            rows = [
                ("Footprints", working.get("footprints", {}).get("enabled", True)),
                ("Fast zombies", working.get("fast_zombies", {}).get("enabled", True)),
                ("Car hint", working.get("car_hint", {}).get("enabled", True)),
            ]
            hint_start_y = start_y + len(rows) * row_height + 40
            for idx, (label, enabled) in enumerate(rows):
                row_y = start_y + idx * row_height
                if idx == selected:
                    highlight_rect = pygame.Rect(panel_rect.left + 6, row_y - 4, panel_width - 12, row_height + 4)
                    pygame.draw.rect(screen, highlight_color, highlight_rect)

                label_surface = label_font.render(label, True, WHITE)
                label_rect = label_surface.get_rect(topleft=(row_x_label, row_y))
                screen.blit(label_surface, label_rect)

                value_text = "ON" if enabled else "OFF"
                value_color = GREEN if enabled else LIGHT_GRAY
                value_surface = value_font.render(value_text, True, value_color)
                value_rect = value_surface.get_rect(topleft=(row_x_value, row_y))
                screen.blit(value_surface, value_rect)

            hint_font = pygame.font.Font(None, 22)
            hint_lines = [
                "Up/Down: select",
                "Space/Enter/Left/Right: toggle",
                "R: reset to defaults",
                "Esc/Backspace: save and return",
            ]
            for i, line in enumerate(hint_lines):
                hint_surface = hint_font.render(line, True, WHITE)
                hint_rect = hint_surface.get_rect(topleft=(panel_rect.left + 30, hint_start_y + i * 26))
                screen.blit(hint_surface, hint_rect)

            path_font = pygame.font.Font(None, 20)
            path_text = f"Config: {config_path}"
            path_surface = path_font.render(path_text, True, LIGHT_GRAY)
            path_rect = path_surface.get_rect(midtop=(SCREEN_WIDTH // 2, panel_rect.bottom + 24))
            screen.blit(path_surface, path_rect)
        except pygame.error as e:
            print(f"Error rendering settings: {e}")

        present(screen)
        clock.tick(FPS)


# --- Main Entry Point ---
def main():
    pygame.init()
    try:
        pygame.font.init()
    except pygame.error as e:
        print(f"Pygame font failed to initialize: {e}")
        # Font errors are often non-fatal, continue without fonts or handle gracefully

    apply_window_scale(current_window_scale)
    screen = pygame.Surface((SCREEN_WIDTH, SCREEN_HEIGHT)).convert_alpha()
    clock = pygame.time.Clock()

    hide_pause_overlay = "--hide-pause-overlay" in sys.argv

    config, config_path = load_config()
    if not config_path.exists():
        save_config(config, config_path)

    restart_game = True
    while restart_game:
        selection = title_screen(screen, clock, config)

        if selection["action"] == "quit":
            restart_game = False
            break

        if selection["action"] == "settings":
            config = settings_screen(screen, clock, config, config_path)
            continue

        if selection["action"] == "stage":
            try:
                restart_game = run_game(screen, clock, config, selection["stage"], show_pause_overlay=not hide_pause_overlay)
            except SystemExit:
                restart_game = False  # Exit the main loop
            except Exception:
                print("An unhandled error occurred during game execution:")
                traceback.print_exc()
                restart_game = False  # Stop loop on error
        else:
            restart_game = False

    pygame.quit()  # Quit pygame only once at the very end of main
    sys.exit()  # Exit the script


if __name__ == "__main__":
    main()
