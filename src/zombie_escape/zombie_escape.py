import pygame
import random
import math
import sys
import traceback  # For error reporting
from enum import Enum  # For Zombie Modes

# --- Constants ---
SCREEN_WIDTH = 800
SCREEN_HEIGHT = 600
FPS = 60
LEVEL_SCALE = 4
LEVEL_WIDTH = SCREEN_WIDTH * LEVEL_SCALE
LEVEL_HEIGHT = SCREEN_HEIGHT * LEVEL_SCALE

# Colors
WHITE = (255, 255, 255)
BLACK = (0, 0, 0)
DARK_GRAY = (20, 20, 20)
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

# Player settings
PLAYER_RADIUS = 10
PLAYER_SPEED = 3.5
FOV_RADIUS = 180
PLAYER_PUSHBACK = 5
FOV_RADIUS_SOFT_FACTOR = 1.5

# Zombie settings
ZOMBIE_RADIUS = 8
ZOMBIE_SPEED = 1.4
ZOMBIE_SPAWN_DELAY_MS = 100
MAX_ZOMBIES = 200
INITIAL_ZOMBIES_INSIDE = 20
ZOMBIE_MODE_CHANGE_INTERVAL_MS = 5000
ZOMBIE_SIGHT_RANGE = FOV_RADIUS * 2.0

# Car settings
CAR_WIDTH = 30
CAR_HEIGHT = 50
CAR_SPEED = 4
CAR_HEALTH = 30
CAR_WALL_DAMAGE = 1
CAR_ZOMBIE_DAMAGE = 1

# Wall settings
NUM_INTERNAL_WALL_LINES = 220
INTERNAL_WALL_THICKNESS = 24
INTERNAL_WALL_MIN_LEN = 100
INTERNAL_WALL_MAX_LEN = 400
INTERNAL_WALL_GRID_SNAP = 100
INTERNAL_WALL_SEGMENT_LENGTH = 50
INTERNAL_WALL_HEALTH = 20
INTERNAL_WALL_COLOR = GRAY
OUTER_WALL_MARGIN = 100
OUTER_WALL_THICKNESS = 50
OUTER_WALL_SEGMENT_LENGTH = 100
OUTER_WALL_HEALTH = 9999
OUTER_WALL_COLOR = LIGHT_GRAY
EXIT_WIDTH = 100
EXITS_PER_SIDE = 4


# --- Camera Class ---
class Camera:
    def __init__(self, width, height):
        self.camera = pygame.Rect(0, 0, width, height)
        self.width = width
        self.height = height

    def apply(self, entity):
        return entity.rect.move(self.camera.topleft)

    def apply_rect(self, rect):
        return rect.move(self.camera.topleft)

    def update(self, target):
        x = -target.rect.centerx + int(SCREEN_WIDTH / 2)
        y = -target.rect.centery + int(SCREEN_HEIGHT / 2)
        x = min(0, x)
        y = min(0, y)
        x = max(-(self.width - SCREEN_WIDTH), x)
        y = max(-(self.height - SCREEN_HEIGHT), y)
        self.camera = pygame.Rect(x, y, self.width, self.height)


# --- Enums ---
class ZombieMode(Enum):
    CHASE = 1
    HORIZONTAL_ONLY = 2
    VERTICAL_ONLY = 3
    FLANK_X = 4
    FLANK_Y = 5


# --- Game Classes ---
class Player(pygame.sprite.Sprite):
    def __init__(self, x, y):
        super().__init__()
        self.radius = PLAYER_RADIUS
        self.image = pygame.Surface((self.radius * 2 + 2, self.radius * 2 + 2), pygame.SRCALPHA)
        pygame.draw.circle(self.image, BLUE, (self.radius + 1, self.radius + 1), self.radius)
        self.rect = self.image.get_rect(center=(x, y))
        self.speed = PLAYER_SPEED
        self.in_car = False
        self.x = float(self.rect.centerx)
        self.y = float(self.rect.centery)

    def move(self, dx, dy, walls):
        if self.in_car:
            return

        if dx != 0:
            self.x += dx
            self.x = min(LEVEL_WIDTH, max(0, self.x))
            self.rect.centerx = int(self.x)
            hit_list_x = pygame.sprite.spritecollide(self, walls, False)
            push_back = False
            for wall in hit_list_x:
                wall.take_damage()
                if wall.health <= 0:
                    wall.kill()
                push_back = True
            if push_back:
                self.x -= dx * 1.5
                self.rect.centerx = int(self.x)

        if dy != 0:
            self.y += dy
            self.y = min(LEVEL_HEIGHT, max(0, self.y))
            self.rect.centery = int(self.y)
            hit_list_y = pygame.sprite.spritecollide(self, walls, False)
            push_back = False
            for wall in hit_list_y:
                if wall.alive():
                    wall.take_damage()
                    if wall.health <= 0:
                        wall.kill()
                    push_back = True
            if push_back:
                self.y -= dy * 1.5
                self.rect.centery = int(self.y)

        self.rect.center = (int(self.x), int(self.y))


