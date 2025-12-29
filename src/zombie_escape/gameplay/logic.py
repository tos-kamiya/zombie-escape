from __future__ import annotations

from bisect import bisect_left
from typing import Any, Mapping, Sequence

import math
import random

import pygame

from ..colors import (
    INTERNAL_WALL_BORDER_COLOR,
    INTERNAL_WALL_COLOR,
    OUTER_WALL_BORDER_COLOR,
    OUTER_WALL_COLOR,
)
from ..constants import (
    CAR_SPEED,
    CAR_ZOMBIE_DAMAGE,
    CELL_SIZE,
    COMPANION_RADIUS,
    DEFAULT_FLASHLIGHT_SPAWN_COUNT,
    FAST_ZOMBIE_BASE_SPEED,
    FLASHLIGHT_PICKUP_RADIUS,
    FOOTPRINT_MAX,
    FOOTPRINT_STEP_DISTANCE,
    FUEL_HINT_DURATION_MS,
    FUEL_PICKUP_RADIUS,
    INTERNAL_WALL_HEALTH,
    LEVEL_GRID_COLS,
    LEVEL_HEIGHT,
    LEVEL_WIDTH,
    MAX_ZOMBIES,
    OUTER_WALL_HEALTH,
    PLAYER_RADIUS,
    PLAYER_SPEED,
    SCREEN_HEIGHT,
    SCREEN_WIDTH,
    STEEL_BEAM_HEALTH,
    SURVIVOR_CONVERSION_LINE_KEYS,
    SURVIVOR_MAX_SAFE_PASSENGERS,
    SURVIVOR_MESSAGE_DURATION_MS,
    SURVIVOR_MIN_SPEED_FACTOR,
    SURVIVOR_OVERLOAD_DAMAGE_RATIO,
    SURVIVOR_RADIUS,
    SURVIVOR_SPAWN_RATE,
    SURVIVOR_SPEED_PENALTY_PER_PASSENGER,
    ZOMBIE_INTERIOR_SPAWN_RATE,
    ZOMBIE_RADIUS,
    ZOMBIE_SEPARATION_DISTANCE,
    ZOMBIE_SPAWN_DELAY_MS,
    ZOMBIE_SPAWN_PLAYER_BUFFER,
    ZOMBIE_SPEED,
)
from ..localization import translate as _
from ..level_blueprints import choose_blueprint
from ..models import Areas, GameData, Groups, ProgressState, Stage
from ..entities import (
    Camera,
    Car,
    Companion,
    Flashlight,
    FuelCan,
    Player,
    SteelBeam,
    Survivor,
    Wall,
    Zombie,
)

__all__ = [
    "create_zombie",
    "rect_for_cell",
    "generate_level_from_blueprint",
    "place_new_car",
    "place_fuel_can",
    "place_flashlight",
    "place_flashlights",
    "place_companion",
    "scatter_positions_on_walkable",
    "spawn_survivors",
    "update_survivors",
    "calculate_car_speed_for_passengers",
    "apply_passenger_speed_penalty",
    "add_survivor_message",
    "random_survivor_conversion_line",
    "cleanup_survivor_messages",
    "drop_survivors_from_car",
    "handle_survivor_zombie_collisions",
    "respawn_rescued_companion_near_player",
    "get_shrunk_sprite",
    "update_footprints",
    "initialize_game_state",
    "setup_player_and_car",
    "spawn_initial_zombies",
    "process_player_input",
    "update_entities",
    "check_interactions",
]


def create_zombie(
    config: dict[str, Any],
    *,
    start_pos: tuple[int, int] | None = None,
    hint_pos: tuple[float, float] | None = None,
) -> Zombie:
    """Factory to create zombies with optional fast variants."""
    fast_conf = config.get("fast_zombies", {})
    fast_enabled = fast_conf.get("enabled", True)
    if fast_enabled:
        base_speed = random.uniform(ZOMBIE_SPEED, FAST_ZOMBIE_BASE_SPEED)
    else:
        base_speed = ZOMBIE_SPEED
    base_speed = min(base_speed, PLAYER_SPEED - 0.05)
    return Zombie(
        start_pos=start_pos,
        hint_pos=hint_pos,
        speed=base_speed,
    )


