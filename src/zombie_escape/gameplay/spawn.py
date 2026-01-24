from __future__ import annotations

from typing import Any, Callable, Literal, Mapping, Sequence

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
    FOV_RADIUS,
    PLAYER_SPEED,
    ZOMBIE_AGING_DURATION_FRAMES,
    ZOMBIE_SPEED,
)
from ..gameplay_constants import DEFAULT_FLASHLIGHT_SPAWN_COUNT
from ..level_constants import DEFAULT_GRID_COLS, DEFAULT_GRID_ROWS, DEFAULT_TILE_SIZE
from ..models import DustRing, FallingZombie, GameData, Stage
from ..render_constants import FLASHLIGHT_FOG_SCALE_STEP, FOG_RADIUS_SCALE
from ..rng import get_rng
from .constants import (
    MAX_ZOMBIES,
    ZOMBIE_SPAWN_PLAYER_BUFFER,
    ZOMBIE_TRACKER_AGING_DURATION_FRAMES,
)
from .utils import (
    find_exterior_spawn_position,
    find_interior_spawn_positions,
    find_nearby_offscreen_spawn_position,
    rect_visible_on_screen,
)

RNG = get_rng()

FallScheduleResult = Literal["scheduled", "no_position", "blocked", "no_player"]

__all__ = [
    "place_new_car",
    "place_fuel_can",
    "place_flashlights",
    "place_buddies",
    "spawn_survivors",
    "setup_player_and_cars",
    "spawn_initial_zombies",
    "spawn_waiting_car",
    "maintain_waiting_car_supply",
    "nearest_waiting_car",
    "update_falling_zombies",
    "spawn_exterior_zombie",
    "spawn_weighted_zombie",
]


def _car_appearance_for_stage(stage: Stage | None) -> str:
    return "disabled" if stage and stage.endurance_stage else "default"


def _pick_zombie_variant(stage: Stage | None) -> tuple[bool, bool]:
    normal_ratio = 1.0
    tracker_ratio = 0.0
    wall_follower_ratio = 0.0
    if stage is not None:
        normal_ratio = max(0.0, min(1.0, stage.zombie_normal_ratio))
        tracker_ratio = max(0.0, min(1.0, stage.zombie_tracker_ratio))
        wall_follower_ratio = max(0.0, min(1.0, stage.zombie_wall_follower_ratio))
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
    total_ratio = normal_ratio + tracker_ratio + wall_follower_ratio
    if total_ratio <= 0:
        return False, False
    pick = RNG.random() * total_ratio
    if pick < normal_ratio:
        return False, False
    if pick < normal_ratio + tracker_ratio:
        return True, False
    return False, True


def _fov_radius_for_flashlights(flashlight_count: int) -> float:
    count = max(0, int(flashlight_count))
    scale = FOG_RADIUS_SCALE + max(0.0, FLASHLIGHT_FOG_SCALE_STEP) * count
    return FOV_RADIUS * scale


def _is_spawn_position_clear(
    game_data: GameData,
    candidate: Zombie,
    *,
    allow_player_overlap: bool = False,
) -> bool:
    wall_group = game_data.groups.wall_group
    if spritecollideany_walls(candidate, wall_group):
        return False

    spawn_rect = candidate.rect
    player = game_data.player
    if not allow_player_overlap and player and spawn_rect.colliderect(player.rect):
        return False
    car = game_data.car
    if car and car.alive() and spawn_rect.colliderect(car.rect):
        return False
    for parked in game_data.waiting_cars:
        if parked.alive() and spawn_rect.colliderect(parked.rect):
            return False
    for survivor in game_data.groups.survivor_group:
        if survivor.alive() and spawn_rect.colliderect(survivor.rect):
            return False
    for zombie in game_data.groups.zombie_group:
        if zombie.alive() and spawn_rect.colliderect(zombie.rect):
            return False
    return True