class Zombie(pygame.sprite.Sprite):
    def __init__(self, start_pos=None):
        super().__init__()
        self.radius = ZOMBIE_RADIUS
        self.image = pygame.Surface((self.radius * 2, self.radius * 2), pygame.SRCALPHA)
        pygame.draw.circle(self.image, RED, (self.radius, self.radius), self.radius)
        if start_pos:
            x, y = start_pos
        else:
            side = random.choice(["top", "bottom", "left", "right"])
            margin = 100
            if side == "top":
                x, y = random.randint(0, LEVEL_WIDTH), -margin
            elif side == "bottom":
                x, y = random.randint(0, LEVEL_WIDTH), LEVEL_HEIGHT + margin
            elif side == "left":
                x, y = -margin, random.randint(0, LEVEL_HEIGHT)
            else:
                x, y = LEVEL_WIDTH + margin, random.randint(0, LEVEL_HEIGHT)
        self.rect = self.image.get_rect(center=(x, y))
        self.speed = ZOMBIE_SPEED + random.uniform(-0.4, 0.4)
        self.x = float(self.rect.centerx)
        self.y = float(self.rect.centery)
        self.mode = random.choice(list(ZombieMode))
        self.last_mode_change_time = pygame.time.get_ticks()
        self.mode_change_interval = ZOMBIE_MODE_CHANGE_INTERVAL_MS + random.randint(-1000, 1000)
        self.was_in_sight = False

    def change_mode(self, force_mode=None):
        if force_mode:
            self.mode = force_mode
        else:
            possible_modes = list(ZombieMode)
            self.mode = random.choice(possible_modes)
        self.last_mode_change_time = pygame.time.get_ticks()
        self.mode_change_interval = ZOMBIE_MODE_CHANGE_INTERVAL_MS + random.randint(-1000, 1000)

    def _calculate_movement(self, player_center):
        move_x, move_y = 0, 0
        dx_target = player_center[0] - self.x
        dy_target = player_center[1] - self.y
        dist = math.hypot(dx_target, dy_target)
        if self.mode == ZombieMode.CHASE:
            if dist > 0:
                move_x, move_y = (dx_target / dist) * self.speed, (dy_target / dist) * self.speed
        elif self.mode == ZombieMode.HORIZONTAL_ONLY:
            if dist > 0:
                move_x = (dx_target / abs(dx_target) if dx_target != 0 else 0) * self.speed
                move_y = 0
        elif self.mode == ZombieMode.VERTICAL_ONLY:
            move_x = 0
            if dist > 0:
                move_y = (dy_target / abs(dy_target) if dy_target != 0 else 0) * self.speed
        elif self.mode == ZombieMode.FLANK_X:
            if dist > 0:
                move_x = (dx_target / abs(dx_target) if dx_target != 0 else 0) * self.speed * 0.8
            move_y = random.uniform(-self.speed * 0.6, self.speed * 0.6)
        elif self.mode == ZombieMode.FLANK_Y:
            move_x = random.uniform(-self.speed * 0.6, self.speed * 0.6)
            if dist > 0:
                move_y = (dy_target / abs(dy_target) if dy_target != 0 else 0) * self.speed * 0.8
        return move_x, move_y

    def _handle_wall_collision(self, next_x, next_y, walls):
        final_x, final_y = next_x, next_y
        temp_rect = self.rect.copy()
        temp_rect.centerx = int(next_x)
        temp_rect.centery = int(self.y)
        x_collided = False
        possible_walls = [w for w in walls if abs(w.rect.centerx - self.x) < 100 and abs(w.rect.centery - self.y) < 100]
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

    def update(self, player_center, walls):
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
        self.x = final_x
        self.y = final_y
        self.rect.center = (int(self.x), int(self.y))