def rect_for_cell(x_idx: int, y_idx: int) -> pygame.Rect:
    return pygame.Rect(x_idx * CELL_SIZE, y_idx * CELL_SIZE, CELL_SIZE, CELL_SIZE)


def generate_level_from_blueprint(
    game_data: GameData, config: dict[str, Any]
) -> dict[str, list[pygame.Rect]]:
    """Build walls/spawn candidates/outside area from a blueprint grid."""
    wall_group = game_data.groups.wall_group
    all_sprites = game_data.groups.all_sprites

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

    outside_rects: list[pygame.Rect] = []
    walkable_cells: list[pygame.Rect] = []
    player_cells: list[pygame.Rect] = []
    car_cells: list[pygame.Rect] = []
    zombie_cells: list[pygame.Rect] = []

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


def place_new_car(
    wall_group: pygame.sprite.Group,
    player: Player,
    walkable_cells: list[pygame.Rect],
) -> Car | None:
    if not walkable_cells:
        return None

    max_attempts = 150
    for attempt in range(max_attempts):
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
    walkable_cells: list[pygame.Rect], player: Player, *, car: Car | None = None
) -> FuelCan | None:
    """Pick a spawn spot for the fuel can away from the player (and car if given)."""
    if not walkable_cells:
        return None

    min_player_dist = 250
    min_car_dist = 200

    for attempt in range(200):
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
    walkable_cells: list[pygame.Rect], player: Player, *, car: Car | None = None
) -> Flashlight | None:
    """Pick a spawn spot for the flashlight away from the player (and car if given)."""
    if not walkable_cells:
        return None

    min_player_dist = 260
    min_car_dist = 200

    for attempt in range(200):
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
    walkable_cells: list[pygame.Rect],
    player: Player,
    *,
    car: Car | None = None,
    count: int = DEFAULT_FLASHLIGHT_SPAWN_COUNT,
) -> list[Flashlight]:
    """Spawn multiple flashlights using the single-place helper to spread them out."""
    placed: list[Flashlight] = []
    attempts = 0
    max_attempts = max(200, count * 80)
    while len(placed) < count and attempts < max_attempts:
        attempts += 1
        fl = place_flashlight(walkable_cells, player, car=car)
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
    walkable_cells: list[pygame.Rect], player: Player, *, car: Car | None = None
) -> Companion | None:
    """Spawn the stranded buddy somewhere on a walkable tile away from the player and car."""
    if not walkable_cells:
        return None

    min_player_dist = 240
    min_car_dist = 180

    for attempt in range(200):
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


def scatter_positions_on_walkable(
    walkable_cells: list[pygame.Rect],
    spawn_rate: float,
    *,
    jitter_ratio: float = 0.35,
) -> list[tuple[int, int]]:
    positions: list[tuple[int, int]] = []
    if not walkable_cells or spawn_rate <= 0:
        return positions

    clamped_rate = max(0.0, min(1.0, spawn_rate))
    for cell in walkable_cells:
        if random.random() >= clamped_rate:
            continue
        jitter_x = random.uniform(-cell.width * jitter_ratio, cell.width * jitter_ratio)
        jitter_y = random.uniform(
            -cell.height * jitter_ratio, cell.height * jitter_ratio
        )
        positions.append((int(cell.centerx + jitter_x), int(cell.centery + jitter_y)))
    return positions


def spawn_survivors(
    game_data: GameData, layout_data: Mapping[str, list[pygame.Rect]]
) -> list[Survivor]:
    """Populate Stage 4 with passive survivors on open tiles."""
    survivors: list[Survivor] = []
    if not game_data.stage.survivor_stage:
        return survivors

    walkable = layout_data.get("walkable_cells", [])
    wall_group = game_data.groups.wall_group
    survivor_group = game_data.groups.survivor_group
    all_sprites = game_data.groups.all_sprites

    for pos in scatter_positions_on_walkable(walkable, SURVIVOR_SPAWN_RATE):
        s = Survivor(*pos)
        if pygame.sprite.spritecollideany(s, wall_group):
            continue
        survivor_group.add(s)
        all_sprites.add(s, layer=1)
        survivors.append(s)

    return survivors


