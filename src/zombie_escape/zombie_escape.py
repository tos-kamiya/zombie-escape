from typing import List, Optional, Self, Tuple, Union
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
SCREEN_WIDTH = 800
SCREEN_HEIGHT = 600
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
FOG_COLOR = (0, 0, 0, 255)
FOG_COLOR_SOFT = (0, 0, 0, 190)
FLOOR_COLOR_PRIMARY = (47, 52, 58)  # #2f343a
FLOOR_COLOR_SECONDARY = (58, 65, 73)  # #3a4149

# Player settings
PLAYER_RADIUS = 11
PLAYER_SPEED = 2.8
FOV_RADIUS = 180
FOV_RADIUS_SOFT_FACTOR = 1.5
FOG_RADIUS_SCALE = 1.2
FOG_MAX_RADIUS_FACTOR = 1.55
FOG_HATCH_DEFAULT_SPACING = 18
FOG_HATCH_THICKNESS = 7
FOG_HATCH_PIXEL_SCALE = 3
FOG_RINGS = [
    {"radius_factor": 0.9, "alpha": 130, "spacing": 20},
    {"radius_factor": 1.1, "alpha": 190, "spacing": 16},
    {"radius_factor": 1.3, "alpha": 240, "spacing": 12},
    {"radius_factor": 1.45, "alpha": 255, "spacing": 10},
]

# Footprint settings
FOOTPRINT_RADIUS = 5
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

# Car settings
CAR_WIDTH = 30
CAR_HEIGHT = 50
CAR_SPEED = 4
CAR_HEALTH = 20
CAR_WALL_DAMAGE = 1
CAR_ZOMBIE_DAMAGE = 1
CAR_HINT_DELAY_MS_DEFAULT = 180000

# Wall settings
INTERNAL_WALL_THICKNESS = 24
INTERNAL_WALL_GRID_SNAP = CELL_SIZE
INTERNAL_WALL_SEGMENT_LENGTH = 50
INTERNAL_WALL_HEALTH = 40
INTERNAL_WALL_COLOR = (90, 100, 111)  # #5a646f
OUTER_WALL_MARGIN = 100
OUTER_WALL_THICKNESS = 50
OUTER_WALL_SEGMENT_LENGTH = 100
OUTER_WALL_HEALTH = 9999
OUTER_WALL_COLOR = (106, 117, 130)  # #6a7582


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
    ) -> None:
        super().__init__()
        safe_width = max(1, width)
        safe_height = max(1, height)
        self.image = pygame.Surface((safe_width, safe_height))
        self.base_color = color
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
        else:
            health_ratio = max(0, self.health / self.max_health)
            r = int(self.base_color[0])
            g = int(self.base_color[1] * health_ratio)
            b = int(self.base_color[2])
            self.image.fill((r, g, b))


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
        x_collided = False
        for wall in possible_walls:
            if temp_rect.colliderect(wall.rect):
                x_collided = True
                final_x = self.x
                break

        temp_rect.centerx = int(final_x)
        temp_rect.centery = int(next_y)
        y_collided = False
        for wall in possible_walls:
            if temp_rect.colliderect(wall.rect):
                y_collided = True
                final_y = self.y
                break

        return final_x, final_y

    def update(self: Self, player_center: Tuple[int, int], walls: List[Wall]) -> None:
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
        self.original_image.fill(color)
        pygame.draw.rect(self.original_image, BLACK, (CAR_WIDTH * 0.1, 5, CAR_WIDTH * 0.8, 10))
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


# --- Wall Generation Functions ---
def generate_outer_walls_simple(
    outer_rect: Tuple[int, int, int, int],
    exit_width: int,
    exits_per_side: int,
) -> pygame.sprite.Group:
    left, top, right, bottom = outer_rect
    segment_length = OUTER_WALL_SEGMENT_LENGTH
    t2 = OUTER_WALL_THICKNESS // 2
    walls = pygame.sprite.Group()

    for y in [top, bottom]:
        exit_positions = [random.randrange(left, right - exit_width) for i in range(exits_per_side)]
        for x in range(left, right, segment_length):
            if not any(ex <= x < ex + exit_width for ex in exit_positions):
                walls.add(
                    Wall(x - t2, y - t2, segment_length + t2, t2, health=OUTER_WALL_HEALTH, color=OUTER_WALL_COLOR)
                )

    for x in [left, right]:
        exit_positions = [random.randrange(top, bottom - exit_width) for i in range(exits_per_side)]
        for y in range(top, bottom, segment_length):
            if not any(ey <= y < ey + exit_width for ey in exit_positions):
                walls.add(
                    Wall(x - t2, y - t2, t2, segment_length + t2, health=OUTER_WALL_HEALTH, color=OUTER_WALL_COLOR)
                )

    return walls


