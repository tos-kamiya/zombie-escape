import copy
import math
import random
import sys
import traceback  # For error reporting
from dataclasses import dataclass
from enum import Enum  # For Zombie Modes
from typing import Callable, Iterable, List, Optional, Self, Tuple

import pygame
from pygame import rect, sprite, surface, time

try:
    from .__about__ import __version__
except:
    __version__ = "0.0.0-unknown"
from .colors import (
    BLACK,
    BLUE,
    DARK_RED,
    GRAY,
    GREEN,
    INTERNAL_WALL_BORDER_COLOR,
    INTERNAL_WALL_COLOR,
    LIGHT_GRAY,
    ORANGE,
    OUTER_WALL_BORDER_COLOR,
    OUTER_WALL_COLOR,
    RED,
    STEEL_BEAM_COLOR,
    STEEL_BEAM_LINE_COLOR,
    WHITE,
    YELLOW,
)
from .config import DEFAULT_CONFIG, load_config, save_config
from .font_utils import load_font
from .level_blueprints import GRID_COLS, GRID_ROWS, TILE_SIZE, choose_blueprint
from .render import FogRing, RenderAssets, draw, draw_level_overview, show_message

# --- Constants/Global variables ---
LOGICAL_SCREEN_WIDTH = 400
LOGICAL_SCREEN_HEIGHT = 300
RENDER_SCREEN_WIDTH = 400
RENDER_SCREEN_HEIGHT = 300
DEFAULT_WINDOW_SCALE = 2.0  # Keep ~800x600 OS window while rendering at 400x300
WINDOW_SCALE_MIN = 1.0
WINDOW_SCALE_MAX = DEFAULT_WINDOW_SCALE * 2  # Allow up to 1600x1200 windows
SCREEN_WIDTH = LOGICAL_SCREEN_WIDTH  # Logical render width
SCREEN_HEIGHT = LOGICAL_SCREEN_HEIGHT  # Logical render height
current_window_scale = DEFAULT_WINDOW_SCALE  # Applied to the OS window only
FPS = 60
STATUS_BAR_HEIGHT = 18

# Level dimensions are driven by the blueprint grid.
LEVEL_GRID_COLS = GRID_COLS
LEVEL_GRID_ROWS = GRID_ROWS
CELL_SIZE = TILE_SIZE
LEVEL_WIDTH = LEVEL_GRID_COLS * CELL_SIZE
LEVEL_HEIGHT = LEVEL_GRID_ROWS * CELL_SIZE

# Player settings
PLAYER_RADIUS = 6
PLAYER_SPEED = 1.4
FOV_RADIUS = 80
FOG_RADIUS_SCALE = 1.2
FOG_MAX_RADIUS_FACTOR = 1.55
FOG_HATCH_PIXEL_SCALE = 1
# Companion settings (Stage 3)
COMPANION_RADIUS = PLAYER_RADIUS
COMPANION_FOLLOW_SPEED = PLAYER_SPEED * 0.7
COMPANION_COLOR = (0, 200, 70)

# Flashlight settings (defaults pulled from DEFAULT_CONFIG)
DEFAULT_FLASHLIGHT_BONUS_SCALE = float(
    DEFAULT_CONFIG.get("flashlight", {}).get("bonus_scale", 1.35)
)
FLASHLIGHT_WIDTH = 10
FLASHLIGHT_HEIGHT = 8
FLASHLIGHT_PICKUP_RADIUS = 13
DEFAULT_FLASHLIGHT_SPAWN_COUNT = 2

# Footprint settings
FOOTPRINT_RADIUS = 3
FOOTPRINT_OVERVIEW_RADIUS = 4
FOOTPRINT_COLOR = (110, 200, 255)
FOOTPRINT_STEP_DISTANCE = 40
FOOTPRINT_LIFETIME_MS = 135000
FOOTPRINT_MAX = 320
FOOTPRINT_MIN_FADE = 0.3

# Zombie settings
ZOMBIE_RADIUS = 6
ZOMBIE_SPEED = 0.6
NORMAL_ZOMBIE_SPEED_JITTER = 0.15
ZOMBIE_SPAWN_DELAY_MS = 5000
MAX_ZOMBIES = 400
INITIAL_ZOMBIES_INSIDE = 15
ZOMBIE_MODE_CHANGE_INTERVAL_MS = 5000
ZOMBIE_SIGHT_RANGE = FOV_RADIUS * 2.0
FAST_ZOMBIE_BASE_SPEED = PLAYER_SPEED * 0.83
FAST_ZOMBIE_SPEED_JITTER = 0.075
ZOMBIE_SEPARATION_DISTANCE = ZOMBIE_RADIUS * 2.2

# Car settings
CAR_WIDTH = 15
CAR_HEIGHT = 25
CAR_SPEED = 2
CAR_HEALTH = 20
CAR_WALL_DAMAGE = 1
CAR_ZOMBIE_DAMAGE = 1
CAR_HINT_DELAY_MS_DEFAULT = 300000

# Fuel settings (Stage 2)
FUEL_CAN_WIDTH = 11
FUEL_CAN_HEIGHT = 15
FUEL_PICKUP_RADIUS = 12
FUEL_HINT_DURATION_MS = 1600

# Wall settings
INTERNAL_WALL_GRID_SNAP = CELL_SIZE
INTERNAL_WALL_HEALTH = 40
OUTER_WALL_HEALTH = 9999
STEEL_BEAM_HEALTH = INTERNAL_WALL_HEALTH * 2

# Rendering assets (shared with render module)
FOG_RINGS = [
    FogRing(radius_factor=0.82, thickness=2),
    FogRing(radius_factor=0.99, thickness=4),
    FogRing(radius_factor=1.16, thickness=6),
    FogRing(radius_factor=1.33, thickness=8),
    FogRing(radius_factor=1.5, thickness=12),
]

RENDER_ASSETS = RenderAssets(
    screen_width=SCREEN_WIDTH,
    screen_height=SCREEN_HEIGHT,
    status_bar_height=STATUS_BAR_HEIGHT,
    player_radius=PLAYER_RADIUS,
    fov_radius=FOV_RADIUS,
    fog_radius_scale=FOG_RADIUS_SCALE,
    fog_max_radius_factor=FOG_MAX_RADIUS_FACTOR,
    fog_hatch_pixel_scale=FOG_HATCH_PIXEL_SCALE,
    fog_rings=FOG_RINGS,
    footprint_radius=FOOTPRINT_RADIUS,
    footprint_overview_radius=FOOTPRINT_OVERVIEW_RADIUS,
    footprint_lifetime_ms=FOOTPRINT_LIFETIME_MS,
    footprint_min_fade=FOOTPRINT_MIN_FADE,
    internal_wall_grid_snap=INTERNAL_WALL_GRID_SNAP,
    default_flashlight_bonus_scale=DEFAULT_FLASHLIGHT_BONUS_SCALE,
)


