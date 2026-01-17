from __future__ import annotations

from typing import Any, Mapping, Sequence

import pygame

from ..entities import (
    Car,
    Flashlight,
    FuelCan,
    Player,
    Survivor,
    Zombie,
    random_position_outside_building,
    spritecollideany_walls,
)
from ..entities_constants import (
    FAST_ZOMBIE_BASE_SPEED,
    PLAYER_SPEED,
    ZOMBIE_AGING_DURATION_FRAMES,
    ZOMBIE_SPEED,
)
from ..gameplay_constants import DEFAULT_FLASHLIGHT_SPAWN_COUNT, ZOMBIE_SPAWN_DELAY_MS
from .constants import (
    MAX_ZOMBIES,
    SURVIVAL_NEAR_SPAWN_MAX_DISTANCE,
    SURVIVAL_NEAR_SPAWN_MIN_DISTANCE,
    ZOMBIE_SPAWN_PLAYER_BUFFER,
    ZOMBIE_TRACKER_AGING_DURATION_FRAMES,
)
from ..level_constants import GRID_COLS, GRID_ROWS, TILE_SIZE
from ..models import GameData, Stage
from ..rng import get_rng
from .utils import (
    find_exterior_spawn_position,
    find_interior_spawn_positions,
    find_nearby_offscreen_spawn_position,
    rect_visible_on_screen,
)

RNG = get_rng()

__all__ = [
    "car_appearance_for_stage",
    "create_zombie",
    "place_new_car",
    "place_fuel_can",
    "place_flashlight",
    "place_flashlights",
    "place_buddies",
    "spawn_survivors",
    "setup_player_and_cars",
    "spawn_initial_zombies",
    "spawn_waiting_car",
    "maintain_waiting_car_supply",
    "alive_waiting_cars",
    "log_waiting_car_count",
    "nearest_waiting_car",
    "spawn_nearby_zombie",
    "spawn_exterior_zombie",
    "spawn_weighted_zombie",
]


def car_appearance_for_stage(stage: Stage | None) -> str:
    return "disabled" if stage and stage.survival_stage else "default"


def create_zombie(
    config: dict[str, Any],
    *,
    start_pos: tuple[int, int] | None = None,
    hint_pos: tuple[float, float] | None = None,
    stage: Stage | None = None,
    tracker: bool | None = None,
    wall_follower: bool | None = None,
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
    if start_pos is None:
        tile_size = getattr(stage, "tile_size", TILE_SIZE) if stage else TILE_SIZE
        level_width = GRID_COLS * tile_size
        level_height = GRID_ROWS * tile_size
        if hint_pos is not None:
            points = [
                random_position_outside_building(level_width, level_height)
                for _ in range(5)
            ]
            points.sort(
                key=lambda p: (p[0] - hint_pos[0]) ** 2 + (p[1] - hint_pos[1]) ** 2
            )
            start_pos = points[0]
        else:
            start_pos = random_position_outside_building(level_width, level_height)
    return Zombie(
        x=float(start_pos[0]),
        y=float(start_pos[1]),
        speed=base_speed,
        tracker=tracker,
        wall_follower=wall_follower,
        aging_duration_frames=aging_duration_frames,
    )


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

    for _ in range(200):
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

    for _ in range(200):
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
    for _ in range(max_attempts):
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
            survivor = Survivor(*pos)
            if spritecollideany_walls(survivor, wall_group):
                continue
            survivor_group.add(survivor)
            all_sprites.add(survivor, layer=1)
            survivors.append(survivor)

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
        choice = car_candidates.pop()
        return choice.center

    for _ in range(max(1, car_count)):
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
        )
        if spritecollideany_walls(tentative, wall_group):
            continue
        zombie_group.add(tentative)
        all_sprites.add(tentative, layer=1)

    interval = max(1, getattr(game_data.stage, "spawn_interval_ms", ZOMBIE_SPAWN_DELAY_MS))
    game_data.state.last_zombie_spawn_time = pygame.time.get_ticks() - interval


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
        attempts=50,
    )
    new_zombie = create_zombie(
        config,
        start_pos=spawn_pos,
        stage=game_data.stage,
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