def generate_internal_walls(
    num_lines: int,
    outer_rect: Tuple[int, int, int, int],
    len_range: Tuple[int, int],
    avoid_rects: list[rect.Rect],
) -> sprite.Group:
    left, top, right, bottom = outer_rect
    margin_x, margin_y = left, top
    min_len, max_len = len_range
    t2 = INTERNAL_WALL_THICKNESS // 2
    segment_length = INTERNAL_WALL_SEGMENT_LENGTH
    grid_snap = INTERNAL_WALL_GRID_SNAP

    newly_added_walls = pygame.sprite.Group()
    lines_created = 0
    max_attempts = num_lines * 25
    attempts = 0
    while lines_created < num_lines and attempts < max_attempts:
        attempts += 1
        total_length = random.randint(min_len, max_len)
        num_segments = max(1, round(total_length / segment_length))
        is_horizontal = random.choice([True, False])
        if is_horizontal:
            w, h = segment_length, 0
            min_start_x, max_start_x = left, right
            min_start_y, max_start_y = top + grid_snap, bottom - grid_snap
        else:
            w, h = 0, segment_length
            min_start_x, max_start_x = left + grid_snap, right - grid_snap
            min_start_y, max_start_y = top, bottom
        x = random.randint(0, right + margin_x)
        x = round(x / grid_snap) * grid_snap
        x = max(min_start_x, min(max_start_x, x))
        y = random.randint(0, bottom + margin_y)
        y = round(y / grid_snap) * grid_snap
        y = max(min_start_y, min(max_start_y, y))

        line_segments = pygame.sprite.Group()
        valid_line = True
        check_rects = [r.inflate(grid_snap, grid_snap) for r in avoid_rects]
        for i in range(num_segments):
            segment_rect = pygame.Rect(x - t2, y - t2, w + t2, h + t2)
            if (
                segment_rect.right > right
                or segment_rect.bottom > bottom
                or any(segment_rect.colliderect(cr) for cr in check_rects)
            ):
                valid_line = False
                break
            line_segments.add(Wall(x - t2, y - t2, w + t2, h + t2))
            x += w
            y += h
        if valid_line and len(line_segments) > 0:
            newly_added_walls.add(line_segments)
            lines_created += 1
    return newly_added_walls


def rect_for_cell(x_idx: int, y_idx: int) -> pygame.Rect:
    return pygame.Rect(x_idx * CELL_SIZE, y_idx * CELL_SIZE, CELL_SIZE, CELL_SIZE)