def update_survivors(game_data: GameData) -> None:
    if not game_data.stage.survivor_stage:
        return
    survivor_group = game_data.groups.survivor_group
    wall_group = game_data.groups.wall_group
    player = game_data.player
    car = game_data.car
    if not player:
        return
    target_rect = car.rect if player.in_car and car and car.alive() else player.rect
    target_pos = target_rect.center
    survivors = [s for s in survivor_group if getattr(s, "alive", lambda: False)()]
    for survivor in survivors:
        survivor.update_behavior(target_pos, wall_group)

    # Gently prevent survivors from overlapping the player or each other
    def _separate_from_point(
        survivor: Survivor, point: tuple[float, float], min_dist: float
    ) -> None:
        dx = point[0] - survivor.x
        dy = point[1] - survivor.y
        dist = math.hypot(dx, dy)
        if dist == 0:
            angle = random.uniform(0, math.tau)
            dx, dy = math.cos(angle), math.sin(angle)
            dist = 1
        if dist < min_dist:
            push = min_dist - dist
            survivor.x -= (dx / dist) * push
            survivor.y -= (dy / dist) * push
            survivor.rect.center = (int(survivor.x), int(survivor.y))

    player_overlap = (SURVIVOR_RADIUS + PLAYER_RADIUS) * 1.05
    survivor_overlap = (SURVIVOR_RADIUS * 2) * 1.05

    player_point = (player.x, player.y)
    for survivor in survivors:
        _separate_from_point(survivor, player_point, player_overlap)

    survivors_with_x = sorted(
        ((survivor.x, survivor) for survivor in survivors), key=lambda item: item[0]
    )
    for i, (base_x, survivor) in enumerate(survivors_with_x):
        for other_base_x, other in survivors_with_x[i + 1 :]:
            if other_base_x - base_x > survivor_overlap:
                break
            dx = other.x - survivor.x
            dy = other.y - survivor.y
            dist = math.hypot(dx, dy)
            if dist == 0:
                angle = random.uniform(0, math.tau)
                dx, dy = math.cos(angle), math.sin(angle)
                dist = 1
            if dist < survivor_overlap:
                push = (survivor_overlap - dist) / 2
                offset_x = (dx / dist) * push
                offset_y = (dy / dist) * push
                survivor.x -= offset_x
                survivor.y -= offset_y
                other.x += offset_x
                other.y += offset_y
                survivor.rect.center = (int(survivor.x), int(survivor.y))
                other.rect.center = (int(other.x), int(other.y))


def calculate_car_speed_for_passengers(passengers: int) -> float:
    penalty = SURVIVOR_SPEED_PENALTY_PER_PASSENGER * passengers
    penalty = min(0.95, max(0.0, penalty))
    adjusted = CAR_SPEED * (1 - penalty)
    return max(CAR_SPEED * SURVIVOR_MIN_SPEED_FACTOR, adjusted)


def apply_passenger_speed_penalty(game_data: GameData) -> None:
    car = game_data.car
    if not car:
        return
    if not game_data.stage.survivor_stage:
        car.speed = CAR_SPEED
        return
    car.speed = calculate_car_speed_for_passengers(game_data.state.survivors_onboard)


def add_survivor_message(game_data: GameData, text: str) -> None:
    expires = pygame.time.get_ticks() + SURVIVOR_MESSAGE_DURATION_MS
    game_data.state.survivor_messages.append({"text": text, "expires_at": expires})


def random_survivor_conversion_line() -> str:
    if not SURVIVOR_CONVERSION_LINE_KEYS:
        return ""
    key = random.choice(SURVIVOR_CONVERSION_LINE_KEYS)
    return _(key)


def cleanup_survivor_messages(state: ProgressState) -> None:
    now = pygame.time.get_ticks()
    state.survivor_messages = [
        msg for msg in state.survivor_messages if msg.get("expires_at", 0) > now
    ]