class Car(pygame.sprite.Sprite):
    def __init__(self, x, y):
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

    def update_color(self):
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

        temp_rect_x = self.rect.copy()
        temp_rect_x.centerx = int(new_x)
        collided_x = False
        hit_wall_x = None
        possible_walls_x = [
            w for w in walls if abs(w.rect.centery - self.y) < 100 and abs(w.rect.centerx - new_x) < 100
        ]
        for wall in possible_walls_x:
            if temp_rect_x.colliderect(wall.rect):
                collided_x = True
                hit_wall_x = wall
                break
        if collided_x:
            new_x -= dx * 1.5
            if hit_wall_x.health < OUTER_WALL_HEALTH:
                self.take_damage(CAR_WALL_DAMAGE)
        self.x = new_x

        temp_rect_y = self.rect.copy()
        temp_rect_y.centerx = int(self.x)
        temp_rect_y.centery = int(new_y)
        collided_y = False
        hit_wall_y = None
        possible_walls_y = [
            w for w in walls if abs(w.rect.centerx - self.x) < 100 and abs(w.rect.centery - new_y) < 100
        ]
        for wall in possible_walls_y:
            if temp_rect_y.colliderect(wall.rect):
                collided_y = True
                hit_wall_y = wall
                break
        if collided_y:
            new_y -= dy * 1.5
            if hit_wall_y.health < OUTER_WALL_HEALTH:
                self.take_damage(CAR_WALL_DAMAGE)
        self.y = new_y
        self.rect.center = (int(self.x), int(self.y))


class Wall(pygame.sprite.Sprite):
    def __init__(self, x, y, width, height, health=INTERNAL_WALL_HEALTH, color=INTERNAL_WALL_COLOR):
        super().__init__()
        safe_width = max(1, width)
        safe_height = max(1, height)
        self.image = pygame.Surface((safe_width, safe_height))
        self.base_color = color
        self.health = health
        self.max_health = max(1, health)
        self.update_color()
        self.rect = self.image.get_rect(topleft=(x, y))

    def take_damage(self, amount=1):
        if self.health > 0:
            self.health -= amount
            self.update_color()

    def update_color(self):
        if self.health <= 0:
            self.image.fill((40, 40, 40))
        else:
            health_ratio = max(0, self.health / self.max_health)
            r = int(self.base_color[0])
            g = int(self.base_color[1] * health_ratio)
            b = int(self.base_color[2])
            self.image.fill((r, g, b))


# --- Wall Generation Functions ---
def generate_outer_walls_simple(
    level_w,
    level_h,
    margin,
    thickness,
    segment_length,
    exit_width,
    exists_per_side,
):
    walls = pygame.sprite.Group()
    left = margin
    top = margin
    right = level_w - margin
    bottom = level_h - margin
    t2 = thickness // 2

    for y in [top, bottom]:
        exit_positions = [random.randrange(left, right - exit_width) for i in range(exists_per_side)]
        for x in range(left, right, segment_length):
            if not any(ex <= x < ex + exit_width for ex in exit_positions):
                walls.add(
                    Wall(x - t2, y - t2, segment_length + t2, t2, health=OUTER_WALL_HEALTH, color=OUTER_WALL_COLOR)
                )

    for x in [left, right]:
        exit_positions = [random.randrange(top, bottom - exit_width) for i in range(exists_per_side)]
        for y in range(top, bottom, segment_length):
            if not any(ey <= y < ey + exit_width for ey in exit_positions):
                walls.add(
                    Wall(x - t2, y - t2, t2, segment_length + t2, health=OUTER_WALL_HEALTH, color=OUTER_WALL_COLOR)
                )

    return walls


