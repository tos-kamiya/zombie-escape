from __future__ import annotations

from bisect import bisect_left
from typing import Any, Mapping, Sequence

import math

import pygame

from ..colors import (
    DAWN_AMBIENT_PALETTE_KEY,
    ambient_palette_key_for_flashlights,
    get_environment_palette,
)
from ..gameplay_constants import (
    CAR_HEIGHT,
    CAR_SPEED,
    CAR_WIDTH,
    CAR_ZOMBIE_DAMAGE,
    BUDDY_RADIUS,
    DEFAULT_FLASHLIGHT_SPAWN_COUNT,
    FAST_ZOMBIE_BASE_SPEED,
    FLASHLIGHT_HEIGHT,
    FLASHLIGHT_WIDTH,
    FOOTPRINT_MAX,
    FOOTPRINT_STEP_DISTANCE,
    FUEL_CAN_HEIGHT,
    FUEL_CAN_WIDTH,
    FUEL_HINT_DURATION_MS,
    INTERNAL_WALL_HEALTH,
    MAX_ZOMBIES,
    OUTER_WALL_HEALTH,
    PLAYER_RADIUS,
    PLAYER_SPEED,
    STEEL_BEAM_HEALTH,
    SURVIVOR_CONVERSION_LINE_KEYS,
    SURVIVOR_APPROACH_RADIUS,
    SURVIVOR_MAX_SAFE_PASSENGERS,
    SURVIVOR_MESSAGE_DURATION_MS,
    SURVIVOR_MIN_SPEED_FACTOR,
    SURVIVOR_OVERLOAD_DAMAGE_RATIO,
    SURVIVOR_RADIUS,
    SURVIVOR_SPEED_PENALTY_PER_PASSENGER,
    SURVIVOR_STAGE_WAITING_CAR_COUNT,
    SURVIVAL_NEAR_SPAWN_MAX_DISTANCE,
    SURVIVAL_NEAR_SPAWN_MIN_DISTANCE,
    ZOMBIE_AGING_DURATION_FRAMES,
    ZOMBIE_RADIUS,
    ZOMBIE_SEPARATION_DISTANCE,
    ZOMBIE_SPAWN_DELAY_MS,
    ZOMBIE_SPAWN_PLAYER_BUFFER,
    ZOMBIE_SPEED,
    ZOMBIE_TRACKER_AGING_DURATION_FRAMES,
    interaction_radius,
    ZOMBIE_WALL_FOLLOW_SENSOR_DISTANCE,
)
from ..level_constants import GRID_COLS, GRID_ROWS
from ..screen_constants import SCREEN_HEIGHT, SCREEN_WIDTH
from ..localization import translate as tr
from ..level_blueprints import choose_blueprint
from ..models import GameData, Groups, LevelLayout, ProgressState, Stage
from ..rng import get_rng
from ..entities import (
    Camera,
    Car,
    Flashlight,
    FuelCan,
    Player,
    SteelBeam,
    Survivor,
    Wall,
    Zombie,
    random_position_outside_building,
    spritecollideany_walls,
    walls_for_radius,
    WallIndex,
)

LOGICAL_SCREEN_RECT = pygame.Rect(0, 0, SCREEN_WIDTH, SCREEN_HEIGHT)
RNG = get_rng()


def car_appearance_for_stage(stage: Stage | None) -> str:
    return "disabled" if stage and stage.survival_stage else "default"

__all__ = [
    "create_zombie",
    "rect_for_cell",
    "generate_level_from_blueprint",
    "place_new_car",
    "place_fuel_can",
    "place_flashlight",
    "place_flashlights",
    "place_buddies",
    "find_interior_spawn_positions",
    "find_nearby_offscreen_spawn_position",
    "find_exterior_spawn_position",
    "spawn_survivors",
    "spawn_nearby_zombie",
    "spawn_exterior_zombie",
    "spawn_weighted_zombie",
    "update_survivors",
    "alive_waiting_cars",
    "log_waiting_car_count",
    "nearest_waiting_car",
    "calculate_car_speed_for_passengers",
    "apply_passenger_speed_penalty",
    "increase_survivor_capacity",
    "waiting_car_target_count",
    "spawn_waiting_car",
    "maintain_waiting_car_supply",
    "add_survivor_message",
    "random_survivor_conversion_line",
    "cleanup_survivor_messages",
    "drop_survivors_from_car",
    "handle_survivor_zombie_collisions",
    "respawn_buddies_near_player",
    "get_shrunk_sprite",
    "update_footprints",
    "initialize_game_state",
    "setup_player_and_cars",
    "spawn_initial_zombies",
    "update_survival_timer",
    "carbonize_outdoor_zombies",
    "process_player_input",
    "update_entities",
    "check_interactions",
    "set_ambient_palette",
    "sync_ambient_palette_with_flashlights",
]


def create_zombie(
    config: dict[str, Any],
    *,
    start_pos: tuple[int, int] | None = None,
    hint_pos: tuple[float, float] | None = None,
    stage: Stage | None = None,
    tracker: bool | None = None,
    wall_follower: bool | None = None,
    level_width: int,
    level_height: int,
) -> Zombie:
    """Factory to create zombies with optional fast variants."""
    fast_conf = config.get("fast_zombies", {})
    fast_enabled = fast_conf.get("enabled", True)
    if fast_enabled:
        base_speed = RNG.uniform(ZOMBIE_SPEED, FAST_ZOMBIE_BASE_SPEED)
    else:
        base_speed = ZOMBIE_SPEED
    base_speed = min(base_speed, PLAYER_SPEED - 0.05)
    normal_ratio = 1.0
    tracker_ratio = 0.0
    wall_follower_ratio = 0.0
    if stage is not None:
        normal_ratio = max(0.0, min(1.0, getattr(stage, "zombie_normal_ratio", 1.0)))
        tracker_ratio = max(0.0, min(1.0, getattr(stage, "zombie_tracker_ratio", 0.0)))
        wall_follower_ratio = max(
            0.0, min(1.0, getattr(stage, "zombie_wall_follower_ratio", 0.0))
        )
        if normal_ratio + tracker_ratio + wall_follower_ratio <= 0:
            # Fall back to normal behavior if all ratios are zero.
            normal_ratio = 1.0
            tracker_ratio = 0.0
            wall_follower_ratio = 0.0
        if (
            normal_ratio == 1.0
            and (tracker_ratio > 0.0 or wall_follower_ratio > 0.0)
            and tracker_ratio + wall_follower_ratio <= 1.0
        ):
            normal_ratio = max(0.0, 1.0 - tracker_ratio - wall_follower_ratio)
        aging_duration_frames = max(
            1.0,
            float(
                getattr(
                    stage, "zombie_aging_duration_frames", ZOMBIE_AGING_DURATION_FRAMES
                )
            ),
        )
    else:
        aging_duration_frames = ZOMBIE_AGING_DURATION_FRAMES
    picked_tracker = False
    picked_wall_follower = False
    total_ratio = normal_ratio + tracker_ratio + wall_follower_ratio
    if total_ratio > 0:
        pick = RNG.random() * total_ratio
        if pick < normal_ratio:
            pass
        elif pick < normal_ratio + tracker_ratio:
            picked_tracker = True
        else:
            picked_wall_follower = True
    if tracker is None:
        tracker = picked_tracker
    if wall_follower is None:
        wall_follower = picked_wall_follower
    if tracker:
        wall_follower = False
    if tracker:
        ratio = (
            ZOMBIE_TRACKER_AGING_DURATION_FRAMES / ZOMBIE_AGING_DURATION_FRAMES
            if ZOMBIE_AGING_DURATION_FRAMES > 0
            else 1.0
        )
        aging_duration_frames = max(1.0, aging_duration_frames * ratio)
    return Zombie(
        start_pos=start_pos,
        hint_pos=hint_pos,
        speed=base_speed,
        tracker=tracker,
        wall_follower=wall_follower,
        aging_duration_frames=aging_duration_frames,
        level_width=level_width,
        level_height=level_height,
    )