def drop_survivors_from_car(game_data: GameData, origin: tuple[int, int]) -> None:
    """Respawn boarded survivors back into the world after a crash."""
    count = game_data.state.survivors_onboard
    if count <= 0:
        return
    wall_group = game_data.groups.wall_group
    survivor_group = game_data.groups.survivor_group
    all_sprites = game_data.groups.all_sprites

    for survivor_idx in range(count):
        placed = False
        for attempt in range(6):
            angle = random.uniform(0, math.tau)
            dist = random.uniform(16, 40)
            pos = (
                origin[0] + math.cos(angle) * dist,
                origin[1] + math.sin(angle) * dist,
            )
            s = Survivor(*pos)
            if not pygame.sprite.spritecollideany(s, wall_group):
                survivor_group.add(s)
                all_sprites.add(s, layer=1)
                placed = True
                break
        if not placed:
            s = Survivor(*origin)
            survivor_group.add(s)
            all_sprites.add(s, layer=1)

    game_data.state.survivors_onboard = 0
    apply_passenger_speed_penalty(game_data)


def handle_survivor_zombie_collisions(
    game_data: GameData, config: dict[str, Any]
) -> None:
    if not game_data.stage.survivor_stage:
        return
    survivor_group = game_data.groups.survivor_group
    if not survivor_group:
        return
    zombie_group = game_data.groups.zombie_group
    zombies = [z for z in zombie_group if getattr(z, "alive", lambda: False)()]
    if not zombies:
        return
    zombies.sort(key=lambda s: s.rect.centerx)
    zombie_xs = [z.rect.centerx for z in zombies]
    camera = game_data.camera
    screen_rect = pygame.Rect(0, 0, SCREEN_WIDTH, SCREEN_HEIGHT)

    for survivor in list(survivor_group):
        if not survivor.alive():
            continue
        survivor_radius = getattr(survivor, "radius", SURVIVOR_RADIUS)
        search_radius = survivor_radius + ZOMBIE_RADIUS
        search_radius_sq = search_radius * search_radius

        min_x = survivor.rect.centerx - search_radius
        max_x = survivor.rect.centerx + search_radius
        start_idx = bisect_left(zombie_xs, min_x)
        collided = False
        for idx in range(start_idx, len(zombies)):
            zombie_x = zombie_xs[idx]
            if zombie_x > max_x:
                break
            zombie = zombies[idx]
            if not zombie.alive():
                continue
            dy = zombie.rect.centery - survivor.rect.centery
            if abs(dy) > search_radius:
                continue
            dx = zombie_x - survivor.rect.centerx
            if dx * dx + dy * dy <= search_radius_sq:
                collided = True
                break

        if not collided:
            continue
        if not camera.apply_rect(survivor.rect).colliderect(screen_rect):
            continue
        survivor.kill()
        line = random_survivor_conversion_line()
        if line:
            add_survivor_message(game_data, line)
        new_zombie = create_zombie(config, start_pos=survivor.rect.center)
        zombie_group.add(new_zombie)
        game_data.groups.all_sprites.add(new_zombie, layer=1)
        insert_idx = bisect_left(zombie_xs, new_zombie.rect.centerx)
        zombie_xs.insert(insert_idx, new_zombie.rect.centerx)
        zombies.insert(insert_idx, new_zombie)


def respawn_rescued_companion_near_player(game_data: GameData) -> None:
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
    assert player is not None
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
    sprite_obj: pygame.sprite.Sprite, scale_x: float, *, scale_y: float | None = None
) -> pygame.sprite.Sprite:
    if scale_y is None:
        scale_y = scale_x

    original_rect = sprite_obj.rect
    shrunk_width = int(original_rect.width * scale_x)
    shrunk_height = int(original_rect.height * scale_y)

    shrunk_width = max(1, shrunk_width)
    shrunk_height = max(1, shrunk_height)

    rect = pygame.Rect(0, 0, shrunk_width, shrunk_height)
    rect.center = original_rect.center

    new_sprite = pygame.sprite.Sprite()
    new_sprite.rect = rect

    return new_sprite


def update_footprints(game_data: GameData, config: dict[str, Any]) -> None:
    """Record player steps and clean up old footprints."""
    state = game_data.state
    player = game_data.player
    assert player is not None
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