def generate_internal_walls(
    num_lines,
    level_w,
    level_h,
    margin,
    thickness,
    segment_length,
    min_len,
    max_len,
    grid_snap,
    avoid_rects,
):
    newly_added_walls = pygame.sprite.Group()
    lines_created = 0
    attempts = 0
    max_attempts = num_lines * 25
    inner_left, inner_top = margin, margin
    inner_right, inner_bottom = level_w - margin, level_h - margin
    t2 = thickness // 2

    while lines_created < num_lines and attempts < max_attempts:
        attempts += 1
        total_length = random.randint(min_len, max_len)
        num_segments = max(1, round(total_length / segment_length))
        is_horizontal = random.choice([True, False])
        if is_horizontal:
            w, h = segment_length, 0
            min_start_x, max_start_x = inner_left, inner_right
            min_start_y, max_start_y = inner_top + grid_snap, inner_bottom - grid_snap
        else:
            w, h = 0, segment_length
            min_start_x, max_start_x = inner_left + grid_snap, inner_right - grid_snap
            min_start_y, max_start_y = inner_top, inner_bottom
        x = random.randint(0, level_w)
        x = round(x / grid_snap) * grid_snap
        x = max(min_start_x, min(max_start_x, x))
        y = random.randint(0, level_h)
        y = round(y / grid_snap) * grid_snap
        y = max(min_start_y, min(max_start_y, y))
        line_segments = pygame.sprite.Group()
        valid_line = True
        check_rects = [r.inflate(grid_snap, grid_snap) for r in avoid_rects]
        for i in range(num_segments):
            segment_rect = pygame.Rect(x - t2, y - t2, w + t2, h + t2)
            if (
                segment_rect.right > inner_right
                or segment_rect.bottom > inner_bottom
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


# --- Helper Functions ---
def show_message(screen, text, size, color, position):
    try:
        font = pygame.font.Font(None, size)
        text_surface = font.render(text, True, color)
        text_rect = text_surface.get_rect(center=position)
        bg_surface = pygame.Surface((text_rect.width + 30, text_rect.height + 15), pygame.SRCALPHA)
        bg_surface.fill((0, 0, 0, 190))
        screen.blit(bg_surface, bg_surface.get_rect(center=position))
        screen.blit(text_surface, text_rect)
    except pygame.error as e:
        print(f"Error rendering font: {e}")


def draw_level_overview(surface, wall_group, player, car):
    surface.fill(BLACK)
    for wall in wall_group:
        pygame.draw.rect(surface, INTERNAL_WALL_COLOR, wall.rect)
    if player:
        pygame.draw.circle(surface, BLUE, player.rect.center, PLAYER_RADIUS * 2)
    if car and car.alive():
        pygame.draw.rect(surface, YELLOW, car.rect)  # Draw car only if it exists


def place_new_car(wall_group, player):
    max_attempts = 150
    for attempt in range(max_attempts):
        inner_left = OUTER_WALL_MARGIN + INTERNAL_WALL_GRID_SNAP
        inner_top = OUTER_WALL_MARGIN + INTERNAL_WALL_GRID_SNAP
        inner_right = LEVEL_WIDTH - OUTER_WALL_MARGIN - INTERNAL_WALL_GRID_SNAP
        inner_bottom = LEVEL_HEIGHT - OUTER_WALL_MARGIN - INTERNAL_WALL_GRID_SNAP
        c_x = random.randint(inner_left, inner_right)
        c_y = random.randint(inner_top, inner_bottom)
        temp_car = Car(c_x, c_y)
        temp_rect = temp_car.rect.inflate(30, 30)
        collides_wall = False
        nearby_walls = [w for w in wall_group if abs(w.rect.centerx - c_x) < 150 and abs(w.rect.centery - c_y) < 150]
        if pygame.sprite.spritecollideany(temp_car, nearby_walls, collided=lambda s1, s2: s1.rect.colliderect(s2.rect)):
            collides_wall = True
        collides_player = temp_rect.colliderect(player.rect.inflate(50, 50))
        if not collides_wall and not collides_player:
            return temp_car
    # print("Warning: Failed to find suitable location for new car.")
    return None


# --- Main Game Function ---
def game():
    pygame.init()
    try:
        pygame.font.init()
    except pygame.error as e:
        print(f"Pygame font failed: {e}")
        pygame.quit()
        sys.exit()

    screen = pygame.display.set_mode((SCREEN_WIDTH, SCREEN_HEIGHT))
    pygame.display.set_caption("Zombie Escape v0.5.4")
    clock = pygame.time.Clock()

    running = True
    game_over = False
    game_won = False
    overview_surface = None
    scaled_overview = None
    overview_created = False
    all_sprites = pygame.sprite.LayeredUpdates()
    wall_group = pygame.sprite.Group()
    zombie_group = pygame.sprite.Group()
    fog_surface_hard = pygame.Surface((SCREEN_WIDTH, SCREEN_HEIGHT), pygame.SRCALPHA)
    fog_surface_soft = pygame.Surface((SCREEN_WIDTH, SCREEN_HEIGHT), pygame.SRCALPHA)  # Soft fog surface
    camera = Camera(LEVEL_WIDTH, LEVEL_HEIGHT)

    # Place Player/Car
    player_start_x = random.randint(int(LEVEL_WIDTH * 0.2), int(LEVEL_WIDTH * 0.8))
    player_start_y = random.randint(int(LEVEL_HEIGHT * 0.2), int(LEVEL_HEIGHT * 0.8))
    player = Player(player_start_x, player_start_y)
    car_start_x = random.randint(int(LEVEL_WIDTH * 0.2), int(LEVEL_WIDTH * 0.8))
    car_start_y = random.randint(int(LEVEL_HEIGHT * 0.2), int(LEVEL_HEIGHT * 0.8))
    while math.hypot(car_start_x - player_start_x, car_start_y - player_start_y) < 400:
        car_start_x = random.randint(int(LEVEL_WIDTH * 0.2), int(LEVEL_WIDTH * 0.8))
        car_start_y = random.randint(int(LEVEL_HEIGHT * 0.2), int(LEVEL_HEIGHT * 0.8))
    car = Car(car_start_x, car_start_y)
    player_initial_rect = player.rect.copy()
    car_initial_rect = car.rect.copy()
    all_sprites.add(player, layer=2)
    all_sprites.add(car, layer=1)

    # Generate Walls
    outer_walls = generate_outer_walls_simple(
        LEVEL_WIDTH,
        LEVEL_HEIGHT,
        OUTER_WALL_MARGIN,
        OUTER_WALL_THICKNESS,
        OUTER_WALL_SEGMENT_LENGTH,
        EXIT_WIDTH,
        EXITS_PER_SIDE,
    )
    wall_group.add(outer_walls)
    all_sprites.add(outer_walls, layer=0)
    internal_walls = generate_internal_walls(
        NUM_INTERNAL_WALL_LINES,
        LEVEL_WIDTH,
        LEVEL_HEIGHT,
        OUTER_WALL_MARGIN,
        INTERNAL_WALL_THICKNESS,
        INTERNAL_WALL_SEGMENT_LENGTH,
        INTERNAL_WALL_MIN_LEN,
        INTERNAL_WALL_MAX_LEN,
        INTERNAL_WALL_GRID_SNAP,
        [player_initial_rect, car_initial_rect],
    )
    wall_group.add(internal_walls)
    all_sprites.add(internal_walls, layer=0)
    # print(f"Wall generation complete. Total wall segments: {len(wall_group)}")

    # Initial Zombies Inside
    initial_zombies_placed = 0
    placement_attempts = 0
    max_placement_attempts = INITIAL_ZOMBIES_INSIDE * 20
    inner_left = OUTER_WALL_MARGIN + OUTER_WALL_THICKNESS
    inner_top = OUTER_WALL_MARGIN + OUTER_WALL_THICKNESS
    inner_right = LEVEL_WIDTH - OUTER_WALL_MARGIN - OUTER_WALL_THICKNESS
    inner_bottom = LEVEL_HEIGHT - OUTER_WALL_MARGIN - OUTER_WALL_THICKNESS
    while initial_zombies_placed < INITIAL_ZOMBIES_INSIDE and placement_attempts < max_placement_attempts:
        placement_attempts += 1
        z_x = random.randint(inner_left, inner_right)
        z_y = random.randint(inner_top, inner_bottom)
        temp_zombie = Zombie(start_pos=(z_x, z_y))
        temp_sprite = pygame.sprite.Sprite()
        temp_sprite.rect = temp_zombie.rect.inflate(5, 5)

        collides_with_wall = pygame.sprite.spritecollideany(temp_sprite, wall_group)
        collides_with_player = temp_sprite.rect.colliderect(player.rect.inflate(ZOMBIE_SIGHT_RANGE, ZOMBIE_SIGHT_RANGE))

        # Check collision with initial car position
        collides_with_car = temp_sprite.rect.colliderect(car_initial_rect.inflate(40, 40))
        if not collides_with_wall and not collides_with_player and not collides_with_car:
            new_zombie = temp_zombie
            zombie_group.add(new_zombie)
            all_sprites.add(new_zombie, layer=1)
            initial_zombies_placed += 1
    # if initial_zombies_placed < INITIAL_ZOMBIES_INSIDE: print(f"Warning: Could only place {initial_zombies_placed}/{INITIAL_ZOMBIES_INSIDE} initial zombies.")

    last_zombie_spawn_time = pygame.time.get_ticks() - ZOMBIE_SPAWN_DELAY_MS

    # --- Game Loop ---
    while running:
        dt = clock.tick(FPS) / 1000.0
        player_dx, player_dy, car_dx, car_dy = 0, 0, 0, 0

        # Event Handling
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    running = False
                if (game_over or game_won) and event.key == pygame.K_r:
                    return

        # Game Over/Game Won State
        if game_over or game_won:
            if not overview_created:
                overview_surface = pygame.Surface((LEVEL_WIDTH, LEVEL_HEIGHT))
                draw_level_overview(overview_surface, wall_group, player, car)
                level_aspect = LEVEL_WIDTH / LEVEL_HEIGHT
                screen_aspect = SCREEN_WIDTH / SCREEN_HEIGHT
                if level_aspect > screen_aspect:
                    scaled_w = SCREEN_WIDTH - 40
                    scaled_h = int(scaled_w / level_aspect)
                else:
                    scaled_h = SCREEN_HEIGHT - 40
                    scaled_w = int(scaled_h * level_aspect)
                scaled_overview = pygame.transform.smoothscale(overview_surface, (scaled_w, scaled_h))
                overview_created = True
            screen.fill(BLACK)
            if scaled_overview:
                screen.blit(scaled_overview, scaled_overview.get_rect(center=(SCREEN_WIDTH // 2, SCREEN_HEIGHT // 2)))

            if game_won:
                show_message(screen, "YOU ESCAPED!", 40, GREEN, (SCREEN_WIDTH // 2, SCREEN_HEIGHT // 2 - 40))

            show_message(
                screen, "Press 'R' to Restart or ESC to Quit", 30, WHITE, (SCREEN_WIDTH // 2, SCREEN_HEIGHT // 2 + 30)
            )
            pygame.display.flip()
            continue

        # Normal Game Running State
        keys = pygame.key.get_pressed()
        dx_input, dy_input = 0, 0
        if keys[pygame.K_w] or keys[pygame.K_UP]:
            dy_input -= 1
        if keys[pygame.K_s] or keys[pygame.K_DOWN]:
            dy_input += 1
        if keys[pygame.K_a] or keys[pygame.K_LEFT]:
            dx_input -= 1
        if keys[pygame.K_d] or keys[pygame.K_RIGHT]:
            dx_input += 1
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

        # Updates
        active_walls = wall_group.sprites()
        if player.in_car and car.alive():
            car.move(car_dx, car_dy, active_walls)
            player.rect.center = car.rect.center
            player.x, player.y = car.x, car.y
        elif not player.in_car:
            if player not in all_sprites:
                all_sprites.add(player, layer=2)
            player.move(player_dx, player_dy, active_walls)
        target_for_camera = car if player.in_car and car.alive() else player
        camera.update(target_for_camera)
        current_time = pygame.time.get_ticks()
        if len(zombie_group) < MAX_ZOMBIES and current_time - last_zombie_spawn_time > ZOMBIE_SPAWN_DELAY_MS:
            new_zombie = Zombie()
            spawn_rect = new_zombie.rect.inflate(40, 40)
            screen_boundary_check_rect = pygame.Rect(
                -camera.camera.x, -camera.camera.y, SCREEN_WIDTH, SCREEN_HEIGHT
            ).inflate(100, 100)
            player_spawn_check_rect = player.rect.copy().inflate(100, 100)
            car_spawn_check_rect = car.rect.copy().inflate(100, 100) if car.alive() else pygame.Rect(0, 0, 0, 0)
            if (
                not player_spawn_check_rect.colliderect(spawn_rect)
                and (not car.alive() or not car_spawn_check_rect.colliderect(spawn_rect))
                and not new_zombie.rect.colliderect(screen_boundary_check_rect)
            ):
                zombie_group.add(new_zombie)
                all_sprites.add(new_zombie, layer=1)
            last_zombie_spawn_time = current_time
        target_center = car.rect.center if player.in_car and car.alive() else player.rect.center
        screen_rect_level_coords = pygame.Rect(-camera.camera.x, -camera.camera.y, SCREEN_WIDTH, SCREEN_HEIGHT).inflate(
            400, 400
        )
        for zombie in zombie_group:
            if zombie.rect.colliderect(screen_rect_level_coords):
                zombie.update(target_center, active_walls)

        # Interactions & State Checks
        if not player.in_car and car.alive() and car.health > 0:
            car_center_v = pygame.math.Vector2(car.rect.center)
            player_center_v = pygame.math.Vector2(player.rect.center)
            entry_distance = max(car.rect.width, car.rect.height) * 0.7 + player.radius
            if player_center_v.distance_to(car_center_v) < entry_distance:
                player.in_car = True
                all_sprites.remove(player)
                print("Player entered car!")
        if player.in_car and car.alive() and car.health > 0:
            zombies_hit = pygame.sprite.spritecollide(car, zombie_group, True)
            if zombies_hit:
                car.take_damage(CAR_ZOMBIE_DAMAGE * len(zombies_hit))
        if car.alive() and car.health <= 0:  # Check if car is alive before checking health
            car_destroyed_pos = car.rect.center  # Store position before killing
            car.kill()
            if player.in_car:
                player.in_car = False
                player.x, player.y = car_destroyed_pos[0], car_destroyed_pos[1]
                player.rect.center = (int(player.x), int(player.y))
                if player not in all_sprites:
                    all_sprites.add(player, layer=2)
                print("Car destroyed! Player ejected.")

            # Respawn car
            new_car = place_new_car(wall_group, player)
            if new_car is None:
                new_car = Car(car_start_x, car_start_y)
                print("Failed to find a suitable location for the new car. Falling back to the original car's position.")
            car = new_car  # Update the main car variable
            all_sprites.add(car, layer=1)
        if not player.in_car and player in all_sprites:
            if pygame.sprite.spritecollide(player, zombie_group, False, pygame.sprite.collide_circle):
                game_over = True
        if player.in_car and car.alive():
            if not pygame.Rect(0, 0, LEVEL_WIDTH, LEVEL_HEIGHT).collidepoint(car.rect.center):
                game_won = True

        # Drawing
        screen.fill(BLACK)

        # floor tiles
        for y in range(OUTER_WALL_MARGIN // INTERNAL_WALL_GRID_SNAP, (LEVEL_HEIGHT - OUTER_WALL_MARGIN) // INTERNAL_WALL_GRID_SNAP):
            for x in range(OUTER_WALL_MARGIN // INTERNAL_WALL_GRID_SNAP, (LEVEL_WIDTH - OUTER_WALL_MARGIN) // INTERNAL_WALL_GRID_SNAP):
                if (x + y) % 2 == 0:
                    lx, ly = x * INTERNAL_WALL_GRID_SNAP, y * INTERNAL_WALL_GRID_SNAP
                    r = pygame.Rect(lx, ly, INTERNAL_WALL_GRID_SNAP, INTERNAL_WALL_GRID_SNAP)
                    sr = camera.apply_rect(r)
                    if sr.colliderect(screen.get_rect()):
                            pygame.draw.rect(screen, DARK_GRAY, sr)

        # player, car, zombies, walls
        for sprite in all_sprites:
            sprite_screen_rect = camera.apply_rect(sprite.rect)
            if sprite_screen_rect.colliderect(screen.get_rect().inflate(100, 100)):
                screen.blit(sprite.image, sprite_screen_rect)

        # fog
        if not game_over and not game_won:
            # Soft Fog Layer
            fog_surface_soft.fill(FOG_COLOR_SOFT)
            fov_target = car if player.in_car and car.alive() else player
            fov_center_on_screen = camera.apply(fov_target).center
            soft_radius = int(FOV_RADIUS * FOV_RADIUS_SOFT_FACTOR)
            pygame.draw.circle(fog_surface_soft, (0, 0, 0, 0), fov_center_on_screen, FOV_RADIUS)
            screen.blit(fog_surface_soft, (0, 0))
            # Hard Fog Layer
            fog_surface_hard.fill(FOG_COLOR)
            pygame.draw.circle(fog_surface_hard, (0, 0, 0, 0), fov_center_on_screen, soft_radius)
            screen.blit(fog_surface_hard, (0, 0))

        pygame.display.flip()

    pygame.quit()
    sys.exit()


# --- Run ---
def main():
    while True:
        try:
            game()
        except SystemExit:
            break
        except Exception as e:
            print(f"Error: {e}")
            traceback.print_exc()
            pygame.quit()
            break


if __name__ == "__main__":
    main()