@dataclass
class Areas:
    """Container for level area rectangles."""

    outer_rect: Tuple[int, int, int, int]
    inner_rect: Tuple[int, int, int, int]
    outside_rects: list[pygame.Rect]
    walkable_cells: list[pygame.Rect]


@dataclass
class ProgressState:
    """Game progress/state flags."""

    game_over: bool
    game_won: bool
    game_over_message: str | None
    game_over_at: int | None
    overview_surface: surface.Surface | None
    scaled_overview: surface.Surface | None
    overview_created: bool
    last_zombie_spawn_time: int
    footprints: list
    last_footprint_pos: tuple | None
    elapsed_play_ms: int
    has_fuel: bool
    has_flashlight: bool
    hint_expires_at: int
    hint_target_type: str | None
    fuel_message_until: int
    companion_rescued: bool


@dataclass
class Groups:
    """Sprite groups container."""

    all_sprites: sprite.LayeredUpdates
    wall_group: sprite.Group
    zombie_group: sprite.Group


@dataclass
class GameData:
    """Lightweight container for game state."""

    state: "ProgressState"
    groups: Groups
    camera: "Camera"
    areas: "Areas"
    fog: dict
    config: dict
    stage: "Stage"
    fuel: Optional["FuelCan"] = None
    flashlights: List["Flashlight"] | None = None
    player: Optional["Player"] = None
    car: Optional["Car"] = None
    companion: Optional["Companion"] = None


@dataclass(frozen=True)
class Stage:
    id: str
    name: str
    description: str
    available: bool = True
    requires_fuel: bool = False
    requires_companion: bool = False


# Stage metadata (stage 2 placeholder for fuel flow coming soon)
STAGES = [
    Stage(
        id="stage1",
        name="#1 Find the Car",
        description="Locate the car and drive out to escape.",
        available=True,
    ),
    Stage(
        id="stage2",
        name="#2 Fuel Run",
        description="Find fuel, bring it to the car, then escape.",
        available=True,
        requires_fuel=True,
    ),
    Stage(
        id="stage3",
        name="#3 Rescue Buddy",
        description="Find your stranded buddy, pick up fuel, and escape together.",
        available=True,
        requires_companion=True,
        requires_fuel=True,
    ),
]
DEFAULT_STAGE_ID = "stage1"


# --- Window scaling helpers ---
def apply_window_scale(
    scale: float, game_data: Optional[GameData] = None
) -> surface.Surface:
    """Resize the OS window; the logical render surface stays at the default size."""
    global current_window_scale

    clamped_scale = max(WINDOW_SCALE_MIN, min(WINDOW_SCALE_MAX, scale))
    current_window_scale = clamped_scale

    window_width = max(1, int(RENDER_SCREEN_WIDTH * current_window_scale))
    window_height = max(1, int(RENDER_SCREEN_HEIGHT * current_window_scale))

    new_window = pygame.display.set_mode((window_width, window_height))
    pygame.display.set_caption(
        f"Zombie Escape v{__version__} ({window_width}x{window_height})"
    )

    if game_data is not None:
        # Invalidate cached overview so it can be re-scaled next time it's drawn
        game_data.state.overview_created = False

    return new_window


def nudge_window_scale(
    multiplier: float, game_data: Optional[dict] = None
) -> surface.Surface:
    """Change window scale relative to the current setting."""
    target_scale = current_window_scale * multiplier
    return apply_window_scale(target_scale, game_data)


def present(logical_surface: surface.Surface) -> None:
    """Scale the logical surface directly to the window and flip buffers."""
    window = pygame.display.get_surface()
    if window is None:
        return
    window_size = window.get_size()
    logical_size = logical_surface.get_size()
    if window_size == logical_size:
        window.blit(logical_surface, (0, 0))
    else:
        pygame.transform.scale(logical_surface, window_size, window)
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
        on_destroy: Optional[Callable[[Self], None]] = None,
    ) -> None:
        super().__init__()
        safe_width = max(1, width)
        safe_height = max(1, height)
        self.image = pygame.Surface((safe_width, safe_height))
        self.base_color = color
        self.border_base_color = border_color
        self.health = health
        self.max_health = max(1, health)
        self.on_destroy = on_destroy
        self.update_color()
        self.rect = self.image.get_rect(topleft=(x, y))

    def take_damage(self: Self, amount: int = 1) -> None:
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