def initialize_game_state(config: dict[str, Any], stage: Stage) -> GameData:
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
        survivors_onboard=0,
        survivors_rescued=0,
        survivor_messages=[],
    )

    # Create sprite groups
    all_sprites = pygame.sprite.LayeredUpdates()
    wall_group = pygame.sprite.Group()
    zombie_group = pygame.sprite.Group()
    survivor_group = pygame.sprite.Group()

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
            all_sprites=all_sprites,
            wall_group=wall_group,
            zombie_group=zombie_group,
            survivor_group=survivor_group,
        ),
        camera=camera,
        areas=Areas(
            outer_rect=outer_rect,
            inner_rect=inner_rect,
            outside_rects=[],
            walkable_cells=[],
        ),
        fog={
            "hard": fog_surface_hard,
            "soft": fog_surface_soft,
            "hatch_patterns": {},
            "overlays": {},
        },
        stage=stage,
        fuel=None,
        flashlights=[],
        companion=None,
    )


def setup_player_and_car(
    game_data: GameData, layout_data: Mapping[str, list[pygame.Rect]]
) -> tuple[Player, Car]:
    """Create and position the player and car using blueprint candidates."""
    all_sprites = game_data.groups.all_sprites
    walkable_cells: list[pygame.Rect] = layout_data["walkable_cells"]

    def pick_center(cells: list[pygame.Rect]) -> tuple[int, int]:
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
    for attempt in range(200):
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


def spawn_initial_zombies(
    game_data: GameData,
    player: Player,
    layout_data: Mapping[str, list[pygame.Rect]],
    config: dict[str, Any],
) -> None:
    """Spawn initial zombies using blueprint candidate cells."""
    wall_group = game_data.groups.wall_group
    zombie_group = game_data.groups.zombie_group
    all_sprites = game_data.groups.all_sprites

    spawn_cells = layout_data["walkable_cells"]
    if not spawn_cells:
        return

    spawn_rate = ZOMBIE_INTERIOR_SPAWN_RATE
    positions = scatter_positions_on_walkable(spawn_cells, spawn_rate)
    if not positions:
        positions = scatter_positions_on_walkable(spawn_cells, spawn_rate * 1.5)

    for pos in positions:
        if (
            math.hypot(pos[0] - player.x, pos[1] - player.y)
            < ZOMBIE_SPAWN_PLAYER_BUFFER
        ):
            continue
        tentative = create_zombie(config, start_pos=pos)
        if pygame.sprite.spritecollideany(tentative, wall_group):
            continue
        zombie_group.add(tentative)
        all_sprites.add(tentative, layer=1)

    game_data.state.last_zombie_spawn_time = (
        pygame.time.get_ticks() - ZOMBIE_SPAWN_DELAY_MS
    )


def process_player_input(
    keys: Sequence[bool], player: Player, car: Car
) -> tuple[float, float, float, float]:
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
        target_speed = getattr(car, "speed", CAR_SPEED)
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


def update_entities(
    game_data: GameData,
    player_dx: float,
    player_dy: float,
    car_dx: float,
    car_dy: float,
    config: dict[str, Any],
) -> None:
    """Update positions and states of game entities."""
    player = game_data.player
    assert player is not None
    car = game_data.car
    assert car is not None
    companion = game_data.companion
    wall_group = game_data.groups.wall_group
    all_sprites = game_data.groups.all_sprites
    zombie_group = game_data.groups.zombie_group
    camera = game_data.camera
    stage = game_data.stage

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

    update_survivors(game_data)

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

    survivors_on_screen: list[Survivor] = []
    if stage.survivor_stage:
        survivor_group = game_data.groups.survivor_group
        for survivor in survivor_group:
            if getattr(survivor, "alive", lambda: False)():
                if camera.apply_rect(survivor.rect).colliderect(screen_rect):
                    survivors_on_screen.append(survivor)

    zombies_sorted: list[Zombie] = sorted(list(zombie_group), key=lambda z: z.x)

    def _nearby_zombies(index: int) -> list[Zombie]:
        center = zombies_sorted[index]
        neighbors: list[Zombie] = []
        search_radius = ZOMBIE_SEPARATION_DISTANCE + PLAYER_SPEED
        for left in range(index - 1, -1, -1):
            other = zombies_sorted[left]
            if center.x - other.x > search_radius:
                break
            if other.alive():
                neighbors.append(other)
        for right in range(index + 1, len(zombies_sorted)):
            other = zombies_sorted[right]
            if other.x - center.x > search_radius:
                break
            if other.alive():
                neighbors.append(other)
        return neighbors

    for idx, zombie in enumerate(zombies_sorted):
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

        if stage.survivor_stage:
            zombie_on_screen = camera.apply_rect(zombie.rect).colliderect(screen_rect)
            if zombie_on_screen:
                candidate_positions: list[tuple[int, int]] = []
                for survivor in survivors_on_screen:
                    candidate_positions.append(survivor.rect.center)
                if companion and companion_on_screen:
                    candidate_positions.append(companion.rect.center)
                candidate_positions.append(player.rect.center)
                if candidate_positions:
                    target = min(
                        candidate_positions,
                        key=lambda pos: math.hypot(
                            pos[0] - zombie.x, pos[1] - zombie.y
                        ),
                    )
        nearby_candidates = _nearby_zombies(idx)
        zombie.update(target, wall_group, nearby_candidates)