def rect_for_cell(x_idx: int, y_idx: int, cell_size: int) -> pygame.Rect:
    return pygame.Rect(
        x_idx * cell_size,
        y_idx * cell_size,
        cell_size,
        cell_size,
    )


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
    cell_size = game_data.cell_size
    outer_wall_cells = {
        (x, y)
        for y, row in enumerate(blueprint)
        for x, ch in enumerate(row)
        if ch == "B"
    }
    wall_cells = {
        (x, y)
        for y, row in enumerate(blueprint)
        for x, ch in enumerate(row)
        if ch in {"B", "1"}
    }

    def has_wall(nx: int, ny: int) -> bool:
        if nx < 0 or ny < 0 or nx >= GRID_COLS or ny >= GRID_ROWS:
            return True
        return (nx, ny) in wall_cells

    outside_rects: list[pygame.Rect] = []
    walkable_cells: list[pygame.Rect] = []
    player_cells: list[pygame.Rect] = []
    car_cells: list[pygame.Rect] = []
    zombie_cells: list[pygame.Rect] = []
    palette = get_environment_palette(game_data.state.ambient_palette_key)

    def add_beam_to_groups(beam: "SteelBeam") -> None:
        if getattr(beam, "_added_to_groups", False):
            return
        wall_group.add(beam)
        all_sprites.add(beam, layer=0)
        beam._added_to_groups = True

    for y, row in enumerate(blueprint):
        if len(row) != GRID_COLS:
            raise ValueError(
                f"Blueprint width mismatch at row {y}: {len(row)} != {GRID_COLS}"
            )
        for x, ch in enumerate(row):
            cell_rect = rect_for_cell(x, y, cell_size)
            cell_has_beam = steel_enabled and (x, y) in steel_cells
            if ch == "O":
                outside_rects.append(cell_rect)
                continue
            if ch == "B":
                draw_bottom_side = not has_wall(x, y + 1)
                wall = Wall(
                    cell_rect.x,
                    cell_rect.y,
                    cell_rect.width,
                    cell_rect.height,
                    health=OUTER_WALL_HEALTH,
                    color=palette.outer_wall,
                    border_color=palette.outer_wall_border,
                    palette_category="outer_wall",
                    bevel_depth=0,
                    draw_bottom_side=draw_bottom_side,
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
                draw_bottom_side = not has_wall(x, y + 1)
                bevel_mask = (
                    not has_wall(x, y - 1)
                    and not has_wall(x - 1, y)
                    and not has_wall(x - 1, y - 1),
                    not has_wall(x, y - 1)
                    and not has_wall(x + 1, y)
                    and not has_wall(x + 1, y - 1),
                    not has_wall(x, y + 1)
                    and not has_wall(x + 1, y)
                    and not has_wall(x + 1, y + 1),
                    not has_wall(x, y + 1)
                    and not has_wall(x - 1, y)
                    and not has_wall(x - 1, y + 1),
                )
                wall = Wall(
                    cell_rect.x,
                    cell_rect.y,
                    cell_rect.width,
                    cell_rect.height,
                    health=INTERNAL_WALL_HEALTH,
                    color=palette.inner_wall,
                    border_color=palette.inner_wall_border,
                    palette_category="inner_wall",
                    bevel_mask=bevel_mask,
                    draw_bottom_side=draw_bottom_side,
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

    game_data.layout.outer_rect = (0, 0, game_data.level_width, game_data.level_height)
    game_data.layout.inner_rect = (0, 0, game_data.level_width, game_data.level_height)
    game_data.layout.outside_rects = outside_rects
    game_data.layout.walkable_cells = walkable_cells
    game_data.layout.outer_wall_cells = outer_wall_cells
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
    *,
    existing_cars: Sequence[Car] | None = None,
    appearance: str = "default",
) -> Car | None:
    if not walkable_cells:
        return None

    max_attempts = 150
    for attempt in range(max_attempts):
        cell = RNG.choice(walkable_cells)
        c_x, c_y = cell.center
        temp_car = Car(c_x, c_y, appearance=appearance)
        temp_rect = temp_car.rect.inflate(30, 30)
        nearby_walls = pygame.sprite.Group()
        nearby_walls.add(
            [
                w
                for w in wall_group
                if abs(w.rect.centerx - c_x) < 150 and abs(w.rect.centery - c_y) < 150
            ]
        )
        collides_wall = spritecollideany_walls(temp_car, nearby_walls)
        collides_player = temp_rect.colliderect(player.rect.inflate(50, 50))
        car_overlap = False
        if existing_cars:
            car_overlap = any(
                temp_car.rect.colliderect(other.rect)
                for other in existing_cars
                if other and other.alive()
            )
        if not collides_wall and not collides_player and not car_overlap:
            return temp_car
    return None


def place_fuel_can(
    walkable_cells: list[pygame.Rect],
    player: Player,
    *,
    cars: Sequence[Car] | None = None,
    count: int = 1,
) -> FuelCan | None:
    """Pick a spawn spot for the fuel can away from the player (and car if given)."""
    if count <= 0 or not walkable_cells:
        return None

    min_player_dist = 250
    min_car_dist = 200
    min_player_dist_sq = min_player_dist * min_player_dist
    min_car_dist_sq = min_car_dist * min_car_dist

    for attempt in range(200):
        cell = RNG.choice(walkable_cells)
        dx = cell.centerx - player.x
        dy = cell.centery - player.y
        if dx * dx + dy * dy < min_player_dist_sq:
            continue
        if cars:
            too_close = False
            for parked_car in cars:
                dx = cell.centerx - parked_car.rect.centerx
                dy = cell.centery - parked_car.rect.centery
                if dx * dx + dy * dy < min_car_dist_sq:
                    too_close = True
                    break
            if too_close:
                continue
        return FuelCan(cell.centerx, cell.centery)

    # Fallback: drop near a random walkable cell
    cell = RNG.choice(walkable_cells)
    return FuelCan(cell.centerx, cell.centery)


def place_flashlight(
    walkable_cells: list[pygame.Rect],
    player: Player,
    *,
    cars: Sequence[Car] | None = None,
) -> Flashlight | None:
    """Pick a spawn spot for the flashlight away from the player (and car if given)."""
    if not walkable_cells:
        return None

    min_player_dist = 260
    min_car_dist = 200
    min_player_dist_sq = min_player_dist * min_player_dist
    min_car_dist_sq = min_car_dist * min_car_dist

    for attempt in range(200):
        cell = RNG.choice(walkable_cells)
        dx = cell.centerx - player.x
        dy = cell.centery - player.y
        if dx * dx + dy * dy < min_player_dist_sq:
            continue
        if cars:
            if any(
                (cell.centerx - parked.rect.centerx) ** 2
                + (cell.centery - parked.rect.centery) ** 2
                < min_car_dist_sq
                for parked in cars
            ):
                continue
        return Flashlight(cell.centerx, cell.centery)

    cell = RNG.choice(walkable_cells)
    return Flashlight(cell.centerx, cell.centery)


def place_flashlights(
    walkable_cells: list[pygame.Rect],
    player: Player,
    *,
    cars: Sequence[Car] | None = None,
    count: int = DEFAULT_FLASHLIGHT_SPAWN_COUNT,
) -> list[Flashlight]:
    """Spawn multiple flashlights using the single-place helper to spread them out."""
    placed: list[Flashlight] = []
    attempts = 0
    max_attempts = max(200, count * 80)
    while len(placed) < count and attempts < max_attempts:
        attempts += 1
        fl = place_flashlight(walkable_cells, player, cars=cars)
        if not fl:
            break
        # Avoid clustering too tightly
        if any(
            (other.rect.centerx - fl.rect.centerx) ** 2
            + (other.rect.centery - fl.rect.centery) ** 2
            < 120 * 120
            for other in placed
        ):
            continue
        placed.append(fl)
    return placed


def place_buddies(
    walkable_cells: list[pygame.Rect],
    player: Player,
    *,
    cars: Sequence[Car] | None = None,
    count: int = 1,
) -> list[Survivor]:
    placed: list[Survivor] = []
    if count <= 0 or not walkable_cells:
        return placed
    min_player_dist = 240
    positions = find_interior_spawn_positions(
        walkable_cells,
        1.0,
        player=player,
        min_player_dist=min_player_dist,
    )
    RNG.shuffle(positions)
    for pos in positions[:count]:
        placed.append(Survivor(pos[0], pos[1], is_buddy=True))
    remaining = count - len(placed)
    for _ in range(max(0, remaining)):
        spawn_pos = find_nearby_offscreen_spawn_position(walkable_cells)
        placed.append(Survivor(spawn_pos[0], spawn_pos[1], is_buddy=True))
    return placed


def _scatter_positions_on_walkable(
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
        if RNG.random() >= clamped_rate:
            continue
        jitter_x = RNG.uniform(-cell.width * jitter_ratio, cell.width * jitter_ratio)
        jitter_y = RNG.uniform(
            -cell.height * jitter_ratio, cell.height * jitter_ratio
        )
        positions.append((int(cell.centerx + jitter_x), int(cell.centery + jitter_y)))
    return positions


def spawn_survivors(
    game_data: GameData, layout_data: Mapping[str, list[pygame.Rect]]
) -> list[Survivor]:
    """Populate rescue-stage survivors and buddy-stage buddies."""
    survivors: list[Survivor] = []
    if not (game_data.stage.rescue_stage or game_data.stage.buddy_required_count > 0):
        return survivors

    walkable = layout_data.get("walkable_cells", [])
    wall_group = game_data.groups.wall_group
    survivor_group = game_data.groups.survivor_group
    all_sprites = game_data.groups.all_sprites

    if game_data.stage.rescue_stage:
        positions = find_interior_spawn_positions(
            walkable,
            game_data.stage.survivor_spawn_rate,
        )
        for pos in positions:
            s = Survivor(*pos)
            if spritecollideany_walls(s, wall_group):
                continue
            survivor_group.add(s)
            all_sprites.add(s, layer=1)
            survivors.append(s)

    if game_data.stage.buddy_required_count > 0:
        buddy_count = max(0, game_data.stage.buddy_required_count)
        buddies: list[Survivor] = []
        if game_data.player:
            buddies = place_buddies(
                walkable,
                game_data.player,
                cars=game_data.waiting_cars,
                count=buddy_count,
            )
        for buddy in buddies:
            if spritecollideany_walls(buddy, wall_group):
                continue
            survivor_group.add(buddy)
            all_sprites.add(buddy, layer=2)
            survivors.append(buddy)

    return survivors


def update_survivors(
    game_data: GameData, wall_index: WallIndex | None = None
) -> None:
    if not (game_data.stage.rescue_stage or game_data.stage.buddy_required_count > 0):
        return
    survivor_group = game_data.groups.survivor_group
    wall_group = game_data.groups.wall_group
    player = game_data.player
    car = game_data.car
    if not player:
        return
    target_rect = car.rect if player.in_car and car and car.alive() else player.rect
    target_pos = target_rect.center
    survivors = [s for s in survivor_group if s.alive()]
    for survivor in survivors:
        survivor.update_behavior(
            target_pos,
            wall_group,
            wall_index=wall_index,
            cell_size=game_data.cell_size,
            level_width=game_data.level_width,
            level_height=game_data.level_height,
        )

    # Gently prevent survivors from overlapping the player or each other
    def _separate_from_point(
        survivor: Survivor, point: tuple[float, float], min_dist: float
    ) -> None:
        dx = point[0] - survivor.x
        dy = point[1] - survivor.y
        dist = math.hypot(dx, dy)
        if dist == 0:
            angle = RNG.uniform(0, math.tau)
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
                angle = RNG.uniform(0, math.tau)
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


def calculate_car_speed_for_passengers(
    passengers: int, *, capacity: int = SURVIVOR_MAX_SAFE_PASSENGERS
) -> float:
    cap = max(1, capacity)
    load_ratio = max(0.0, passengers / cap)
    penalty = SURVIVOR_SPEED_PENALTY_PER_PASSENGER * load_ratio
    penalty = min(0.95, max(0.0, penalty))
    adjusted = CAR_SPEED * (1 - penalty)
    if passengers <= cap:
        return max(CAR_SPEED * SURVIVOR_MIN_SPEED_FACTOR, adjusted)

    overload = passengers - cap
    overload_factor = 1 / math.sqrt(overload + 1)
    overloaded_speed = CAR_SPEED * overload_factor
    return max(CAR_SPEED * SURVIVOR_MIN_SPEED_FACTOR, overloaded_speed)


def apply_passenger_speed_penalty(game_data: GameData) -> None:
    car = game_data.car
    if not car:
        return
    if not game_data.stage.rescue_stage:
        car.speed = CAR_SPEED
        return
    car.speed = calculate_car_speed_for_passengers(
        game_data.state.survivors_onboard,
        capacity=game_data.state.survivor_capacity,
    )


def increase_survivor_capacity(game_data: GameData, increments: int = 1) -> None:
    if increments <= 0:
        return
    if not game_data.stage.rescue_stage:
        return
    state = game_data.state
    state.survivor_capacity += increments * SURVIVOR_MAX_SAFE_PASSENGERS
    apply_passenger_speed_penalty(game_data)


def rect_visible_on_screen(camera: Camera | None, rect: pygame.Rect) -> bool:
    if camera is None:
        return False
    return camera.apply_rect(rect).colliderect(LOGICAL_SCREEN_RECT)


def find_interior_spawn_positions(
    walkable_cells: list[pygame.Rect],
    spawn_rate: float,
    *,
    player: Player | None = None,
    min_player_dist: float | None = None,
) -> list[tuple[int, int]]:
    positions = _scatter_positions_on_walkable(
        walkable_cells,
        spawn_rate,
        jitter_ratio=0.35,
    )
    if not positions and spawn_rate > 0:
        positions = _scatter_positions_on_walkable(
            walkable_cells,
            spawn_rate * 1.5,
            jitter_ratio=0.35,
        )
    if not positions:
        return []
    if player is None or min_player_dist is None or min_player_dist <= 0:
        return positions
    min_player_dist_sq = min_player_dist * min_player_dist
    filtered: list[tuple[int, int]] = []
    for pos in positions:
        dx = pos[0] - player.x
        dy = pos[1] - player.y
        if dx * dx + dy * dy < min_player_dist_sq:
            continue
        filtered.append(pos)
    return filtered


def find_nearby_offscreen_spawn_position(
    walkable_cells: list[pygame.Rect],
    *,
    player: Player | None = None,
    camera: Camera | None = None,
    min_player_dist: float | None = None,
    max_player_dist: float | None = None,
    attempts: int = 18,
) -> tuple[int, int]:
    if not walkable_cells:
        raise ValueError("walkable_cells must not be empty")
    view_rect = None
    if camera is not None:
        view_rect = pygame.Rect(
            -camera.camera.x,
            -camera.camera.y,
            SCREEN_WIDTH,
            SCREEN_HEIGHT,
        )
        view_rect.inflate_ip(SCREEN_WIDTH, SCREEN_HEIGHT)
    min_distance_sq = (
        None if min_player_dist is None else min_player_dist * min_player_dist
    )
    max_distance_sq = (
        None if max_player_dist is None else max_player_dist * max_player_dist
    )
    for _ in range(max(1, attempts)):
        cell = RNG.choice(walkable_cells)
        jitter_x = RNG.uniform(-cell.width * 0.35, cell.width * 0.35)
        jitter_y = RNG.uniform(-cell.height * 0.35, cell.height * 0.35)
        candidate = (int(cell.centerx + jitter_x), int(cell.centery + jitter_y))
        if player is not None and (min_distance_sq is not None or max_distance_sq is not None):
            dx = candidate[0] - player.x
            dy = candidate[1] - player.y
            dist_sq = dx * dx + dy * dy
            if min_distance_sq is not None and dist_sq < min_distance_sq:
                continue
            if max_distance_sq is not None and dist_sq > max_distance_sq:
                continue
        if view_rect is not None and view_rect.collidepoint(candidate):
            continue
        return candidate
    fallback_cell = RNG.choice(walkable_cells)
    fallback_x = RNG.uniform(-fallback_cell.width * 0.35, fallback_cell.width * 0.35)
    fallback_y = RNG.uniform(-fallback_cell.height * 0.35, fallback_cell.height * 0.35)
    return (
        int(fallback_cell.centerx + fallback_x),
        int(fallback_cell.centery + fallback_y),
    )


def find_exterior_spawn_position(
    level_width: int,
    level_height: int,
    *,
    hint_pos: tuple[float, float] | None = None,
    attempts: int = 5,
) -> tuple[int, int]:
    if hint_pos is None:
        return random_position_outside_building(level_width, level_height)
    points = [
        random_position_outside_building(level_width, level_height)
        for _ in range(max(1, attempts))
    ]
    return min(
        points,
        key=lambda pos: (pos[0] - hint_pos[0]) ** 2 + (pos[1] - hint_pos[1]) ** 2,
    )


def waiting_car_target_count(stage: Stage) -> int:
    return SURVIVOR_STAGE_WAITING_CAR_COUNT if stage.rescue_stage else 1


def spawn_waiting_car(game_data: GameData) -> Car | None:
    """Attempt to place an additional parked car on the map."""
    player = game_data.player
    if not player:
        return None
    walkable_cells = game_data.layout.walkable_cells
    if not walkable_cells:
        return None
    wall_group = game_data.groups.wall_group
    all_sprites = game_data.groups.all_sprites
    active_car = game_data.car if game_data.car and game_data.car.alive() else None
    waiting = alive_waiting_cars(game_data)
    obstacles: list[Car] = list(waiting)
    if active_car:
        obstacles.append(active_car)
    camera = game_data.camera
    appearance = car_appearance_for_stage(game_data.stage)
    offscreen_attempts = 6
    while offscreen_attempts > 0:
        new_car = place_new_car(
            wall_group,
            player,
            walkable_cells,
            existing_cars=obstacles,
            appearance=appearance,
        )
        if not new_car:
            return None
        if rect_visible_on_screen(camera, new_car.rect):
            offscreen_attempts -= 1
            continue
        game_data.waiting_cars.append(new_car)
        all_sprites.add(new_car, layer=1)
        return new_car
    return None


def maintain_waiting_car_supply(
    game_data: GameData, *, minimum: int | None = None
) -> None:
    """Ensure a baseline count of parked cars exists."""
    target = 1 if minimum is None else max(0, minimum)
    current = len(alive_waiting_cars(game_data))
    while current < target:
        new_car = spawn_waiting_car(game_data)
        if not new_car:
            break
        current += 1


def alive_waiting_cars(game_data: GameData) -> list[Car]:
    """Return the list of parked cars that still exist, pruning any destroyed sprites."""
    cars = [car for car in game_data.waiting_cars if car.alive()]
    game_data.waiting_cars = cars
    log_waiting_car_count(game_data)
    return cars


def log_waiting_car_count(game_data: GameData, *, force: bool = False) -> None:
    """Print the number of waiting cars when it changes."""
    current = len(game_data.waiting_cars)
    if not force and current == game_data.last_logged_waiting_cars:
        return
    game_data.last_logged_waiting_cars = current


def nearest_waiting_car(
    game_data: GameData, origin: tuple[float, float]
) -> Car | None:
    """Find the closest waiting car to an origin point."""
    cars = alive_waiting_cars(game_data)
    if not cars:
        return None
    return min(
        cars,
        key=lambda car: (car.rect.centerx - origin[0]) ** 2
        + (car.rect.centery - origin[1]) ** 2,
    )


def add_survivor_message(game_data: GameData, text: str) -> None:
    expires = pygame.time.get_ticks() + SURVIVOR_MESSAGE_DURATION_MS
    game_data.state.survivor_messages.append({"text": text, "expires_at": expires})


def random_survivor_conversion_line() -> str:
    if not SURVIVOR_CONVERSION_LINE_KEYS:
        return ""
    key = RNG.choice(SURVIVOR_CONVERSION_LINE_KEYS)
    return tr(key)


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
            angle = RNG.uniform(0, math.tau)
            dist = RNG.uniform(16, 40)
            pos = (
                origin[0] + math.cos(angle) * dist,
                origin[1] + math.sin(angle) * dist,
            )
            s = Survivor(*pos)
            if not spritecollideany_walls(s, wall_group):
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
    if not game_data.stage.rescue_stage:
        return
    survivor_group = game_data.groups.survivor_group
    if not survivor_group:
        return
    zombie_group = game_data.groups.zombie_group
    zombies = [z for z in zombie_group if z.alive()]
    if not zombies:
        return
    zombies.sort(key=lambda s: s.rect.centerx)
    zombie_xs = [z.rect.centerx for z in zombies]
    camera = game_data.camera
    walkable_cells = game_data.layout.walkable_cells

    for survivor in list(survivor_group):
        if not survivor.alive():
            continue
        survivor_radius = survivor.radius
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
        if not rect_visible_on_screen(camera, survivor.rect):
            spawn_pos = find_nearby_offscreen_spawn_position(
                walkable_cells,
                camera=camera,
            )
            survivor.teleport(spawn_pos)
            continue
        survivor.kill()
        line = random_survivor_conversion_line()
        if line:
            add_survivor_message(game_data, line)
        new_zombie = create_zombie(
            config,
            start_pos=survivor.rect.center,
            stage=game_data.stage,
            level_width=game_data.level_width,
            level_height=game_data.level_height,
        )
        zombie_group.add(new_zombie)
        game_data.groups.all_sprites.add(new_zombie, layer=1)
        insert_idx = bisect_left(zombie_xs, new_zombie.rect.centerx)
        zombie_xs.insert(insert_idx, new_zombie.rect.centerx)
        zombies.insert(insert_idx, new_zombie)


def respawn_buddies_near_player(game_data: GameData) -> None:
    """Bring back onboard buddies near the player after losing the car."""
    if game_data.stage.buddy_required_count <= 0:
        return
    count = game_data.state.buddy_onboard
    if count <= 0:
        return

    player = game_data.player
    assert player is not None
    wall_group = game_data.groups.wall_group
    camera = game_data.camera
    walkable_cells = game_data.layout.walkable_cells
    offsets = [
        (BUDDY_RADIUS * 3, 0),
        (-BUDDY_RADIUS * 3, 0),
        (0, BUDDY_RADIUS * 3),
        (0, -BUDDY_RADIUS * 3),
        (0, 0),
    ]
    for _ in range(count):
        if walkable_cells:
            spawn_pos = find_nearby_offscreen_spawn_position(
                walkable_cells,
                camera=camera,
            )
        else:
            spawn_pos = (int(player.x), int(player.y))
        for dx, dy in offsets:
            candidate = Survivor(player.x + dx, player.y + dy, is_buddy=True)
            if not spritecollideany_walls(candidate, wall_group):
                spawn_pos = (candidate.x, candidate.y)
                break

        buddy = Survivor(*spawn_pos, is_buddy=True)
        buddy.following = True
        game_data.groups.all_sprites.add(buddy, layer=2)
        game_data.groups.survivor_group.add(buddy)
    game_data.state.buddy_onboard = 0


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
        dist_sq = (
            (player.x - last_pos[0]) ** 2 + (player.y - last_pos[1]) ** 2
            if last_pos
            else None
        )
        if last_pos is None or (
            dist_sq is not None
            and dist_sq >= FOOTPRINT_STEP_DISTANCE * FOOTPRINT_STEP_DISTANCE
        ):
            footprints.append({"pos": (player.x, player.y), "time": now})
            state.last_footprint_pos = (player.x, player.y)

    if len(footprints) > FOOTPRINT_MAX:
        footprints = footprints[-FOOTPRINT_MAX:]

    state.footprints = footprints


def initialize_game_state(config: dict[str, Any], stage: Stage) -> GameData:
    """Initialize and return the base game state objects."""
    starts_with_fuel = not stage.requires_fuel
    if stage.survival_stage:
        starts_with_fuel = False
    starts_with_flashlight = False
    initial_flashlights = 1 if starts_with_flashlight else 0
    initial_palette_key = ambient_palette_key_for_flashlights(initial_flashlights)
    game_state = ProgressState(
        game_over=False,
        game_won=False,
        game_over_message=None,
        game_over_at=None,
        scaled_overview=None,
        overview_created=False,
        footprints=[],
        last_footprint_pos=None,
        elapsed_play_ms=0,
        has_fuel=starts_with_fuel,
        flashlight_count=initial_flashlights,
        ambient_palette_key=initial_palette_key,
        hint_expires_at=0,
        hint_target_type=None,
        fuel_message_until=0,
        buddy_rescued=0,
        buddy_onboard=0,
        survivors_onboard=0,
        survivors_rescued=0,
        survivor_messages=[],
        survivor_capacity=SURVIVOR_MAX_SAFE_PASSENGERS,
        seed=None,
        survival_elapsed_ms=0,
        survival_goal_ms=max(0, stage.survival_goal_ms),
        dawn_ready=False,
        dawn_prompt_at=None,
        time_accel_active=False,
        last_zombie_spawn_time=0,
        dawn_carbonized=False,
        debug_mode=False,
    )

    # Create sprite groups
    all_sprites = pygame.sprite.LayeredUpdates()
    wall_group = pygame.sprite.Group()
    zombie_group = pygame.sprite.Group()
    survivor_group = pygame.sprite.Group()

    # Create camera
    cell_size = stage.tile_size
    level_width = GRID_COLS * cell_size
    level_height = GRID_ROWS * cell_size
    camera = Camera(level_width, level_height)

    # Define level layout (will be filled by blueprint generation)
    outer_rect = 0, 0, level_width, level_height
    inner_rect = outer_rect

    return GameData(
        state=game_state,
        groups=Groups(
            all_sprites=all_sprites,
            wall_group=wall_group,
            zombie_group=zombie_group,
            survivor_group=survivor_group,
        ),
        camera=camera,
        layout=LevelLayout(
            outer_rect=outer_rect,
            inner_rect=inner_rect,
            outside_rects=[],
            walkable_cells=[],
            outer_wall_cells=set(),
        ),
        fog={
            "hatch_patterns": {},
            "overlays": {},
        },
        stage=stage,
        cell_size=cell_size,
        level_width=level_width,
        level_height=level_height,
        fuel=None,
        flashlights=[],
    )


def setup_player_and_cars(
    game_data: GameData,
    layout_data: Mapping[str, list[pygame.Rect]],
    *,
    car_count: int = 1,
) -> tuple[Player, list[Car]]:
    """Create the player plus one or more parked cars using blueprint candidates."""
    all_sprites = game_data.groups.all_sprites
    walkable_cells: list[pygame.Rect] = layout_data["walkable_cells"]

    def pick_center(cells: list[pygame.Rect]) -> tuple[int, int]:
        return (
            RNG.choice(cells).center
            if cells
            else (game_data.level_width // 2, game_data.level_height // 2)
        )

    player_pos = pick_center(layout_data["player_cells"] or walkable_cells)
    player = Player(*player_pos)

    car_candidates = list(layout_data["car_cells"] or walkable_cells)
    waiting_cars: list[Car] = []
    car_appearance = car_appearance_for_stage(game_data.stage)

    def _pick_car_position() -> tuple[int, int]:
        """Favor distant cells for the first car, otherwise fall back to random picks."""
        if not car_candidates:
            return (player_pos[0] + 200, player_pos[1])
        RNG.shuffle(car_candidates)
        for candidate in car_candidates:
            if (
                (candidate.centerx - player_pos[0]) ** 2
                + (candidate.centery - player_pos[1]) ** 2
                >= 400 * 400
            ):
                car_candidates.remove(candidate)
                return candidate.center
        # No far-enough cells found; pick the first available
        choice = car_candidates.pop()
        return choice.center

    for idx in range(max(1, car_count)):
        car_pos = _pick_car_position()
        car = Car(*car_pos, appearance=car_appearance)
        waiting_cars.append(car)
        all_sprites.add(car, layer=1)
        if not car_candidates:
            break

    all_sprites.add(player, layer=2)
    return player, waiting_cars


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

    spawn_rate = max(0.0, getattr(game_data.stage, "initial_interior_spawn_rate", 0.0))
    positions = find_interior_spawn_positions(
        spawn_cells,
        spawn_rate,
        player=player,
        min_player_dist=ZOMBIE_SPAWN_PLAYER_BUFFER,
    )

    for pos in positions:
        tentative = create_zombie(
            config,
            start_pos=pos,
            stage=game_data.stage,
            level_width=game_data.level_width,
            level_height=game_data.level_height,
        )
        if spritecollideany_walls(tentative, wall_group):
            continue
        zombie_group.add(tentative)
        all_sprites.add(tentative, layer=1)

    interval = max(1, getattr(game_data.stage, "spawn_interval_ms", ZOMBIE_SPAWN_DELAY_MS))
    game_data.state.last_zombie_spawn_time = pygame.time.get_ticks() - interval


def spawn_nearby_zombie(
    game_data: GameData,
    config: dict[str, Any],
) -> Zombie | None:
    """Spawn a zombie just outside of the current camera frustum."""
    player = game_data.player
    if not player:
        return None
    zombie_group = game_data.groups.zombie_group
    if len(zombie_group) >= MAX_ZOMBIES:
        return None
    camera = game_data.camera
    wall_group = game_data.groups.wall_group
    all_sprites = game_data.groups.all_sprites
    spawn_pos = find_nearby_offscreen_spawn_position(
        game_data.layout.walkable_cells,
        player=player,
        camera=camera,
        min_player_dist=SURVIVAL_NEAR_SPAWN_MIN_DISTANCE,
        max_player_dist=SURVIVAL_NEAR_SPAWN_MAX_DISTANCE,
    )
    new_zombie = create_zombie(
        config,
        start_pos=spawn_pos,
        stage=game_data.stage,
        level_width=game_data.level_width,
        level_height=game_data.level_height,
    )
    if spritecollideany_walls(new_zombie, wall_group):
        return None
    zombie_group.add(new_zombie)
    all_sprites.add(new_zombie, layer=1)
    return new_zombie


def spawn_exterior_zombie(
    game_data: GameData,
    config: dict[str, Any],
) -> Zombie | None:
    """Spawn a zombie using the standard exterior hint logic."""
    player = game_data.player
    if not player:
        return None
    zombie_group = game_data.groups.zombie_group
    all_sprites = game_data.groups.all_sprites
    spawn_pos = find_exterior_spawn_position(
        game_data.level_width,
        game_data.level_height,
        hint_pos=(player.x, player.y),
    )
    new_zombie = create_zombie(
        config,
        start_pos=spawn_pos,
        stage=game_data.stage,
        level_width=game_data.level_width,
        level_height=game_data.level_height,
    )
    zombie_group.add(new_zombie)
    all_sprites.add(new_zombie, layer=1)
    return new_zombie


def spawn_weighted_zombie(
    game_data: GameData,
    config: dict[str, Any],
) -> bool:
    """Spawn a zombie according to the stage's interior/exterior mix."""
    stage = game_data.stage
    def _spawn(choice: str) -> bool:
        if choice == "interior":
            return spawn_nearby_zombie(game_data, config) is not None
        return spawn_exterior_zombie(game_data, config) is not None

    interior_weight = max(0.0, stage.interior_spawn_weight)
    exterior_weight = max(0.0, stage.exterior_spawn_weight)
    total_weight = interior_weight + exterior_weight
    if total_weight <= 0:
        # Fall back to exterior spawns if weights are unset or invalid.
        return _spawn("exterior")

    pick = RNG.uniform(0, total_weight)
    if pick <= interior_weight:
        if _spawn("interior"):
            return True
        return _spawn("exterior")
    if _spawn("exterior"):
        return True
    return _spawn("interior")


def carbonize_outdoor_zombies(game_data: GameData) -> None:
    """Petrify zombies that have already broken through to the exterior."""
    outside_rects = game_data.layout.outside_rects or []
    if not outside_rects:
        return
    group = game_data.groups.zombie_group
    if not group:
        return
    for zombie in list(group):
        alive = getattr(zombie, "alive", lambda: False)
        if not alive():
            continue
        center = zombie.rect.center
        if any(rect_obj.collidepoint(center) for rect_obj in outside_rects):
            carbonize = getattr(zombie, "carbonize", None)
            if carbonize:
                carbonize()


def update_survival_timer(game_data: GameData, dt_ms: int) -> None:
    """Advance the survival countdown and trigger dawn handoff."""
    stage = game_data.stage
    state = game_data.state
    if not stage.survival_stage:
        return
    if state.survival_goal_ms <= 0 or dt_ms <= 0:
        return
    state.survival_elapsed_ms = min(
        state.survival_goal_ms,
        state.survival_elapsed_ms + dt_ms,
    )
    if not state.dawn_ready and state.survival_elapsed_ms >= state.survival_goal_ms:
        state.dawn_ready = True
        state.dawn_prompt_at = pygame.time.get_ticks()
        set_ambient_palette(game_data, DAWN_AMBIENT_PALETTE_KEY, force=True)
    if state.dawn_ready:
        carbonize_outdoor_zombies(game_data)
        state.dawn_carbonized = True


def process_player_input(
    keys: Sequence[bool], player: Player, car: Car | None
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

    if player.in_car and car and car.alive():
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
    wall_index: WallIndex | None = None,
) -> None:
    """Update positions and states of game entities."""
    player = game_data.player
    assert player is not None
    car = game_data.car
    wall_group = game_data.groups.wall_group
    all_sprites = game_data.groups.all_sprites
    zombie_group = game_data.groups.zombie_group
    survivor_group = game_data.groups.survivor_group
    camera = game_data.camera
    stage = game_data.stage
    active_car = car if car and car.alive() else None

    all_walls = list(wall_group) if wall_index is None else None

    def walls_near(center: tuple[float, float], radius: float) -> list[Wall]:
        if wall_index is None:
            return all_walls or []
        return walls_for_radius(wall_index, center, radius, cell_size=game_data.cell_size)

    # Update player/car movement
    if player.in_car and active_car:
        car_walls = walls_near((active_car.x, active_car.y), 150.0)
        active_car.move(car_dx, car_dy, car_walls)
        player.rect.center = active_car.rect.center
        player.x, player.y = active_car.x, active_car.y
    elif not player.in_car:
        # Ensure player is in all_sprites if not in car
        if player not in all_sprites:
            all_sprites.add(player, layer=2)
        player.move(
            player_dx,
            player_dy,
            wall_group,
            wall_index=wall_index,
            cell_size=game_data.cell_size,
            level_width=game_data.level_width,
            level_height=game_data.level_height,
        )
    else:
        # Player flagged as in-car but car is gone; drop them back to foot control
        player.in_car = False

    # Update camera
    target_for_camera = active_car if player.in_car and active_car else player
    camera.update(target_for_camera)

    update_survivors(game_data, wall_index=wall_index)

    # Spawn new zombies if needed
    current_time = pygame.time.get_ticks()
    spawn_interval = max(1, getattr(stage, "spawn_interval_ms", ZOMBIE_SPAWN_DELAY_MS))
    spawn_blocked = stage.survival_stage and game_data.state.dawn_ready
    if (
        len(zombie_group) < MAX_ZOMBIES
        and not spawn_blocked
        and current_time - game_data.state.last_zombie_spawn_time > spawn_interval
    ):
        if spawn_weighted_zombie(game_data, config):
            game_data.state.last_zombie_spawn_time = current_time

    # Update zombies
    target_center = (
        active_car.rect.center if player.in_car and active_car else player.rect.center
    )
    buddies = [
        survivor
        for survivor in survivor_group
        if survivor.alive() and survivor.is_buddy and not survivor.rescued
    ]
    buddies_on_screen = [
        buddy for buddy in buddies if rect_visible_on_screen(camera, buddy.rect)
    ]

    survivors_on_screen: list[Survivor] = []
    if stage.rescue_stage:
        for survivor in survivor_group:
            if survivor.alive():
                if rect_visible_on_screen(camera, survivor.rect):
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
        if buddies_on_screen:
            dist_to_target_sq = (target_center[0] - zombie.x) ** 2 + (
                target_center[1] - zombie.y
            ) ** 2
            nearest_buddy = min(
                buddies_on_screen,
                key=lambda buddy: (buddy.rect.centerx - zombie.x) ** 2
                + (buddy.rect.centery - zombie.y) ** 2,
            )
            dist_to_buddy_sq = (nearest_buddy.rect.centerx - zombie.x) ** 2 + (
                nearest_buddy.rect.centery - zombie.y
            ) ** 2
            if dist_to_buddy_sq < dist_to_target_sq:
                target = nearest_buddy.rect.center

        if stage.rescue_stage:
            zombie_on_screen = rect_visible_on_screen(camera, zombie.rect)
            if zombie_on_screen:
                candidate_positions: list[tuple[int, int]] = []
                for survivor in survivors_on_screen:
                    candidate_positions.append(survivor.rect.center)
                for buddy in buddies_on_screen:
                    candidate_positions.append(buddy.rect.center)
                candidate_positions.append(player.rect.center)
                if candidate_positions:
                    target = min(
                        candidate_positions,
                        key=lambda pos: (pos[0] - zombie.x) ** 2
                        + (pos[1] - zombie.y) ** 2,
                    )
        nearby_candidates = _nearby_zombies(idx)
        zombie_search_radius = ZOMBIE_WALL_FOLLOW_SENSOR_DISTANCE + zombie.radius + 120
        nearby_walls = walls_near((zombie.x, zombie.y), zombie_search_radius)
        zombie.update(
            target,
            nearby_walls,
            nearby_candidates,
            footprints=game_data.state.footprints,
            cell_size=game_data.cell_size,
            level_width=game_data.level_width,
            level_height=game_data.level_height,
            outer_wall_cells=game_data.layout.outer_wall_cells,
        )


def check_interactions(
    game_data: GameData, config: dict[str, Any]
) -> pygame.sprite.Sprite | None:
    """Check and handle interactions between entities."""
    player = game_data.player
    assert player is not None
    car = game_data.car
    zombie_group = game_data.groups.zombie_group
    all_sprites = game_data.groups.all_sprites
    survivor_group = game_data.groups.survivor_group
    state = game_data.state
    walkable_cells = game_data.layout.walkable_cells
    outside_rects = game_data.layout.outside_rects
    fuel = game_data.fuel
    flashlights = game_data.flashlights or []
    camera = game_data.camera
    stage = game_data.stage
    maintain_waiting_car_supply(game_data)
    active_car = car if car and car.alive() else None
    waiting_cars = game_data.waiting_cars
    shrunk_car = get_shrunk_sprite(active_car, 0.8) if active_car else None

    car_interaction_radius = interaction_radius(CAR_WIDTH, CAR_HEIGHT)
    fuel_interaction_radius = interaction_radius(FUEL_CAN_WIDTH, FUEL_CAN_HEIGHT)
    flashlight_interaction_radius = interaction_radius(
        FLASHLIGHT_WIDTH, FLASHLIGHT_HEIGHT
    )

    def player_near_point(point: tuple[float, float], radius: float) -> bool:
        dx = point[0] - player.x
        dy = point[1] - player.y
        return dx * dx + dy * dy <= radius * radius

    def player_near_sprite(
        sprite_obj: pygame.sprite.Sprite | None, radius: float
    ) -> bool:
        return bool(
            sprite_obj
            and sprite_obj.alive()
            and player_near_point(sprite_obj.rect.center, radius)
        )

    def player_near_car(car_obj: Car | None) -> bool:
        return player_near_sprite(car_obj, car_interaction_radius)

    # Fuel pickup
    if fuel and fuel.alive() and not state.has_fuel and not player.in_car:
        if player_near_point(fuel.rect.center, fuel_interaction_radius):
            state.has_fuel = True
            state.fuel_message_until = 0
            state.hint_expires_at = 0
            state.hint_target_type = None
            fuel.kill()
            game_data.fuel = None
            print("Fuel acquired!")

    # Flashlight pickup
    if not player.in_car:
        for flashlight in list(flashlights):
            if not flashlight.alive():
                continue
            if player_near_point(
                flashlight.rect.center, flashlight_interaction_radius
            ):
                state.flashlight_count += 1
                state.hint_expires_at = 0
                state.hint_target_type = None
                flashlight.kill()
                try:
                    flashlights.remove(flashlight)
                except ValueError:
                    pass
                print("Flashlight acquired!")
                break

    sync_ambient_palette_with_flashlights(game_data)

    buddies = [
        survivor
        for survivor in survivor_group
        if survivor.alive() and survivor.is_buddy and not survivor.rescued
    ]

    # Buddy interactions (Stage 3)
    if stage.buddy_required_count > 0 and buddies:
        for buddy in list(buddies):
            if not buddy.alive():
                continue
            buddy_on_screen = rect_visible_on_screen(camera, buddy.rect)
            if not player.in_car:
                dist_to_player_sq = (player.x - buddy.x) ** 2 + (
                    player.y - buddy.y
                ) ** 2
                if (
                    dist_to_player_sq
                    <= SURVIVOR_APPROACH_RADIUS * SURVIVOR_APPROACH_RADIUS
                ):
                    buddy.set_following()
            elif player.in_car and active_car and shrunk_car:
                g = pygame.sprite.Group()
                g.add(buddy)
                if pygame.sprite.spritecollide(
                    shrunk_car, g, False, pygame.sprite.collide_circle
                ):
                    prospective_passengers = state.survivors_onboard + 1
                    capacity_limit = state.survivor_capacity
                    if prospective_passengers > capacity_limit:
                        overload_damage = max(
                            1,
                            int(active_car.max_health * SURVIVOR_OVERLOAD_DAMAGE_RATIO),
                        )
                        add_survivor_message(game_data, tr("survivors.too_many_aboard"))
                        active_car.take_damage(overload_damage)
                    state.buddy_onboard += 1
                    buddy.kill()
                    continue

            if buddy.alive() and pygame.sprite.spritecollide(
                buddy, zombie_group, False, pygame.sprite.collide_circle
            ):
                if buddy_on_screen:
                    state.game_over_message = tr("game_over.scream")
                    state.game_over = True
                    state.game_over_at = state.game_over_at or pygame.time.get_ticks()
                else:
                    if walkable_cells:
                        new_cell = RNG.choice(walkable_cells)
                        buddy.teleport(new_cell.center)
                    else:
                        buddy.teleport(
                            (game_data.level_width // 2, game_data.level_height // 2)
                        )
                    buddy.following = False

    # Player entering an active car already under control
    if (
        not player.in_car
        and player_near_car(active_car)
        and active_car
        and active_car.health > 0
    ):
        if state.has_fuel:
            player.in_car = True
            all_sprites.remove(player)
            state.hint_expires_at = 0
            state.hint_target_type = None
            print("Player entered car!")
        else:
            if not stage.survival_stage:
                now_ms = state.elapsed_play_ms
                state.fuel_message_until = now_ms + FUEL_HINT_DURATION_MS
                state.hint_target_type = "fuel"

    # Claim a waiting/parked car when the player finally reaches it
    if not player.in_car and not active_car and waiting_cars:
        claimed_car: Car | None = None
        for parked_car in waiting_cars:
            if player_near_car(parked_car):
                claimed_car = parked_car
                break
        if claimed_car:
            if state.has_fuel:
                try:
                    game_data.waiting_cars.remove(claimed_car)
                except ValueError:
                    pass
                game_data.car = claimed_car
                active_car = claimed_car
                player.in_car = True
                all_sprites.remove(player)
                state.hint_expires_at = 0
                state.hint_target_type = None
                apply_passenger_speed_penalty(game_data)
                maintain_waiting_car_supply(game_data)
                print("Player claimed a waiting car!")
            else:
                if not stage.survival_stage:
                    now_ms = state.elapsed_play_ms
                    state.fuel_message_until = now_ms + FUEL_HINT_DURATION_MS
                    state.hint_target_type = "fuel"

    # Bonus: collide a parked car while driving to repair/extend capabilities
    if player.in_car and active_car and shrunk_car and waiting_cars:
        waiting_group = pygame.sprite.Group(waiting_cars)
        collided_waiters = pygame.sprite.spritecollide(
            shrunk_car, waiting_group, False, pygame.sprite.collide_rect
        )
        if collided_waiters:
            removed_any = False
            capacity_increments = 0
            for parked in collided_waiters:
                if not parked.alive():
                    continue
                parked.kill()
                try:
                    game_data.waiting_cars.remove(parked)
                except ValueError:
                    pass
                active_car.health = active_car.max_health
                active_car.update_color()
                removed_any = True
                if stage.rescue_stage:
                    capacity_increments += 1
            if removed_any:
                if capacity_increments:
                    increase_survivor_capacity(game_data, capacity_increments)
                maintain_waiting_car_supply(game_data)

    # Car hitting zombies
    if player.in_car and active_car and active_car.health > 0 and shrunk_car:
        zombies_hit = pygame.sprite.spritecollide(shrunk_car, zombie_group, True)
        if zombies_hit:
            active_car.take_damage(CAR_ZOMBIE_DAMAGE * len(zombies_hit))

    if (
        stage.rescue_stage
        and player.in_car
        and active_car
        and shrunk_car
        and survivor_group
    ):
        boarded = pygame.sprite.spritecollide(
            shrunk_car, survivor_group, True, pygame.sprite.collide_circle
        )
        if boarded:
            state.survivors_onboard += len(boarded)
            apply_passenger_speed_penalty(game_data)
            capacity_limit = state.survivor_capacity
            if state.survivors_onboard > capacity_limit:
                overload_damage = max(
                    1,
                    int(active_car.max_health * SURVIVOR_OVERLOAD_DAMAGE_RATIO),
                )
                add_survivor_message(game_data, tr("survivors.too_many_aboard"))
                active_car.take_damage(overload_damage)

    if stage.rescue_stage:
        handle_survivor_zombie_collisions(game_data, config)

    # Handle car destruction
    if car and car.alive() and car.health <= 0:
        car_destroyed_pos = car.rect.center
        car.kill()
        if stage.rescue_stage:
            drop_survivors_from_car(game_data, car_destroyed_pos)
        if player.in_car:
            player.in_car = False
            player.x, player.y = car_destroyed_pos[0], car_destroyed_pos[1]
            player.rect.center = (int(player.x), int(player.y))
            if player not in all_sprites:
                all_sprites.add(player, layer=2)
            print("Car destroyed! Player ejected.")

        # Clear active car and let the player hunt for another waiting car.
        game_data.car = None
        state.survivor_capacity = SURVIVOR_MAX_SAFE_PASSENGERS
        apply_passenger_speed_penalty(game_data)

        # Bring back the buddies near the player after losing the car
        respawn_buddies_near_player(game_data)
        maintain_waiting_car_supply(game_data)

    # Player getting caught by zombies
    if not player.in_car and player in all_sprites:
        shrunk_player = get_shrunk_sprite(player, 0.8)
        if pygame.sprite.spritecollide(
            shrunk_player, zombie_group, False, pygame.sprite.collide_circle
        ):
            if not state.game_over:
                state.game_over = True
                state.game_over_at = pygame.time.get_ticks()
                state.game_over_message = tr("game_over.scream")

    # Player escaping on foot after dawn (Stage 5)
    if (
        stage.survival_stage
        and state.dawn_ready
        and not player.in_car
        and outside_rects
        and any(outside.collidepoint(player.rect.center) for outside in outside_rects)
    ):
        state.game_won = True

    # Player escaping the level
    if player.in_car and car and car.alive() and state.has_fuel:
        buddies_following = [
            survivor
            for survivor in survivor_group
            if survivor.alive()
            and survivor.is_buddy
            and survivor.following
            and not survivor.rescued
        ]
        buddy_ready = True
        if stage.buddy_required_count > 0:
            total_ready = (
                state.buddy_rescued + state.buddy_onboard + len(buddies_following)
            )
            buddy_ready = total_ready >= stage.buddy_required_count
        if buddy_ready and any(
            outside.collidepoint(car.rect.center) for outside in outside_rects
        ):
            if stage.buddy_required_count > 0:
                rescued_now = state.buddy_onboard + len(buddies_following)
                state.buddy_rescued = min(
                    stage.buddy_required_count,
                    state.buddy_rescued + rescued_now,
                )
                state.buddy_onboard = 0
                for buddy in buddies_following:
                    buddy.mark_rescued()
            if stage.rescue_stage and state.survivors_onboard:
                state.survivors_rescued += state.survivors_onboard
                state.survivors_onboard = 0
                state.next_overload_check_ms = 0
                apply_passenger_speed_penalty(game_data)
            state.game_won = True

    # Return fog of view target
    if not state.game_over and not state.game_won:
        return car if player.in_car and car and car.alive() else player
    return None


def set_ambient_palette(
    game_data: GameData, key: str, *, force: bool = False
) -> None:
    """Apply a named ambient palette to all walls in the level."""

    palette = get_environment_palette(key)
    state = game_data.state
    if not force and state.ambient_palette_key == key:
        return

    state.ambient_palette_key = key
    _apply_palette_to_walls(game_data, palette, force=True)


def sync_ambient_palette_with_flashlights(
    game_data: GameData, *, force: bool = False
) -> None:
    """Sync the ambient palette with the player's flashlight inventory."""

    state = game_data.state
    if state.dawn_ready:
        set_ambient_palette(game_data, DAWN_AMBIENT_PALETTE_KEY, force=force)
        return
    key = ambient_palette_key_for_flashlights(state.flashlight_count)
    set_ambient_palette(game_data, key, force=force)


def _apply_palette_to_walls(
    game_data: GameData,
    palette,
    *,
    force: bool = False,
) -> None:
    if not hasattr(game_data, "groups") or not hasattr(game_data.groups, "wall_group"):
        return
    wall_group = game_data.groups.wall_group
    for wall in wall_group:
        if not hasattr(wall, "set_palette_colors"):
            continue
        category = getattr(wall, "palette_category", "inner_wall")
        if category == "outer_wall":
            color = palette.outer_wall
            border_color = palette.outer_wall_border
        else:
            color = palette.inner_wall
            border_color = palette.inner_wall_border
        wall.set_palette_colors(color=color, border_color=border_color, force=force)