def _pick_fall_spawn_position(
    game_data: GameData,
    *,
    min_distance: float,
    attempts: int = 10,
    is_clear: Callable[[tuple[int, int]], bool] | None = None,
) -> tuple[int, int] | None:
    player = game_data.player
    if not player:
        return None
    fall_spawn_cells = game_data.layout.fall_spawn_cells
    if not fall_spawn_cells:
        return None
    car = game_data.car
    target_sprite = car if player.in_car and car and car.alive() else player
    target_center = target_sprite.rect.center
    cell_size = game_data.cell_size
    fov_radius = _fov_radius_for_flashlights(game_data.state.flashlight_count)
    min_dist_sq = min_distance * min_distance
    max_dist_sq = fov_radius * fov_radius
    wall_cells = game_data.layout.wall_cells

    candidates: list[tuple[int, int]] = []
    for cell_x, cell_y in fall_spawn_cells:
        if (cell_x, cell_y) in wall_cells:
            continue
        pos = (
            int(cell_x * cell_size + cell_size // 2),
            int(cell_y * cell_size + cell_size // 2),
        )
        dx = pos[0] - target_center[0]
        dy = pos[1] - target_center[1]
        dist_sq = dx * dx + dy * dy
        if dist_sq < min_dist_sq or dist_sq > max_dist_sq:
            continue
        candidates.append(pos)

    if not candidates:
        return None

    RNG.shuffle(candidates)
    for pos in candidates[: max(1, min(attempts, len(candidates)))]:
        if is_clear is not None and not is_clear(pos):
            continue
        return pos
    return None


def _schedule_falling_zombie(
    game_data: GameData,
    config: dict[str, Any],
    *,
    allow_carry: bool = True,
) -> FallScheduleResult:
    player = game_data.player
    if not player:
        return "no_player"
    state = game_data.state
    zombie_group = game_data.groups.zombie_group
    if len(zombie_group) + len(state.falling_zombies) >= MAX_ZOMBIES:
        return "blocked"
    min_distance = game_data.stage.tile_size * 0.5
    tracker, wall_follower = _pick_zombie_variant(game_data.stage)

    def _candidate_clear(pos: tuple[int, int]) -> bool:
        candidate = _create_zombie(
            config,
            start_pos=pos,
            stage=game_data.stage,
            tracker=tracker,
            wall_follower=wall_follower,
        )
        return _is_spawn_position_clear(game_data, candidate)

    spawn_pos = _pick_fall_spawn_position(
        game_data,
        min_distance=min_distance,
        is_clear=_candidate_clear,
    )
    if spawn_pos is None:
        if allow_carry:
            state.falling_spawn_carry += 1
        return "no_position"
    start_offset = game_data.stage.tile_size * 0.7
    start_pos = (int(spawn_pos[0]), int(spawn_pos[1] - start_offset))
    fall = FallingZombie(
        start_pos=start_pos,
        target_pos=(int(spawn_pos[0]), int(spawn_pos[1])),
        started_at_ms=pygame.time.get_ticks(),
        pre_fx_ms=350,
        fall_duration_ms=450,
        dust_duration_ms=220,
        tracker=tracker,
        wall_follower=wall_follower,
    )
    state.falling_zombies.append(fall)
    return "scheduled"


def _create_zombie(
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
    if stage is not None:
        aging_duration_frames = max(
            1.0,
            float(stage.zombie_aging_duration_frames),
        )
    else:
        aging_duration_frames = ZOMBIE_AGING_DURATION_FRAMES
    if tracker is None or wall_follower is None:
        picked_tracker, picked_wall_follower = _pick_zombie_variant(stage)
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
        tile_size = stage.tile_size if stage else DEFAULT_TILE_SIZE
        if stage is None:
            grid_cols = DEFAULT_GRID_COLS
            grid_rows = DEFAULT_GRID_ROWS
        else:
            grid_cols = stage.grid_cols
            grid_rows = stage.grid_rows
        level_width = grid_cols * tile_size
        level_height = grid_rows * tile_size
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


def _place_flashlight(
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
        fl = _place_flashlight(walkable_cells, player, cars=cars)
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

    def _pick_center(cells: list[pygame.Rect]) -> tuple[int, int]:
        return (
            RNG.choice(cells).center
            if cells
            else (game_data.level_width // 2, game_data.level_height // 2)
        )

    player_pos = _pick_center(layout_data["player_cells"] or walkable_cells)
    player = Player(*player_pos)

    car_candidates = list(layout_data["car_cells"] or walkable_cells)
    waiting_cars: list[Car] = []
    car_appearance = _car_appearance_for_stage(game_data.stage)

    def _pick_car_position() -> tuple[int, int]:
        """Favor distant cells for the first car, otherwise fall back to random picks."""
        if not car_candidates:
            return (player_pos[0] + 200, player_pos[1])
        RNG.shuffle(car_candidates)
        for candidate in car_candidates:
            if (candidate.centerx - player_pos[0]) ** 2 + (
                candidate.centery - player_pos[1]
            ) ** 2 >= 400 * 400:
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

    if game_data.stage.id == "debug_tracker":
        player_pos = player.rect.center
        min_dist_sq = 100 * 100
        max_dist_sq = 240 * 240
        candidates = [
            cell
            for cell in spawn_cells
            if min_dist_sq
            <= (cell.centerx - player_pos[0]) ** 2 + (cell.centery - player_pos[1]) ** 2
            <= max_dist_sq
        ]
        if not candidates:
            candidates = spawn_cells
        candidate = RNG.choice(candidates)
        tentative = _create_zombie(
            config,
            start_pos=candidate.center,
            stage=game_data.stage,
            tracker=True,
            wall_follower=False,
        )
        if not spritecollideany_walls(tentative, wall_group):
            zombie_group.add(tentative)
            all_sprites.add(tentative, layer=1)
        interval = max(1, game_data.stage.spawn_interval_ms)
        game_data.state.last_zombie_spawn_time = pygame.time.get_ticks() - interval
        return

    spawn_rate = max(0.0, game_data.stage.initial_interior_spawn_rate)
    positions = find_interior_spawn_positions(
        spawn_cells,
        spawn_rate,
        player=player,
        min_player_dist=ZOMBIE_SPAWN_PLAYER_BUFFER,
    )

    for pos in positions:
        tracker, wall_follower = _pick_zombie_variant(game_data.stage)
        tentative = _create_zombie(
            config,
            start_pos=pos,
            stage=game_data.stage,
            tracker=tracker,
            wall_follower=wall_follower,
        )
        if spritecollideany_walls(tentative, wall_group):
            continue
        zombie_group.add(tentative)
        all_sprites.add(tentative, layer=1)

    interval = max(1, game_data.stage.spawn_interval_ms)
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
    waiting = _alive_waiting_cars(game_data)
    obstacles: list[Car] = list(waiting)
    if active_car:
        obstacles.append(active_car)
    camera = game_data.camera
    appearance = _car_appearance_for_stage(game_data.stage)
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
    current = len(_alive_waiting_cars(game_data))
    while current < target:
        new_car = spawn_waiting_car(game_data)
        if not new_car:
            break
        current += 1


def _alive_waiting_cars(game_data: GameData) -> list[Car]:
    """Return the list of parked cars that still exist, pruning any destroyed sprites."""
    cars = [car for car in game_data.waiting_cars if car.alive()]
    game_data.waiting_cars = cars
    _log_waiting_car_count(game_data)
    return cars


def _log_waiting_car_count(game_data: GameData, *, force: bool = False) -> None:
    """Print the number of waiting cars when it changes."""
    current = len(game_data.waiting_cars)
    if not force and current == game_data.last_logged_waiting_cars:
        return
    game_data.last_logged_waiting_cars = current


def nearest_waiting_car(game_data: GameData, origin: tuple[float, float]) -> Car | None:
    """Find the closest waiting car to an origin point."""
    cars = _alive_waiting_cars(game_data)
    if not cars:
        return None
    return min(
        cars,
        key=lambda car: (car.rect.centerx - origin[0]) ** 2
        + (car.rect.centery - origin[1]) ** 2,
    )


def _spawn_nearby_zombie(
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
        min_player_dist=ZOMBIE_SPAWN_PLAYER_BUFFER,
        attempts=50,
    )
    new_zombie = _create_zombie(
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
    new_zombie = _create_zombie(
        config,
        start_pos=spawn_pos,
        stage=game_data.stage,
    )
    zombie_group.add(new_zombie)
    all_sprites.add(new_zombie, layer=1)
    return new_zombie


def update_falling_zombies(game_data: GameData, config: dict[str, Any]) -> None:
    state = game_data.state
    if not state.falling_zombies:
        return
    now = pygame.time.get_ticks()
    zombie_group = game_data.groups.zombie_group
    all_sprites = game_data.groups.all_sprites
    for fall in list(state.falling_zombies):
        fall_start = fall.started_at_ms + fall.pre_fx_ms
        impact_at = fall_start + fall.fall_duration_ms
        spawn_at = impact_at + fall.dust_duration_ms
        if now >= impact_at and not fall.dust_started:
            state.dust_rings.append(
                DustRing(
                    pos=fall.target_pos,
                    started_at_ms=impact_at,
                    duration_ms=fall.dust_duration_ms,
                )
            )
            fall.dust_started = True
        if now < spawn_at:
            continue
        if len(zombie_group) >= MAX_ZOMBIES:
            state.falling_zombies.remove(fall)
            continue
        candidate = _create_zombie(
            config,
            start_pos=fall.target_pos,
            stage=game_data.stage,
            tracker=fall.tracker,
            wall_follower=fall.wall_follower,
        )
        zombie_group.add(candidate)
        all_sprites.add(candidate, layer=1)
        state.falling_zombies.remove(fall)


def spawn_weighted_zombie(
    game_data: GameData,
    config: dict[str, Any],
) -> bool:
    """Spawn a zombie according to the stage's interior/exterior mix."""
    stage = game_data.stage

    def _spawn_interior() -> bool:
        return _spawn_nearby_zombie(game_data, config) is not None

    def _spawn_exterior() -> bool:
        return spawn_exterior_zombie(game_data, config) is not None

    def _spawn_fall() -> FallScheduleResult:
        result = _schedule_falling_zombie(game_data, config)
        if result != "scheduled":
            return result
        state = game_data.state
        if state.falling_spawn_carry > 0:
            extra = _schedule_falling_zombie(
                game_data,
                config,
                allow_carry=False,
            )
            if extra == "scheduled":
                state.falling_spawn_carry = max(0, state.falling_spawn_carry - 1)
        return "scheduled"

    interior_weight = max(0.0, stage.interior_spawn_weight)
    exterior_weight = max(0.0, stage.exterior_spawn_weight)
    fall_weight = max(0.0, getattr(stage, "interior_fall_spawn_weight", 0.0))
    total_weight = interior_weight + exterior_weight + fall_weight
    if total_weight <= 0:
        # Fall back to exterior spawns if weights are unset or invalid.
        return _spawn_exterior()

    pick = RNG.uniform(0, total_weight)
    if pick <= interior_weight:
        if _spawn_interior():
            return True
        fall_result = _spawn_fall()
        if fall_result == "scheduled":
            return True
        return False
    if pick <= interior_weight + fall_weight:
        fall_result = _spawn_fall()
        if fall_result == "scheduled":
            return True
        return False
    if _spawn_exterior():
        return True
    fall_result = _spawn_fall()
    if fall_result == "scheduled":
        return True
    return False