def generate_level_from_blueprint(game_data):
    """Build walls/spawn candidates/outside area from a blueprint grid."""
    wall_group = game_data["groups"]["wall_group"]
    all_sprites = game_data["groups"]["all_sprites"]

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
                    cell_rect.x, cell_rect.y, cell_rect.width, cell_rect.height, health=OUTER_WALL_HEALTH, color=OUTER_WALL_COLOR
                )
                wall_group.add(wall)
                all_sprites.add(wall, layer=0)
                continue
            if ch == "E":
                walkable_cells.append(cell_rect)
            elif ch == "1":
                wall = Wall(
                    cell_rect.x, cell_rect.y, cell_rect.width, cell_rect.height, health=INTERNAL_WALL_HEALTH, color=INTERNAL_WALL_COLOR
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

    game_data["areas"]["outer_rect"] = (0, 0, LEVEL_WIDTH, LEVEL_HEIGHT)
    game_data["areas"]["inner_rect"] = (0, 0, LEVEL_WIDTH, LEVEL_HEIGHT)
    game_data["areas"]["outside_rects"] = outside_rects
    game_data["areas"]["walkable_cells"] = walkable_cells
    game_data["areas"]["level_rect"] = pygame.Rect(0, 0, LEVEL_WIDTH, LEVEL_HEIGHT)

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


def draw_level_overview(surface: surface.Surface, wall_group: sprite.Group, player: Player, car: Car, footprints) -> None:
    surface.fill(BLACK)
    for wall in wall_group:
        pygame.draw.rect(surface, INTERNAL_WALL_COLOR, wall.rect)
    now = pygame.time.get_ticks()
    for fp in footprints:
        age = now - fp["time"]
        fade = 1 - (age / FOOTPRINT_LIFETIME_MS)
        fade = max(FOOTPRINT_MIN_FADE, fade)
        color = tuple(int(c * fade) for c in FOOTPRINT_COLOR)
        pygame.draw.circle(surface, color, (int(fp["pos"][0]), int(fp["pos"][1])), FOOTPRINT_RADIUS)
    if player:
        pygame.draw.circle(surface, BLUE, player.rect.center, PLAYER_RADIUS * 2)
    if car and car.alive():
        pygame.draw.rect(surface, YELLOW, car.rect)  # Draw car only if it exists


def place_new_car(wall_group, player, walkable_cells: List[pygame.Rect]):
    if not walkable_cells:
        return None

    max_attempts = 150
    for attempt in range(max_attempts):
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


def get_hatch_pattern(fog_data, spacing: int, thickness: int, pixel_scale: int = 1) -> surface.Surface:
    """Return cached ordered-dither tile surface (Bayer-style, optionally chunky)."""
    cache = fog_data.setdefault("hatch_patterns", {})
    pixel_scale = max(1, pixel_scale)
    key = (spacing, thickness, pixel_scale)
    if key in cache:
        return cache[key]

    spacing = max(4, spacing)
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
    state = game_data["state"]
    player: Player = game_data["player"]
    config = game_data.get("config", DEFAULT_CONFIG)

    footprints_enabled = config.get("footprints", {}).get("enabled", True)
    if not footprints_enabled:
        state["footprints"] = []
        state["last_footprint_pos"] = None
        return

    now = pygame.time.get_ticks()

    footprints = state.get("footprints", [])
    if not player.in_car:
        last_pos = state.get("last_footprint_pos")
        dist = math.hypot(player.x - last_pos[0], player.y - last_pos[1]) if last_pos else None
        if last_pos is None or (dist is not None and dist >= FOOTPRINT_STEP_DISTANCE):
            footprints.append({"pos": (player.x, player.y), "time": now})
            state["last_footprint_pos"] = (player.x, player.y)

    if len(footprints) > FOOTPRINT_MAX:
        footprints = footprints[-FOOTPRINT_MAX:]

    state["footprints"] = footprints


def _blit_hatch_ring(screen, overlay: surface.Surface, pattern: surface.Surface, alpha: int, clear_center, radius: float):
    """Draw a single hatched fog ring onto the screen."""
    overlay.fill((0, 0, 0, 0))
    p_w, p_h = pattern.get_size()
    for y in range(0, SCREEN_HEIGHT, p_h):
        for x in range(0, SCREEN_WIDTH, p_w):
            overlay.blit(pattern, (x, y))
    overlay.set_alpha(alpha)
    pygame.draw.circle(overlay, (0, 0, 0, 0), clear_center, int(radius))
    screen.blit(overlay, (0, 0))


def _draw_status_bar(screen, config):
    """Render a compact status bar with current config flags."""
    bar_rect = pygame.Rect(0, SCREEN_HEIGHT - STATUS_BAR_HEIGHT, SCREEN_WIDTH, STATUS_BAR_HEIGHT)
    overlay = pygame.Surface((bar_rect.width, bar_rect.height), pygame.SRCALPHA)
    overlay.fill((0, 0, 0, 140))
    screen.blit(overlay, bar_rect.topleft)

    footprints_on = config.get("footprints", {}).get("enabled", True)
    fast_on = config.get("fast_zombies", {}).get("enabled", True)
    hint_on = config.get("car_hint", {}).get("enabled", True)

    parts = [
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


def _draw_car_hint(screen, camera, player: Player, car: "Car") -> None:
    """Draw a soft directional hint from player to car."""
    if not car or not car.alive():
        return
    player_screen = camera.apply(player).center
    car_screen = camera.apply(car).center
    dx = car_screen[0] - player_screen[0]
    dy = car_screen[1] - player_screen[1]
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
    color = YELLOW
    pygame.draw.polygon(screen, color, [tip, left, right])


def draw(screen, outer_rect, camera, all_sprites, fov_target, fog_surfaces, footprints, config, car, player, show_car_hint: bool, do_flip: bool = True):
    # Drawing
    screen.fill(FLOOR_COLOR_PRIMARY)

    # floor tiles
    xs, ys, xe, ye = outer_rect
    xs //= INTERNAL_WALL_GRID_SNAP
    ys //= INTERNAL_WALL_GRID_SNAP
    xe //= INTERNAL_WALL_GRID_SNAP
    ye //= INTERNAL_WALL_GRID_SNAP
    for y in range(ys, ye):
        for x in range(xs, xe):
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

    if show_car_hint and player and car:
        _draw_car_hint(screen, camera, player, car)

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
            radius = int(FOV_RADIUS * ring["radius_factor"] * FOG_RADIUS_SCALE)
            alpha = ring["alpha"]
            spacing = ring.get("spacing", FOG_HATCH_DEFAULT_SPACING)
            pattern = get_hatch_pattern(fog_surfaces, spacing, FOG_HATCH_THICKNESS, FOG_HATCH_PIXEL_SCALE)
            _blit_hatch_ring(screen, fog_soft, pattern, alpha, fov_center_on_screen, radius)

    _draw_status_bar(screen, config)
    if do_flip:
        pygame.display.flip()


# --- Game State Function (Contains the main game loop) ---
def initialize_game_state(config):
    """Initialize and return the base game state objects."""
    game_state = {
        "game_over": False,
        "game_won": False,
        "overview_surface": None,
        "scaled_overview": None,
        "overview_created": False,
        "last_zombie_spawn_time": 0,
        "footprints": [],
        "last_footprint_pos": None,
        "elapsed_play_ms": 0,
    }

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

    return {
        "state": game_state,
        "groups": {"all_sprites": all_sprites, "wall_group": wall_group, "zombie_group": zombie_group},
        "camera": camera,
        "areas": {"outer_rect": outer_rect, "inner_rect": inner_rect},
        "fog": {"hard": fog_surface_hard, "soft": fog_surface_soft, "hatch_patterns": {}},
        "config": config,
    }


def setup_player_and_car(game_data, layout_data):
    """Create and position the player and car using blueprint candidates."""
    all_sprites = game_data["groups"]["all_sprites"]
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
    wall_group = game_data["groups"]["wall_group"]
    zombie_group = game_data["groups"]["zombie_group"]
    all_sprites = game_data["groups"]["all_sprites"]

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

    game_data["state"]["last_zombie_spawn_time"] = pygame.time.get_ticks() - ZOMBIE_SPAWN_DELAY_MS


def handle_game_over_state(screen, game_data):
    """Handle rendering and input when game is over or won."""
    state = game_data["state"]
    wall_group = game_data["groups"]["wall_group"]
    config = game_data.get("config", DEFAULT_CONFIG)
    footprints_enabled = config.get("footprints", {}).get("enabled", True)

    # Create overview map if needed
    if not state["overview_created"]:
        state["overview_surface"] = pygame.Surface((LEVEL_WIDTH, LEVEL_HEIGHT))
        footprints_to_draw = state.get("footprints", []) if footprints_enabled else []
        draw_level_overview(state["overview_surface"], wall_group, game_data["player"], game_data["car"], footprints_to_draw)

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

        state["scaled_overview"] = pygame.transform.smoothscale(state["overview_surface"], (scaled_w, scaled_h))
        state["overview_created"] = True

    # Display overview map and messages
    screen.fill(BLACK)
    if state["scaled_overview"]:
        screen.blit(
            state["scaled_overview"], state["scaled_overview"].get_rect(center=(SCREEN_WIDTH // 2, SCREEN_HEIGHT // 2))
        )

    if state["game_won"]:
        show_message(screen, "YOU ESCAPED!", 40, GREEN, (SCREEN_WIDTH // 2, SCREEN_HEIGHT // 2 - 40))

    show_message(screen, "Press SPACE to return to Title or ESC to Quit", 30, WHITE, (SCREEN_WIDTH // 2, SCREEN_HEIGHT // 2 + 30))

    pygame.display.flip()

    # Check for restart input
    for event in pygame.event.get():
        if event.type == pygame.QUIT:
            return False
        if event.type == pygame.KEYDOWN:
            if event.key == pygame.K_ESCAPE:
                return False
            if event.key == pygame.K_SPACE:
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
    player = game_data["player"]
    car = game_data["car"]
    wall_group = game_data["groups"]["wall_group"]
    all_sprites = game_data["groups"]["all_sprites"]
    zombie_group = game_data["groups"]["zombie_group"]
    camera = game_data["camera"]
    config = game_data.get("config", DEFAULT_CONFIG)

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
    if (
        len(zombie_group) < MAX_ZOMBIES
        and current_time - game_data["state"]["last_zombie_spawn_time"] > ZOMBIE_SPAWN_DELAY_MS
    ):
        new_zombie = create_zombie(config, hint_pos=(player.x, player.y))
        zombie_group.add(new_zombie)
        all_sprites.add(new_zombie, layer=1)
        game_data["state"]["last_zombie_spawn_time"] = current_time

    # Update zombies
    target_center = car.rect.center if player.in_car and car.alive() else player.rect.center
    for zombie in zombie_group:
        zombie.update(target_center, wall_group)


def check_interactions(game_data):
    """Check and handle interactions between entities."""
    player = game_data["player"]
    car = game_data["car"]
    zombie_group = game_data["groups"]["zombie_group"]
    wall_group = game_data["groups"]["wall_group"]
    all_sprites = game_data["groups"]["all_sprites"]
    state = game_data["state"]
    walkable_cells = game_data["areas"].get("walkable_cells", [])
    outside_rects = game_data["areas"].get("outside_rects", [])

    # Player entering car
    shrunk_car = get_shrunk_sprite(car, 0.8)
    if not player.in_car and car.alive() and car.health > 0:
        g = pygame.sprite.Group()
        g.add(player)
        if pygame.sprite.spritecollide(shrunk_car, g, False):
            player.in_car = True
            all_sprites.remove(player)
            print("Player entered car!")

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
            game_data["car"] = new_car  # Update car reference
            all_sprites.add(new_car, layer=1)
        else:
            print("Error: Failed to respawn car anywhere!")

    # Player getting caught by zombies
    if not player.in_car and player in all_sprites:
        shrunk_player = get_shrunk_sprite(player, 0.8)
        if pygame.sprite.spritecollide(shrunk_player, zombie_group, False, pygame.sprite.collide_circle):
            state["game_over"] = True

    # Player escaping the level
    if player.in_car and car.alive():
        if any(outside.collidepoint(car.rect.center) for outside in outside_rects):
            state["game_won"] = True

    # Return fog of view target
    if not state["game_over"] and not state["game_won"]:
        return car if player.in_car and car.alive() else player
    return None


def run_game(screen: surface.Surface, clock: time.Clock, config, show_pause_overlay: bool = True) -> bool:
    """Main game loop function, now using smaller helper functions."""
    # Initialize game components
    game_data = initialize_game_state(config)
    paused_manual = False
    paused_focus = False
    last_fov_target = None

    # Generate level from blueprint and set up player/car
    layout_data = generate_level_from_blueprint(game_data)
    player, car = setup_player_and_car(game_data, layout_data)
    game_data["player"] = player
    game_data["car"] = car

    # Spawn initial zombies
    spawn_initial_zombies(game_data, player, layout_data)
    update_footprints(game_data)
    last_fov_target = player

    # Game loop
    running = True
    while running:
        dt = clock.tick(FPS) / 1000.0

        # Handle game over state
        if game_data["state"]["game_over"] or game_data["state"]["game_won"]:
            result = handle_game_over_state(screen, game_data)
            if result is not None:  # If restart or quit was selected
                return result
            continue

        # Check for quit events
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                return False
            if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                return False
            if event.type == pygame.WINDOWFOCUSLOST:
                paused_focus = True
            if event.type == pygame.KEYDOWN and event.key == pygame.K_p:
                paused_manual = not paused_manual
            if event.type == pygame.MOUSEBUTTONDOWN:
                paused_focus = False
                paused_manual = False

        paused = paused_manual or paused_focus
        if paused:
            draw(
                screen,
                game_data["areas"]["outer_rect"],
                game_data["camera"],
                game_data["groups"]["all_sprites"],
                last_fov_target,
                game_data["fog"],
                game_data["state"]["footprints"],
                config,
                game_data["car"],
                player,
                False,
                do_flip=not show_pause_overlay,
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
                pygame.display.flip()
            continue

        # Process input
        keys = pygame.key.get_pressed()
        player_dx, player_dy, car_dx, car_dy = process_player_input(keys, player, car)

        # Update game entities
        update_entities(game_data, player_dx, player_dy, car_dx, car_dy)
        update_footprints(game_data)
        game_data["state"]["elapsed_play_ms"] += int(dt * 1000)

        # Handle interactions
        fov_target = check_interactions(game_data)
        last_fov_target = fov_target or last_fov_target

        # Draw everything
        car_hint_conf = config.get("car_hint", {})
        hint_delay = car_hint_conf.get("delay_ms", CAR_HINT_DELAY_MS_DEFAULT)
        show_car_hint = (
            car_hint_conf.get("enabled", True)
            and game_data["state"]["elapsed_play_ms"] >= hint_delay
            and not player.in_car
            and game_data["car"].alive()
            and math.hypot(player.rect.centerx - game_data["car"].rect.centerx, player.rect.centery - game_data["car"].rect.centery)
            > FOV_RADIUS * FOG_RADIUS_SCALE
        )
        draw(
            screen,
            game_data["areas"]["outer_rect"],
            game_data["camera"],
            game_data["groups"]["all_sprites"],
            fov_target,
            game_data["fog"],
            game_data["state"]["footprints"],
            config,
            game_data["car"],
            player,
            show_car_hint,
        )

    return False


# --- Splash Screen Function ---
def title_screen(screen: surface.Surface, clock: time.Clock, config) -> str:
    """Simple title menu. Returns 'start', 'settings', or 'quit'."""
    options = ["Start Game", "Settings", "Quit"]
    selected = 0

    while True:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                return "quit"
            if event.type == pygame.KEYDOWN:
                if event.key in (pygame.K_UP, pygame.K_w):
                    selected = (selected - 1) % len(options)
                elif event.key in (pygame.K_DOWN, pygame.K_s):
                    selected = (selected + 1) % len(options)
                elif event.key in (pygame.K_RETURN, pygame.K_SPACE):
                    return options[selected].lower().split()[0]

        screen.fill(BLACK)
        show_message(screen, "Zombie Escape", 72, LIGHT_GRAY, (SCREEN_WIDTH // 2, SCREEN_HEIGHT // 2 - 120))

        try:
            font = pygame.font.Font(None, 36)
            for idx, label in enumerate(options):
                color = YELLOW if idx == selected else WHITE
                text_surface = font.render(label, True, color)
                text_rect = text_surface.get_rect(center=(SCREEN_WIDTH // 2, SCREEN_HEIGHT // 2 + idx * 50))
                screen.blit(text_surface, text_rect)

            # Show a quick config summary
            small_font = pygame.font.Font(None, 24)
            fp_on = config.get("footprints", {}).get("enabled", True)
            fast_on = config.get("fast_zombies", {}).get("enabled", True)
            hint_on = config.get("car_hint", {}).get("enabled", True)
            summary_parts = [
                f"Footprints: {'ON' if fp_on else 'OFF'}",
                f"Fast Z: {'ON' if fast_on else 'OFF'}",
                f"Car Hint: {'ON' if hint_on else 'OFF'}",
            ]
            summary = " | ".join(summary_parts)
            summary_surface = small_font.render(summary, True, LIGHT_GRAY)
            summary_rect = summary_surface.get_rect(center=(SCREEN_WIDTH // 2, SCREEN_HEIGHT // 2 + 50 * len(options) + 30))
            screen.blit(summary_surface, summary_rect)
        except pygame.error as e:
            print(f"Error rendering title screen: {e}")

        pygame.display.flip()
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

        pygame.display.flip()
        clock.tick(FPS)


# --- Main Entry Point ---
def main():
    pygame.init()
    try:
        pygame.font.init()
    except pygame.error as e:
        print(f"Pygame font failed to initialize: {e}")
        # Font errors are often non-fatal, continue without fonts or handle gracefully

    screen = pygame.display.set_mode((SCREEN_WIDTH, SCREEN_HEIGHT))
    pygame.display.set_caption(f"Zombie Escape v{__version__}")
    clock = pygame.time.Clock()

    hide_pause_overlay = "--hide-pause-overlay" in sys.argv

    config, config_path = load_config()
    if not config_path.exists():
        save_config(config, config_path)

    restart_game = True
    while restart_game:
        selection = title_screen(screen, clock, config)

        if selection == "quit":
            restart_game = False
            break

        if selection == "settings":
            config = settings_screen(screen, clock, config, config_path)
            continue

        if selection == "start":
            try:
                restart_game = run_game(screen, clock, config, show_pause_overlay=not hide_pause_overlay)
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