def check_interactions(
    game_data: GameData, config: dict[str, Any]
) -> pygame.sprite.Sprite | None:
    """Check and handle interactions between entities."""
    player = game_data.player
    assert player is not None
    car = game_data.car
    assert car is not None
    companion = game_data.companion
    zombie_group = game_data.groups.zombie_group
    wall_group = game_data.groups.wall_group
    all_sprites = game_data.groups.all_sprites
    survivor_group = game_data.groups.survivor_group
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
        assert companion is not None
        screen_rect = pygame.Rect(0, 0, SCREEN_WIDTH, SCREEN_HEIGHT)
        companion_on_screen = camera.apply_rect(companion.rect).colliderect(screen_rect)

    # Companion interactions (Stage 3)
    if companion_active and stage.requires_companion:
        assert companion is not None
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
                state.game_over_message = _("game_over.scream")
                state.game_over = True
                state.game_over_at = state.game_over_at or pygame.time.get_ticks()
            else:
                if walkable_cells:
                    new_cell = random.choice(walkable_cells)
                    companion.teleport(new_cell.center)
                else:
                    companion.teleport((LEVEL_WIDTH // 2, LEVEL_HEIGHT // 2))
                companion.following = False

    shrunk_car = get_shrunk_sprite(car, 0.8) if car else None

    # Player entering car
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

    if (
        stage.survivor_stage
        and player.in_car
        and car.alive()
        and shrunk_car
        and survivor_group
    ):
        boarded = pygame.sprite.spritecollide(
            shrunk_car, survivor_group, True, pygame.sprite.collide_circle
        )
        if boarded:
            state.survivors_onboard += len(boarded)
            apply_passenger_speed_penalty(game_data)
            if state.survivors_onboard > SURVIVOR_MAX_SAFE_PASSENGERS:
                overload_damage = max(
                    1, int(game_data.car.max_health * SURVIVOR_OVERLOAD_DAMAGE_RATIO)
                )
                add_survivor_message(game_data, _("survivors.too_many_aboard"))
                game_data.car.take_damage(overload_damage)

    if stage.survivor_stage:
        handle_survivor_zombie_collisions(game_data, config)

    # Handle car destruction
    if car.alive() and car.health <= 0:
        car_destroyed_pos = car.rect.center
        car.kill()
        if stage.survivor_stage:
            drop_survivors_from_car(game_data, car_destroyed_pos)
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
            apply_passenger_speed_penalty(game_data)
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
                state.game_over_message = _("game_over.scream")

    # Player escaping the level
    if player.in_car and car.alive() and state.has_fuel:
        companion_ready = not stage.requires_companion or state.companion_rescued
        if companion_ready and any(
            outside.collidepoint(car.rect.center) for outside in outside_rects
        ):
            if stage.survivor_stage and state.survivors_onboard:
                state.survivors_rescued += state.survivors_onboard
                state.survivors_onboard = 0
                state.next_overload_check_ms = 0
                apply_passenger_speed_penalty(game_data)
            state.game_won = True

    # Return fog of view target
    if not state.game_over and not state.game_won:
        return car if player.in_car and car.alive() else player
    return None