class SteelBeam(pygame.sprite.Sprite):
    """Single-cell obstacle that behaves like a tougher internal wall."""

    def __init__(
        self: Self, x: int, y: int, size: int, health: int = STEEL_BEAM_HEALTH
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

    def take_damage(self: Self, amount: int = 1) -> None:
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

    def teleport(self: Self, pos: Tuple[int, int]) -> None:
        """Reposition the companion (used for quiet respawns)."""
        self.x, self.y = float(pos[0]), float(pos[1])
        self.rect.center = (int(self.x), int(self.y))
        self.following = False

    def update_follow(
        self: Self, target_pos: Tuple[float, float], walls: pygame.sprite.Group
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


def create_zombie(
    config,
    start_pos: Optional[Tuple[int, int]] = None,
    hint_pos: Optional[Tuple[float, float]] = None,
) -> "Zombie":
    """Factory to create zombies with optional fast variants."""
    fast_conf = config.get("fast_zombies", {}) if config else {}
    fast_enabled = fast_conf.get("enabled", True)
    if fast_enabled:
        base_speed = random.uniform(ZOMBIE_SPEED, FAST_ZOMBIE_BASE_SPEED)
        is_fast = base_speed > ZOMBIE_SPEED
    else:
        base_speed = ZOMBIE_SPEED
        is_fast = False
    base_speed = min(base_speed, PLAYER_SPEED - 0.05)
    return Zombie(
        start_pos=start_pos,
        hint_pos=hint_pos,
        speed_override=base_speed,
        is_fast=is_fast,
    )


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
            points.sort(
                key=lambda p: math.hypot(p[0] - hint_pos[0], p[1] - hint_pos[1])
            )
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
        self.mode_change_interval = ZOMBIE_MODE_CHANGE_INTERVAL_MS + random.randint(
            -1000, 1000
        )
        self.was_in_sight = False

    def change_mode(self: Self, force_mode: Optional[ZombieMode] = None) -> None:
        if force_mode:
            self.mode = force_mode
        else:
            possible_modes = list(ZombieMode)
            self.mode = random.choice(possible_modes)
        self.last_mode_change_time = pygame.time.get_ticks()
        self.mode_change_interval = ZOMBIE_MODE_CHANGE_INTERVAL_MS + random.randint(
            -1000, 1000
        )

    def _calculate_movement(
        self: Self, player_center: Tuple[int, int]
    ) -> Tuple[float, float]:
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
            move_y = random.uniform(-self.speed * 0.6, self.speed * 0.6)
        elif self.mode == ZombieMode.FLANK_Y:
            move_x = random.uniform(-self.speed * 0.6, self.speed * 0.6)
            if dist > 0:
                move_y = (
                    (dy_target / abs(dy_target) if dy_target != 0 else 0)
                    * self.speed
                    * 0.8
                )
        return move_x, move_y

    def _handle_wall_collision(
        self: Self, next_x: float, next_y: float, walls: List[Wall]
    ) -> Tuple[float, float]:
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
            angle = random.uniform(0, 2 * math.pi)
            away_dx, away_dy = math.cos(angle), math.sin(angle)
            away_dist = 1

        move_x = (away_dx / away_dist) * self.speed
        move_y = (away_dy / away_dist) * self.speed
        return move_x, move_y

    def update(
        self: Self,
        player_center: Tuple[int, int],
        walls: List[Wall],
        zombies: Iterable["Zombie"],
    ) -> None:
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
        final_x, final_y = self._handle_wall_collision(
            self.x + move_x, self.y + move_y, walls
        )

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
        possible_walls = [
            w
            for w in walls
            if abs(w.rect.centery - self.y) < 100 and abs(w.rect.centerx - new_x) < 100
        ]
        for wall in possible_walls:
            if temp_rect.colliderect(wall.rect):
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


def rect_for_cell(x_idx: int, y_idx: int) -> pygame.Rect:
    return pygame.Rect(x_idx * CELL_SIZE, y_idx * CELL_SIZE, CELL_SIZE, CELL_SIZE)


def generate_level_from_blueprint(game_data):
    """Build walls/spawn candidates/outside area from a blueprint grid."""
    wall_group = game_data.groups.wall_group
    all_sprites = game_data.groups.all_sprites

    config = game_data.config
    steel_conf = config.get("steel_beams", {})
    steel_enabled = steel_conf.get("enabled", False)

    blueprint_data = choose_blueprint(config)
    if isinstance(blueprint_data, dict):
        blueprint = blueprint_data.get("grid", [])
        steel_cells_raw = blueprint_data.get("steel_cells", set())
    else:
        blueprint = blueprint_data
        steel_cells_raw = set()

    steel_cells = (
        {(int(x), int(y)) for x, y in steel_cells_raw} if steel_enabled else set()
    )

    outside_rects: List[pygame.Rect] = []
    walkable_cells: List[pygame.Rect] = []
    player_cells: List[pygame.Rect] = []
    car_cells: List[pygame.Rect] = []
    zombie_cells: List[pygame.Rect] = []

    def add_beam_to_groups(beam: "SteelBeam") -> None:
        if getattr(beam, "_added_to_groups", False):
            return
        wall_group.add(beam)
        all_sprites.add(beam, layer=0)
        beam._added_to_groups = True

    for y, row in enumerate(blueprint):
        if len(row) != LEVEL_GRID_COLS:
            raise ValueError(
                f"Blueprint width mismatch at row {y}: {len(row)} != {LEVEL_GRID_COLS}"
            )
        for x, ch in enumerate(row):
            cell_rect = rect_for_cell(x, y)
            cell_has_beam = steel_enabled and (x, y) in steel_cells
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
                if not cell_has_beam:
                    walkable_cells.append(cell_rect)
            elif ch == "1":
                beam = None
                if cell_has_beam:
                    beam = SteelBeam(
                        cell_rect.x,
                        cell_rect.y,
                        cell_rect.width,
                        health=STEEL_BEAM_HEALTH,
                    )
                wall = Wall(
                    cell_rect.x,
                    cell_rect.y,
                    cell_rect.width,
                    cell_rect.height,
                    health=INTERNAL_WALL_HEALTH,
                    color=INTERNAL_WALL_COLOR,
                    border_color=INTERNAL_WALL_BORDER_COLOR,
                    on_destroy=(lambda _w, b=beam: add_beam_to_groups(b))
                    if beam
                    else None,
                )
                wall_group.add(wall)
                all_sprites.add(wall, layer=0)
                # Embedded beams stay hidden until the wall is destroyed
            else:
                if not cell_has_beam:
                    walkable_cells.append(cell_rect)

            if ch == "P":
                player_cells.append(cell_rect)
            if ch == "C":
                car_cells.append(cell_rect)
            if ch == "Z":
                zombie_cells.append(cell_rect)

            # Standalone beams (non-wall cells) are placed immediately
            if cell_has_beam and ch != "1":
                beam = SteelBeam(
                    cell_rect.x, cell_rect.y, cell_rect.width, health=STEEL_BEAM_HEALTH
                )
                add_beam_to_groups(beam)

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
        nearby_walls.add(
            [
                w
                for w in wall_group
                if abs(w.rect.centerx - c_x) < 150 and abs(w.rect.centery - c_y) < 150
            ]
        )
        collides_wall = pygame.sprite.spritecollideany(
            temp_car, nearby_walls, collided=lambda s1, s2: s1.rect.colliderect(s2.rect)
        )
        collides_player = temp_rect.colliderect(player.rect.inflate(50, 50))
        if not collides_wall and not collides_player:
            return temp_car
    return None


def place_fuel_can(
    walkable_cells: List[pygame.Rect], player: Player, car: Car | None = None
) -> FuelCan | None:
    """Pick a spawn spot for the fuel can away from the player (and car if given)."""
    if not walkable_cells:
        return None

    min_player_dist = 250
    min_car_dist = 200

    for _ in range(200):
        cell = random.choice(walkable_cells)
        if (
            math.hypot(cell.centerx - player.x, cell.centery - player.y)
            < min_player_dist
        ):
            continue
        if (
            car
            and math.hypot(
                cell.centerx - car.rect.centerx, cell.centery - car.rect.centery
            )
            < min_car_dist
        ):
            continue
        return FuelCan(cell.centerx, cell.centery)

    # Fallback: drop near a random walkable cell
    cell = random.choice(walkable_cells)
    return FuelCan(cell.centerx, cell.centery)


def place_flashlight(
    walkable_cells: List[pygame.Rect], player: Player, car: Car | None = None
) -> Flashlight | None:
    """Pick a spawn spot for the flashlight away from the player (and car if given)."""
    if not walkable_cells:
        return None

    min_player_dist = 260
    min_car_dist = 200

    for _ in range(200):
        cell = random.choice(walkable_cells)
        if (
            math.hypot(cell.centerx - player.x, cell.centery - player.y)
            < min_player_dist
        ):
            continue
        if (
            car
            and math.hypot(
                cell.centerx - car.rect.centerx, cell.centery - car.rect.centery
            )
            < min_car_dist
        ):
            continue
        return Flashlight(cell.centerx, cell.centery)

    cell = random.choice(walkable_cells)
    return Flashlight(cell.centerx, cell.centery)


def place_flashlights(
    walkable_cells: List[pygame.Rect],
    player: Player,
    car: Car | None = None,
    count: int = DEFAULT_FLASHLIGHT_SPAWN_COUNT,
) -> list[Flashlight]:
    """Spawn multiple flashlights using the single-place helper to spread them out."""
    placed: list[Flashlight] = []
    attempts = 0
    max_attempts = max(200, count * 80)
    while len(placed) < count and attempts < max_attempts:
        attempts += 1
        fl = place_flashlight(walkable_cells, player, car)
        if not fl:
            break
        # Avoid clustering too tightly
        if any(
            math.hypot(
                other.rect.centerx - fl.rect.centerx,
                other.rect.centery - fl.rect.centery,
            )
            < 120
            for other in placed
        ):
            continue
        placed.append(fl)
    return placed


def place_companion(
    walkable_cells: List[pygame.Rect], player: Player, car: Car | None = None
) -> Companion | None:
    """Spawn the stranded buddy somewhere on a walkable tile away from the player and car."""
    if not walkable_cells:
        return None

    min_player_dist = 240
    min_car_dist = 180

    for _ in range(200):
        cell = random.choice(walkable_cells)
        if (
            math.hypot(cell.centerx - player.x, cell.centery - player.y)
            < min_player_dist
        ):
            continue
        if (
            car
            and math.hypot(
                cell.centerx - car.rect.centerx, cell.centery - car.rect.centery
            )
            < min_car_dist
        ):
            continue
        return Companion(cell.centerx, cell.centery)

    cell = random.choice(walkable_cells)
    return Companion(cell.centerx, cell.centery)


def respawn_rescued_companion_near_player(game_data) -> None:
    """Bring back the rescued companion near the player after losing the car."""
    if not (game_data.stage.requires_companion and game_data.state.companion_rescued):
        return
    # If a companion is already active, do nothing
    if (
        game_data.companion
        and game_data.companion.alive()
        and not game_data.companion.rescued
    ):
        return

    player = game_data.player
    wall_group = game_data.groups.wall_group
    offsets = [
        (COMPANION_RADIUS * 3, 0),
        (-COMPANION_RADIUS * 3, 0),
        (0, COMPANION_RADIUS * 3),
        (0, -COMPANION_RADIUS * 3),
        (0, 0),
    ]
    spawn_pos = (int(player.x), int(player.y))
    for dx, dy in offsets:
        candidate = Companion(player.x + dx, player.y + dy)
        if not pygame.sprite.spritecollideany(candidate, wall_group):
            spawn_pos = (candidate.x, candidate.y)
            break

    companion = Companion(*spawn_pos)
    companion.following = True
    game_data.companion = companion
    game_data.groups.all_sprites.add(companion, layer=2)


def get_shrunk_sprite(
    sprite: pygame.sprite.Sprite, scale_x: float, scale_y: Optional[float] = None
) -> sprite.Sprite:
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


def update_footprints(game_data) -> None:
    """Record player steps and clean up old footprints."""
    state = game_data.state
    player: Player = game_data.player
    config = game_data.config

    footprints_enabled = config.get("footprints", {}).get("enabled", True)
    if not footprints_enabled:
        state.footprints = []
        state.last_footprint_pos = None
        return

    now = pygame.time.get_ticks()

    footprints = state.footprints
    if not player.in_car:
        last_pos = state.last_footprint_pos
        dist = (
            math.hypot(player.x - last_pos[0], player.y - last_pos[1])
            if last_pos
            else None
        )
        if last_pos is None or (dist is not None and dist >= FOOTPRINT_STEP_DISTANCE):
            footprints.append({"pos": (player.x, player.y), "time": now})
            state.last_footprint_pos = (player.x, player.y)

    if len(footprints) > FOOTPRINT_MAX:
        footprints = footprints[-FOOTPRINT_MAX:]

    state.footprints = footprints


# --- Game State Function (Contains the main game loop) ---
def initialize_game_state(config, stage: Stage):
    """Initialize and return the base game state objects."""
    starts_with_fuel = not stage.requires_fuel
    starts_with_flashlight = False
    game_state = ProgressState(
        game_over=False,
        game_won=False,
        game_over_message=None,
        game_over_at=None,
        overview_surface=None,
        scaled_overview=None,
        overview_created=False,
        last_zombie_spawn_time=0,
        footprints=[],
        last_footprint_pos=None,
        elapsed_play_ms=0,
        has_fuel=starts_with_fuel,
        has_flashlight=starts_with_flashlight,
        hint_expires_at=0,
        hint_target_type=None,
        fuel_message_until=0,
        companion_rescued=False,
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
        groups=Groups(
            all_sprites=all_sprites, wall_group=wall_group, zombie_group=zombie_group
        ),
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
        flashlights=[],
        companion=None,
    )


def setup_player_and_car(game_data, layout_data):
    """Create and position the player and car using blueprint candidates."""
    all_sprites = game_data.groups.all_sprites
    walkable_cells: List[pygame.Rect] = layout_data["walkable_cells"]

    def pick_center(cells: List[pygame.Rect]) -> Tuple[int, int]:
        return (
            random.choice(cells).center
            if cells
            else (LEVEL_WIDTH // 2, LEVEL_HEIGHT // 2)
        )

    player_pos = pick_center(layout_data["player_cells"] or walkable_cells)
    player = Player(*player_pos)

    # Place car away from player
    car_candidates = layout_data["car_cells"] or walkable_cells
    car_pos = None
    for _ in range(200):
        candidate = random.choice(car_candidates)
        if (
            math.hypot(
                candidate.centerx - player_pos[0], candidate.centery - player_pos[1]
            )
            >= 400
        ):
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
    config = game_data.config
    wall_group = game_data.groups.wall_group
    zombie_group = game_data.groups.zombie_group
    all_sprites = game_data.groups.all_sprites

    spawn_cells = layout_data["zombie_cells"] or layout_data["walkable_cells"]
    if not spawn_cells:
        return

    initial_zombies_placed = 0
    placement_attempts = 0
    max_placement_attempts = INITIAL_ZOMBIES_INSIDE * 20
    min_spawn_separation = ZOMBIE_SEPARATION_DISTANCE

    while (
        initial_zombies_placed < INITIAL_ZOMBIES_INSIDE
        and placement_attempts < max_placement_attempts
    ):
        placement_attempts += 1
        cell = random.choice(spawn_cells)
        jitter_x = random.uniform(-cell.width * 0.4, cell.width * 0.4)
        jitter_y = random.uniform(-cell.height * 0.4, cell.height * 0.4)
        z_pos = (cell.centerx + jitter_x, cell.centery + jitter_y)
        temp_zombie = create_zombie(config, start_pos=z_pos)
        temp_sprite = pygame.sprite.Sprite()
        temp_sprite.rect = temp_zombie.rect.inflate(5, 5)

        collides_with_wall = pygame.sprite.spritecollideany(temp_sprite, wall_group)
        collides_with_player = temp_sprite.rect.colliderect(
            player.rect.inflate(ZOMBIE_SIGHT_RANGE, ZOMBIE_SIGHT_RANGE)
        )
        too_close_to_zombie = any(
            math.hypot(temp_zombie.rect.centerx - z.x, temp_zombie.rect.centery - z.y)
            < min_spawn_separation
            for z in zombie_group
        )

        if (
            not collides_with_wall
            and not collides_with_player
            and not too_close_to_zombie
        ):
            new_zombie = temp_zombie
            zombie_group.add(new_zombie)
            all_sprites.add(new_zombie, layer=1)
            initial_zombies_placed += 1

    game_data.state.last_zombie_spawn_time = (
        pygame.time.get_ticks() - ZOMBIE_SPAWN_DELAY_MS
    )


def handle_game_over_state(screen, game_data):
    """Handle rendering and input when game is over or won."""
    state = game_data.state
    wall_group = game_data.groups.wall_group
    config = game_data.config
    footprints_enabled = config.get("footprints", {}).get("enabled", True)

    # Create overview map if needed
    if not state.overview_created:
        state.overview_surface = pygame.Surface((LEVEL_WIDTH, LEVEL_HEIGHT))
        footprints_to_draw = state.footprints if footprints_enabled else []
        draw_level_overview(
            RENDER_ASSETS,
            state.overview_surface,
            wall_group,
            game_data.player,
            game_data.car,
            footprints_to_draw,
            fuel=game_data.fuel,
            flashlights=game_data.flashlights or [],
            stage=game_data.stage,
            companion=game_data.companion,
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

        state.scaled_overview = pygame.transform.smoothscale(
            state.overview_surface, (scaled_w, scaled_h)
        )
        state.overview_created = True

    # Display overview map and messages
    screen.fill(BLACK)
    if state.scaled_overview:
        screen.blit(
            state.scaled_overview,
            state.scaled_overview.get_rect(
                center=(SCREEN_WIDTH // 2, SCREEN_HEIGHT // 2)
            ),
        )

        if state.game_won:
            show_message(
                screen,
                "YOU ESCAPED!",
                22,
                GREEN,
                (SCREEN_WIDTH // 2, SCREEN_HEIGHT // 2 - 26),
            )
        else:
            show_message(
                screen,
                "GAME OVER",
                22,
                RED,
                (SCREEN_WIDTH // 2, SCREEN_HEIGHT // 2 - 26),
            )
            if state.game_over_message:
                show_message(
                    screen,
                    state.game_over_message,
                    18,
                    LIGHT_GRAY,
                    (SCREEN_WIDTH // 2, SCREEN_HEIGHT // 2 + 6),
                )

    show_message(
        screen,
        "Press ESC or SPACE to return to Title",
        18,
        WHITE,
        (SCREEN_WIDTH // 2, SCREEN_HEIGHT // 2 + 24),
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
            car_dx, car_dy = (
                (dx_input / move_len) * target_speed,
                (dy_input / move_len) * target_speed,
            )
    elif not player.in_car:
        target_speed = PLAYER_SPEED
        move_len = math.hypot(dx_input, dy_input)
        if move_len > 0:
            player_dx, player_dy = (
                (dx_input / move_len) * target_speed,
                (dy_input / move_len) * target_speed,
            )

    return player_dx, player_dy, car_dx, car_dy


def update_entities(game_data, player_dx, player_dy, car_dx, car_dy):
    """Update positions and states of game entities."""
    player = game_data.player
    car = game_data.car
    companion = game_data.companion
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

    # Update companion (Stage 3 follow logic)
    if companion and companion.alive() and not companion.rescued:
        follow_target = car if player.in_car and car.alive() else player
        companion.update_follow(follow_target.rect.center, wall_group)
        if companion not in all_sprites:
            all_sprites.add(companion, layer=2)

    # Spawn new zombies if needed
    current_time = pygame.time.get_ticks()
    if (
        len(zombie_group) < MAX_ZOMBIES
        and current_time - game_data.state.last_zombie_spawn_time
        > ZOMBIE_SPAWN_DELAY_MS
    ):
        new_zombie = create_zombie(config, hint_pos=(player.x, player.y))
        zombie_group.add(new_zombie)
        all_sprites.add(new_zombie, layer=1)
        game_data.state.last_zombie_spawn_time = current_time

    # Update zombies
    target_center = (
        car.rect.center if player.in_car and car.alive() else player.rect.center
    )
    companion_on_screen = False
    screen_rect = pygame.Rect(0, 0, SCREEN_WIDTH, SCREEN_HEIGHT)
    if (
        game_data.stage.requires_companion
        and companion
        and companion.alive()
        and not companion.rescued
    ):
        companion_on_screen = camera.apply_rect(companion.rect).colliderect(screen_rect)
    for zombie in zombie_group:
        target = target_center
        if companion_on_screen and companion:
            dist_to_target = math.hypot(
                target_center[0] - zombie.x, target_center[1] - zombie.y
            )
            dist_to_companion = math.hypot(
                companion.rect.centerx - zombie.x, companion.rect.centery - zombie.y
            )
            if dist_to_companion < dist_to_target:
                target = companion.rect.center
        zombie.update(target, wall_group, zombie_group)


def check_interactions(game_data):
    """Check and handle interactions between entities."""
    player = game_data.player
    car = game_data.car
    companion = game_data.companion
    zombie_group = game_data.groups.zombie_group
    wall_group = game_data.groups.wall_group
    all_sprites = game_data.groups.all_sprites
    state = game_data.state
    walkable_cells = game_data.areas.walkable_cells
    outside_rects = game_data.areas.outside_rects
    fuel = game_data.fuel
    flashlights = game_data.flashlights or []
    camera = game_data.camera
    stage = game_data.stage

    # Fuel pickup
    if fuel and fuel.alive() and not state.has_fuel and not player.in_car:
        dist_to_fuel = math.hypot(
            fuel.rect.centerx - player.x, fuel.rect.centery - player.y
        )
        if dist_to_fuel <= max(FUEL_PICKUP_RADIUS, PLAYER_RADIUS + 6):
            state.has_fuel = True
            state.fuel_message_until = 0
            state.hint_expires_at = 0
            state.hint_target_type = None
            fuel.kill()
            game_data.fuel = None
            print("Fuel acquired!")

    # Flashlight pickup
    if not state.has_flashlight and not player.in_car:
        for flashlight in list(flashlights):
            if not flashlight.alive():
                continue
            dist_to_flashlight = math.hypot(
                flashlight.rect.centerx - player.x, flashlight.rect.centery - player.y
            )
            if dist_to_flashlight <= max(FLASHLIGHT_PICKUP_RADIUS, PLAYER_RADIUS + 6):
                state.has_flashlight = True
                state.hint_expires_at = 0
                state.hint_target_type = None
                flashlight.kill()
                try:
                    flashlights.remove(flashlight)
                except ValueError:
                    pass
                print("Flashlight acquired!")
                break

    companion_on_screen = False
    companion_active = (
        companion and companion.alive() and not getattr(companion, "rescued", False)
    )
    if companion_active:
        screen_rect = pygame.Rect(0, 0, SCREEN_WIDTH, SCREEN_HEIGHT)
        companion_on_screen = camera.apply_rect(companion.rect).colliderect(screen_rect)

    # Companion interactions (Stage 3)
    if companion_active and stage.requires_companion:
        if not player.in_car:
            if pygame.sprite.collide_circle(companion, player):
                companion.set_following()
        elif player.in_car and car.alive():
            g = pygame.sprite.Group()
            g.add(companion)
            if pygame.sprite.spritecollide(get_shrunk_sprite(car, 0.8), g, False):
                state.companion_rescued = True
                companion.mark_rescued()
                companion.kill()
                game_data.companion = None
                companion_active = False
                companion_on_screen = False

        # Zombies reaching the companion
        if companion_active and pygame.sprite.spritecollide(
            companion, zombie_group, False, pygame.sprite.collide_circle
        ):
            if companion_on_screen:
                state.game_over_message = "AAAAHHH!!"
                state.game_over = True
                state.game_over_at = state.game_over_at or pygame.time.get_ticks()
            else:
                if walkable_cells:
                    new_cell = random.choice(walkable_cells)
                    companion.teleport(new_cell.center)
                else:
                    companion.teleport((LEVEL_WIDTH // 2, LEVEL_HEIGHT // 2))
                companion.following = False

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
                # Keep hint timing unchanged so the car visit doesn't immediately reveal fuel
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

        # Bring back the rescued companion near the player after losing the car
        respawn_rescued_companion_near_player(game_data)

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
        if pygame.sprite.spritecollide(
            shrunk_player, zombie_group, False, pygame.sprite.collide_circle
        ):
            if not state.game_over:
                state.game_over = True
                state.game_over_at = pygame.time.get_ticks()
                state.game_over_message = "AAAHHH!!"

    # Player escaping the level
    if player.in_car and car.alive() and state.has_fuel:
        companion_ready = not stage.requires_companion or state.companion_rescued
        if companion_ready and any(
            outside.collidepoint(car.rect.center) for outside in outside_rects
        ):
            state.game_won = True

    # Return fog of view target
    if not state.game_over and not state.game_won:
        return car if player.in_car and car.alive() else player
    return None


def run_game(
    screen: surface.Surface,
    clock: time.Clock,
    config,
    stage: Stage,
    show_pause_overlay: bool = True,
) -> bool:
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

    flashlight_conf = config.get("flashlight", {})
    flashlights_enabled = flashlight_conf.get("enabled", True)
    raw_flashlight_count = flashlight_conf.get("count", DEFAULT_FLASHLIGHT_SPAWN_COUNT)
    try:
        flashlight_count = int(raw_flashlight_count)
    except (TypeError, ValueError):
        flashlight_count = DEFAULT_FLASHLIGHT_SPAWN_COUNT

    # Stage-specific collectibles (fuel for Stage 2)
    if stage.requires_fuel:
        fuel_can = place_fuel_can(layout_data["walkable_cells"], player, car)
        if fuel_can:
            game_data.fuel = fuel_can
            game_data.groups.all_sprites.add(fuel_can, layer=1)
    if flashlights_enabled:
        flashlights = place_flashlights(
            layout_data["walkable_cells"], player, car, count=max(1, flashlight_count)
        )
        game_data.flashlights = flashlights
        game_data.groups.all_sprites.add(flashlights, layer=1)

    if stage.requires_companion:
        companion = place_companion(layout_data["walkable_cells"], player, car)
        if companion:
            game_data.companion = companion
            game_data.groups.all_sprites.add(companion, layer=2)

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
        if game_data.state.game_over or game_data.state.game_won:
            if game_data.state.game_over and not game_data.state.game_won:
                if game_data.state.game_over_at is None:
                    game_data.state.game_over_at = pygame.time.get_ticks()
                if pygame.time.get_ticks() - game_data.state.game_over_at < 1000:
                    # Keep rendering the current view (with fog) before showing the game-over screen.
                    draw(
                        RENDER_ASSETS,
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
                        None,
                        outside_rects=game_data.areas.outside_rects,
                        stage=stage,
                        has_fuel=game_data.state.has_fuel,
                        has_flashlight=game_data.state.has_flashlight,
                        elapsed_play_ms=game_data.state.elapsed_play_ms,
                        fuel_message_until=game_data.state.fuel_message_until,
                        companion=game_data.companion,
                        companion_rescued=game_data.state.companion_rescued,
                        present_fn=present,
                    )
                    if game_data.state.game_over_message:
                        show_message(
                            screen,
                            game_data.state.game_over_message,
                            18,
                            RED,
                            (SCREEN_WIDTH // 2, SCREEN_HEIGHT // 2 - 24),
                        )
                        present(screen)
                    continue
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
                if event.key == pygame.K_s and (
                    pygame.key.get_mods() & pygame.KMOD_CTRL
                ):
                    state_snapshot = {
                        k: v for k, v in game_data.state.items() if k != "footprints"
                    }
                    print("STATE DEBUG:", state_snapshot)
                    continue
                if event.key == pygame.K_ESCAPE:
                    return True
                if event.key == pygame.K_p:
                    paused_manual = not paused_manual

        paused = paused_manual or paused_focus
        if paused:
            draw(
                RENDER_ASSETS,
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
                has_flashlight=game_data.state.has_flashlight,
                elapsed_play_ms=game_data.state.elapsed_play_ms,
                fuel_message_until=game_data.state.fuel_message_until,
                companion=game_data.companion,
                companion_rescued=game_data.state.companion_rescued,
                present_fn=present,
            )
            if show_pause_overlay:
                overlay = pygame.Surface((SCREEN_WIDTH, SCREEN_HEIGHT), pygame.SRCALPHA)
                overlay.fill((0, 0, 0, 150))
                pygame.draw.circle(
                    overlay,
                    LIGHT_GRAY,
                    (SCREEN_WIDTH // 2, SCREEN_HEIGHT // 2),
                    35,
                    width=3,
                )
                bar_width = 8
                bar_height = 30
                gap = 9
                cx, cy = SCREEN_WIDTH // 2, SCREEN_HEIGHT // 2
                pygame.draw.rect(
                    overlay,
                    LIGHT_GRAY,
                    (cx - gap - bar_width, cy - bar_height // 2, bar_width, bar_height),
                )
                pygame.draw.rect(
                    overlay,
                    LIGHT_GRAY,
                    (cx + gap, cy - bar_height // 2, bar_width, bar_height),
                )
                screen.blit(overlay, (0, 0))
                show_message(
                    screen,
                    "PAUSED",
                    18,
                    WHITE,
                    (SCREEN_WIDTH // 2, SCREEN_HEIGHT // 2 + 24),
                )
                show_message(
                    screen,
                    "Press P or click to resume",
                    18,
                    LIGHT_GRAY,
                    (SCREEN_WIDTH // 2, SCREEN_HEIGHT // 2 + 70),
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
        elapsed_ms = game_data.state.elapsed_play_ms
        has_fuel = game_data.state.has_fuel
        has_flashlight = game_data.state.has_flashlight
        hint_enabled = car_hint_conf.get("enabled", True)
        hint_target = None
        hint_color = YELLOW
        hint_expires_at = game_data.state.hint_expires_at
        hint_target_type = game_data.state.hint_target_type

        if hint_enabled:
            if not has_fuel and game_data.fuel and game_data.fuel.alive():
                target_type = "fuel"
            elif not player.in_car and game_data.car.alive():
                target_type = "car"
            else:
                target_type = None

            if target_type != hint_target_type:
                game_data.state.hint_target_type = target_type
                game_data.state.hint_expires_at = (
                    elapsed_ms + hint_delay if target_type else 0
                )
                hint_expires_at = game_data.state.hint_expires_at
                hint_target_type = target_type

            if (
                target_type
                and hint_expires_at
                and elapsed_ms >= hint_expires_at
                and not player.in_car
            ):
                if target_type == "fuel" and game_data.fuel and game_data.fuel.alive():
                    hint_target = game_data.fuel.rect.center
                elif target_type == "car" and game_data.car.alive():
                    hint_target = game_data.car.rect.center

        draw(
            RENDER_ASSETS,
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
            has_flashlight=game_data.state.has_flashlight,
            elapsed_play_ms=game_data.state.elapsed_play_ms,
            fuel_message_until=game_data.state.fuel_message_until,
            companion=game_data.companion,
            companion_rescued=game_data.state.companion_rescued,
            present_fn=present,
        )

    return False


# --- Splash & Menu Functions ---
def title_screen(screen: surface.Surface, clock: time.Clock, config) -> dict:
    """Title menu with inline stage selection. Returns action dict: {'action': 'stage'|'settings'|'quit', 'stage': Stage|None}."""
    options = [{"type": "stage", "stage": s, "available": s.available} for s in STAGES]
    options += [{"type": "settings"}, {"type": "quit"}]
    selected = next(
        (
            i
            for i, opt in enumerate(options)
            if opt["type"] == "stage" and opt["stage"].id == DEFAULT_STAGE_ID
        ),
        0,
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
        show_message(
            screen,
            "Zombie Escape",
            36,
            LIGHT_GRAY,
            (SCREEN_WIDTH // 2, SCREEN_HEIGHT // 2 - 88),
        )

        try:
            font = load_font(20)
            line_height = 22
            start_y = SCREEN_HEIGHT // 2 - 36
            for idx, option in enumerate(options):
                if option["type"] == "stage":
                    label = option["stage"].name
                    if not option.get("available"):
                        label += " [Locked]"
                    color = (
                        YELLOW
                        if idx == selected
                        else (WHITE if option.get("available") else GRAY)
                    )
                elif option["type"] == "settings":
                    label = "Settings"
                    color = YELLOW if idx == selected else WHITE
                else:
                    label = "Quit"
                    color = YELLOW if idx == selected else WHITE

                text_surface = font.render(label, False, color)
                text_rect = text_surface.get_rect(
                    center=(SCREEN_WIDTH // 2, start_y + idx * line_height)
                )
                screen.blit(text_surface, text_rect)

            # Selected stage description (if a stage is highlighted)
            current = options[selected]
            if current["type"] == "stage":
                desc_font = load_font(12)
                desc_color = LIGHT_GRAY if current.get("available") else GRAY
                desc_surface = desc_font.render(
                    current["stage"].description, False, desc_color
                )
                desc_rect = desc_surface.get_rect(
                    center=(SCREEN_WIDTH // 2, SCREEN_HEIGHT // 2 + 74)
                )
                screen.blit(desc_surface, desc_rect)

            # Quick config summary
            fast_on = config.get("fast_zombies", {}).get("enabled", True)
            hint_on = config.get("car_hint", {}).get("enabled", True)

            hint_font = load_font(12)
            hint_text = "Resize window: [ to shrink, ] to enlarge (menu only)"
            hint_surface = hint_font.render(hint_text, False, LIGHT_GRAY)
            hint_rect = hint_surface.get_rect(
                center=(SCREEN_WIDTH // 2, SCREEN_HEIGHT - 50)
            )
            screen.blit(hint_surface, hint_rect)
        except pygame.error as e:
            print(f"Error rendering title screen: {e}")

        present(screen)
        clock.tick(FPS)


def settings_screen(
    screen: surface.Surface, clock: time.Clock, config, config_path
) -> dict:
    """Settings menu shown from the title screen."""
    working = copy.deepcopy(config)
    selected = 0
    row_count = 0

    def set_value(path: tuple[str, str], value: bool) -> None:
        """Set a nested boolean flag in the working config."""
        root_key, child_key = path
        working.setdefault(root_key, {})[child_key] = value

    def toggle_value(path: tuple[str, str]) -> None:
        """Toggle a nested boolean flag in the working config."""
        root_key, child_key = path
        current = working.get(root_key, {}).get(child_key, True)
        working.setdefault(root_key, {})[child_key] = not current

    sections = [
        {
            "label": "Player support",
            "rows": [
                {
                    "label": "Footprints",
                    "path": ("footprints", "enabled"),
                    "easy_value": True,
                    "left_label": "ON",
                    "right_label": "OFF",
                },
                {
                    "label": "Car hint",
                    "path": ("car_hint", "enabled"),
                    "easy_value": True,
                    "left_label": "ON",
                    "right_label": "OFF",
                },
                {
                    "label": "Flashlight pickups",
                    "path": ("flashlight", "enabled"),
                    "easy_value": True,
                    "left_label": "ON",
                    "right_label": "OFF",
                },
            ],
        },
        {
            "label": "Tougher enemies",
            "rows": [
                {
                    "label": "Fast zombies",
                    "path": ("fast_zombies", "enabled"),
                    "easy_value": False,
                    "left_label": "OFF",
                    "right_label": "ON",
                },
                {
                    "label": "Steel beams",
                    "path": ("steel_beams", "enabled"),
                    "easy_value": False,
                    "left_label": "OFF",
                    "right_label": "ON",
                },
            ],
        },
    ]
    rows = [row for section in sections for row in section["rows"]]
    row_sections = [section["label"] for section in sections for _ in section["rows"]]
    row_count = len(rows)

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
                    selected = (selected - 1) % row_count
                if event.key in (pygame.K_DOWN, pygame.K_s):
                    selected = (selected + 1) % row_count
                if event.key in (pygame.K_SPACE, pygame.K_RETURN):
                    toggle_value(rows[selected]["path"])
                if event.key == pygame.K_LEFT:
                    set_value(rows[selected]["path"], rows[selected]["easy_value"])
                if event.key == pygame.K_RIGHT:
                    set_value(rows[selected]["path"], not rows[selected]["easy_value"])
                if event.key == pygame.K_r:
                    working = copy.deepcopy(DEFAULT_CONFIG)

        screen.fill(BLACK)
        show_message(screen, "Settings", 26, LIGHT_GRAY, (SCREEN_WIDTH // 2, 20))

        try:
            label_font = load_font(12)
            value_font = load_font(12)
            section_font = load_font(12)
            highlight_color = (70, 70, 70)

            row_height = 18
            start_y = 44

            segment_width = 26
            segment_height = 16
            segment_gap = 8
            segment_total_width = segment_width * 2 + segment_gap

            column_margin = 20
            column_width = SCREEN_WIDTH // 2 - column_margin * 2
            section_spacing = 6

            section_states = {}
            y_cursor = start_y
            for section in sections:
                header_surface = section_font.render(
                    section["label"], False, LIGHT_GRAY
                )
                section_states[section["label"]] = {
                    "next_y": y_cursor + header_surface.get_height() + 6,
                    "header_surface": header_surface,
                    "header_pos": (column_margin, y_cursor),
                }
                rows_in_section = len(section["rows"])
                y_cursor = (
                    section_states[section["label"]]["next_y"]
                    + rows_in_section * row_height
                    + section_spacing
                )

            for state in section_states.values():
                screen.blit(state["header_surface"], state["header_pos"])

            for idx, row in enumerate(rows):
                section_label = row_sections[idx]
                state = section_states[section_label]
                col_x = column_margin
                enabled = working.get(row["path"][0], {}).get(
                    row["path"][1], row["easy_value"]
                )
                row_y_current = state["next_y"]
                state["next_y"] += row_height

                highlight_rect = pygame.Rect(
                    col_x, row_y_current - 2, column_width, row_height - 4
                )
                if idx == selected:
                    pygame.draw.rect(screen, highlight_color, highlight_rect)

                label_surface = label_font.render(row["label"], False, WHITE)
                label_rect = label_surface.get_rect(
                    topleft=(
                        col_x,
                        row_y_current + (row_height - label_surface.get_height()) // 2,
                    )
                )
                screen.blit(label_surface, label_rect)

                slider_y = row_y_current + (row_height - segment_height) // 2 - 2
                slider_x = col_x + column_width - segment_total_width
                left_rect = pygame.Rect(
                    slider_x, slider_y, segment_width, segment_height
                )
                right_rect = pygame.Rect(
                    left_rect.right + segment_gap,
                    slider_y,
                    segment_width,
                    segment_height,
                )

                left_active = enabled == row["easy_value"]
                right_active = not left_active

                def draw_segment(rect: pygame.Rect, text: str, active: bool):
                    base_color = (35, 35, 35)
                    active_color = (60, 90, 60) if active else base_color
                    outline_color = GREEN if active else LIGHT_GRAY
                    pygame.draw.rect(screen, active_color, rect)
                    pygame.draw.rect(screen, outline_color, rect, width=2)
                    text_surface = value_font.render(text, False, WHITE)
                    text_rect = text_surface.get_rect(center=rect.center)
                    screen.blit(text_surface, text_rect)

                draw_segment(left_rect, row["left_label"], left_active)
                draw_segment(right_rect, row["right_label"], right_active)

            hint_start_y = start_y
            hint_start_x = SCREEN_WIDTH // 2 + 16
            hint_font = load_font(12)
            hint_lines = [
                "Up/Down: select a setting",
                "Left/Right: set value",
                "Space/Enter: toggle value",
                "R: reset to defaults",
                "Esc/Backspace: save and return",
            ]
            for i, line in enumerate(hint_lines):
                hint_surface = hint_font.render(line, False, WHITE)
                hint_rect = hint_surface.get_rect(
                    topleft=(hint_start_x, hint_start_y + i * 18)
                )
                screen.blit(hint_surface, hint_rect)

            path_font = load_font(12)
            path_text = f"Config: {config_path}"
            path_surface = path_font.render(path_text, False, LIGHT_GRAY)
            path_rect = path_surface.get_rect(
                midtop=(SCREEN_WIDTH // 2, SCREEN_HEIGHT - 32)
            )
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
                restart_game = run_game(
                    screen,
                    clock,
                    config,
                    selection["stage"],
                    show_pause_overlay=not hide_pause_overlay,
                )
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
