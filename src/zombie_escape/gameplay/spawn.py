from __future__ import annotations

from typing import Any, Callable, Literal, Mapping, Sequence

import pygame

from ..entities import (
    CarrierBot,
    Car,
    EmptyFuelCan,
    Flashlight,
    FuelCan,
    FuelStation,
    Material,
    PatrolBot,
    Player,
    Shoes,
    SpikyPlant,
    Survivor,
    TransportBot,
    Zombie,
    ZombieDog,
    random_position_outside_building,
    spritecollideany_walls,
)
from ..entities.zombie_movement import (
    _zombie_lineformer_train_head_movement,
    _zombie_solitary_movement,
)
from ..entities_constants import (
    FAST_ZOMBIE_BASE_SPEED,
    PLAYER_SPEED,
    TRANSPORT_BOT_ACTIVATION_RADIUS,
    TRANSPORT_BOT_END_WAIT_MS,
    TRANSPORT_BOT_SPEED,
    ZombieKind,
    ZOMBIE_DECAY_DURATION_FRAMES,
    ZOMBIE_SPEED,
)
from ..gameplay_constants import (
    DEFAULT_FLASHLIGHT_SPAWN_COUNT,
    DEFAULT_SHOES_SPAWN_COUNT,
)
from ..level_constants import DEFAULT_CELL_SIZE, DEFAULT_GRID_COLS, DEFAULT_GRID_ROWS
from ..models import DustRing, FallingEntity, GameData, Stage
from ..rng import get_rng
from .constants import (
    FALLING_ZOMBIE_DUST_DURATION_MS,
    FALLING_ZOMBIE_DURATION_MS,
    FALLING_ZOMBIE_PRE_FX_MS,
    LAYER_HOUSEPLANTS,
    LAYER_ITEMS,
    LAYER_PLAYERS,
    LAYER_VEHICLES,
    LAYER_ZOMBIES,
    MAX_ZOMBIES,
    ZOMBIE_SPAWN_PLAYER_BUFFER,
    ZOMBIE_TRACKER_DECAY_DURATION_FRAMES,
)
from .utils import (
    fov_radius_for_flashlights,
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
    "place_empty_fuel_can",
    "place_fuel_station",
    "place_flashlights",
    "place_shoes",
    "place_buddies",
    "spawn_survivors",
    "setup_player_and_cars",
    "spawn_initial_zombies",
    "spawn_initial_patrol_bots",
    "spawn_initial_transport_bots",
    "spawn_initial_carrier_bots_and_materials",
    "spawn_spiky_plants",
    "spawn_waiting_car",
    "maintain_waiting_car_supply",
    "nearest_waiting_car",
    "update_falling_zombies",
    "spawn_exterior_zombie",
    "spawn_weighted_zombie",
]


def _cell_center(cell: tuple[int, int], cell_size: int) -> tuple[int, int]:
    return (
        int((cell[0] * cell_size) + (cell_size / 2)),
        int((cell[1] * cell_size) + (cell_size / 2)),
    )


def _car_appearance_for_stage(stage: Stage | None) -> str:
    return "disabled" if stage and stage.endurance_stage else "default"


def _pick_zombie_variant(stage: Stage | None) -> ZombieKind:
    normal_ratio = 1.0
    tracker_ratio = 0.0
    wall_hugging_ratio = 0.0
    lineformer_ratio = 0.0
    solitary_ratio = 0.0
    dog_ratio = 0.0
    if stage is not None:
        normal_ratio = max(0.0, float(stage.zombie_normal_ratio))
        tracker_ratio = max(0.0, float(stage.zombie_tracker_ratio))
        wall_hugging_ratio = max(0.0, float(stage.zombie_wall_hugging_ratio))
        lineformer_ratio = max(0.0, float(stage.zombie_lineformer_ratio))
        solitary_ratio = max(0.0, float(stage.zombie_solitary_ratio))
        # Dog sub-variants are part of dog weight so total type weights normalize.
        tracker_dog_ratio = max(0.0, float(stage.zombie_tracker_dog_ratio))
        # Nimble and tracker dogs are dog sub-variants; include them in dog weight.
        # total zombie-type weights can always be normalized.
        nimble_ratio = max(0.0, float(stage.zombie_nimble_dog_ratio))
        dog_ratio = max(0.0, float(stage.zombie_dog_ratio)) + nimble_ratio + tracker_dog_ratio
    total_ratio = (
        normal_ratio
        + tracker_ratio
        + wall_hugging_ratio
        + lineformer_ratio
        + solitary_ratio
        + dog_ratio
    )
    if total_ratio <= 0:
        return ZombieKind.NORMAL
    pick = RNG.random() * total_ratio
    if pick < normal_ratio:
        return ZombieKind.NORMAL
    if pick < normal_ratio + tracker_ratio:
        return ZombieKind.TRACKER
    if pick < normal_ratio + tracker_ratio + wall_hugging_ratio:
        return ZombieKind.WALL_HUGGER
    if pick < normal_ratio + tracker_ratio + wall_hugging_ratio + lineformer_ratio:
        return ZombieKind.LINEFORMER
    if pick < (
        normal_ratio
        + tracker_ratio
        + wall_hugging_ratio
        + lineformer_ratio
        + solitary_ratio
    ):
        return ZombieKind.SOLITARY
    return ZombieKind.DOG


def _build_initial_zombie_kind_plan(
    stage: Stage | None, total: int
) -> list[ZombieKind]:
    if total <= 0:
        return []
    normal_ratio = 1.0
    tracker_ratio = 0.0
    wall_hugging_ratio = 0.0
    lineformer_ratio = 0.0
    solitary_ratio = 0.0
    dog_ratio = 0.0
    if stage is not None:
        normal_ratio = max(0.0, float(stage.zombie_normal_ratio))
        tracker_ratio = max(0.0, float(stage.zombie_tracker_ratio))
        wall_hugging_ratio = max(0.0, float(stage.zombie_wall_hugging_ratio))
        lineformer_ratio = max(0.0, float(stage.zombie_lineformer_ratio))
        solitary_ratio = max(0.0, float(stage.zombie_solitary_ratio))
        nimble_ratio = max(0.0, float(stage.zombie_nimble_dog_ratio))
        tracker_dog_ratio = max(0.0, float(stage.zombie_tracker_dog_ratio))
        dog_ratio = (
            max(0.0, float(stage.zombie_dog_ratio))
            + nimble_ratio
            + tracker_dog_ratio
        )
    weighted_kinds = [
        (ZombieKind.NORMAL, normal_ratio),
        (ZombieKind.TRACKER, tracker_ratio),
        (ZombieKind.WALL_HUGGER, wall_hugging_ratio),
        (ZombieKind.LINEFORMER, lineformer_ratio),
        (ZombieKind.SOLITARY, solitary_ratio),
        (ZombieKind.DOG, dog_ratio),
    ]
    total_ratio = sum(weight for _, weight in weighted_kinds)
    if total_ratio <= 0.0:
        return [ZombieKind.NORMAL] * total
    planned: list[ZombieKind] = []
    for kind, weight in weighted_kinds:
        if weight <= 0.0:
            continue
        count = int(round(total * (weight / total_ratio)))
        if count == 0:
            count = 1
        planned.extend([kind] * count)
    if not planned:
        return [ZombieKind.NORMAL] * total
    RNG.shuffle(planned)
    if len(planned) >= total:
        return planned[:total]
    while len(planned) < total:
        planned.append(RNG.choice(planned))
    RNG.shuffle(planned)
    return planned


def _is_spawn_position_clear(
    game_data: GameData,
    candidate: Zombie | ZombieDog,
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
    for bot in game_data.groups.patrol_bot_group:
        if bot.alive() and spawn_rect.colliderect(bot.rect):
            return False
    return True


def _is_patrol_spawn_position_clear(
    game_data: GameData,
    candidate: PatrolBot,
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
    for bot in game_data.groups.patrol_bot_group:
        if bot.alive() and spawn_rect.colliderect(bot.rect):
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
    mounted_vehicle = getattr(player, "mounted_vehicle", None)
    if mounted_vehicle is not None and mounted_vehicle.alive():
        target_sprite = mounted_vehicle
    elif player.in_car and car and car.alive():
        # Legacy fallback while call sites migrate from `in_car`.
        target_sprite = car
    else:
        target_sprite = player
    target_center = target_sprite.rect.center
    cell_size = game_data.cell_size
    fov_radius = fov_radius_for_flashlights(game_data.state.flashlight_count)
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
    min_distance = game_data.stage.cell_size * 0.5
    kind = _pick_zombie_variant(game_data.stage)

    def _candidate_clear(pos: tuple[int, int]) -> bool:
        candidate = _create_zombie(
            config,
            start_pos=pos,
            stage=game_data.stage,
            kind=kind,
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
    # start_offset removed; animation handles "falling" via scaling now.
    start_pos = (int(spawn_pos[0]), int(spawn_pos[1]))
    fall = FallingEntity(
        start_pos=start_pos,
        target_pos=(int(spawn_pos[0]), int(spawn_pos[1])),
        started_at_ms=game_data.state.clock.elapsed_ms,
        pre_fx_ms=FALLING_ZOMBIE_PRE_FX_MS,
        fall_duration_ms=FALLING_ZOMBIE_DURATION_MS,
        dust_duration_ms=FALLING_ZOMBIE_DUST_DURATION_MS,
        kind=kind,
    )
    state.falling_zombies.append(fall)
    return "scheduled"


def _create_zombie(
    config: dict[str, Any],
    *,
    start_pos: tuple[int, int] | None = None,
    hint_pos: tuple[float, float] | None = None,
    stage: Stage | None = None,
    kind: ZombieKind | None = None,
) -> Zombie | ZombieDog:
    """Factory to create zombies with optional fast variants."""
    fast_conf = config.get("fast_zombies", {})
    fast_enabled = fast_conf.get("enabled", True)
    if fast_enabled:
        base_speed = RNG.uniform(ZOMBIE_SPEED, FAST_ZOMBIE_BASE_SPEED)
    else:
        base_speed = ZOMBIE_SPEED
    if stage is not None:
        decay_duration_frames = max(
            1.0,
            float(stage.zombie_decay_duration_frames),
        )
    else:
        decay_duration_frames = ZOMBIE_DECAY_DURATION_FRAMES
    if kind is None:
        kind = _pick_zombie_variant(stage)
    base_speed = min(base_speed, PLAYER_SPEED - 0.05)
    if kind == ZombieKind.TRACKER:
        ratio = (
            ZOMBIE_TRACKER_DECAY_DURATION_FRAMES / ZOMBIE_DECAY_DURATION_FRAMES
            if ZOMBIE_DECAY_DURATION_FRAMES > 0
            else 1.0
        )
        decay_duration_frames = max(1.0, decay_duration_frames * ratio)
    if start_pos is None:
        cell_size = stage.cell_size if stage else DEFAULT_CELL_SIZE
        if stage is None:
            grid_cols = DEFAULT_GRID_COLS
            grid_rows = DEFAULT_GRID_ROWS
        else:
            grid_cols = stage.grid_cols
            grid_rows = stage.grid_rows
        level_width = grid_cols * cell_size
        level_height = grid_rows * cell_size
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
    if kind == ZombieKind.DOG:
        normal_weight = 1.0
        nimble_weight = 0.0
        tracker_dog_weight = 0.0
        if stage is not None:
            normal_weight = max(0.0, float(stage.zombie_dog_ratio))
            nimble_weight = max(0.0, float(stage.zombie_nimble_dog_ratio))
            tracker_dog_weight = max(0.0, float(stage.zombie_tracker_dog_ratio))
        total_dog_weight = normal_weight + nimble_weight + tracker_dog_weight
        variant = "normal"
        if total_dog_weight > 0.0:
            pick = RNG.random() * total_dog_weight
            if pick < normal_weight:
                variant = "normal"
            elif pick < normal_weight + nimble_weight:
                variant = "nimble"
            else:
                variant = "tracker"
        return ZombieDog(
            x=float(start_pos[0]),
            y=float(start_pos[1]),
            variant=variant,
        )
    movement_strategy = None
    if kind == ZombieKind.LINEFORMER:
        movement_strategy = _zombie_lineformer_train_head_movement
    elif kind == ZombieKind.SOLITARY:
        movement_strategy = _zombie_solitary_movement
    return Zombie(
        x=float(start_pos[0]),
        y=float(start_pos[1]),
        speed=base_speed,
        kind=kind,
        movement_strategy=movement_strategy,
        decay_duration_frames=decay_duration_frames,
    )


def _spawn_lineformer_request(
    game_data: GameData,
    config: dict[str, Any],
    *,
    start_pos: tuple[int, int],
    allow_player_overlap: bool = False,
    check_walls: bool = True,
) -> Zombie | None:
    zombie_group = game_data.groups.zombie_group
    all_sprites = game_data.groups.all_sprites
    wall_group = game_data.groups.wall_group
    manager = game_data.lineformer_trains
    train_id, target_id = manager.resolve_spawn_target(zombie_group, start_pos)
    if train_id is not None:
        if manager.append_marker(train_id, start_pos):
            return manager.get_train_head(train_id, zombie_group)
        return None
    candidate = _create_zombie(
        config,
        start_pos=start_pos,
        stage=game_data.stage,
        kind=ZombieKind.LINEFORMER,
    )
    if not isinstance(candidate, Zombie):
        return None
    if check_walls and spritecollideany_walls(candidate, wall_group):
        return None
    if not _is_spawn_position_clear(
        game_data,
        candidate,
        allow_player_overlap=allow_player_overlap,
    ):
        return None
    zombie_group.add(candidate)
    all_sprites.add(candidate, layer=LAYER_ZOMBIES)
    manager.create_train_for_head(
        candidate,
        target_id=target_id,
        now_ms=game_data.state.clock.elapsed_ms,
    )
    return candidate


def place_fuel_can(
    walkable_cells: list[tuple[int, int]],
    cell_size: int,
    player: Player,
    *,
    cars: Sequence[Car] | None = None,
    reserved_centers: set[tuple[int, int]] | None = None,
    count: int = 1,
) -> FuelCan | None:
    """Pick a spawn spot for the fuel can away from the player (and car if given)."""
    return _place_collectible(
        walkable_cells,
        cell_size,
        player,
        cars=cars,
        reserved_centers=reserved_centers,
        count=count,
        min_player_dist=250,
        min_car_dist=200,
        factory=FuelCan,
    )


def place_empty_fuel_can(
    walkable_cells: list[tuple[int, int]],
    cell_size: int,
    player: Player,
    *,
    cars: Sequence[Car] | None = None,
    reserved_centers: set[tuple[int, int]] | None = None,
    count: int = 1,
) -> EmptyFuelCan | None:
    """Pick a spawn spot for the empty fuel can away from the player/car."""
    placed = _place_collectible(
        walkable_cells,
        cell_size,
        player,
        cars=cars,
        reserved_centers=reserved_centers,
        count=count,
        min_player_dist=250,
        min_car_dist=200,
        factory=EmptyFuelCan,
    )
    return placed if isinstance(placed, EmptyFuelCan) else None


def place_fuel_station(
    walkable_cells: list[tuple[int, int]],
    cell_size: int,
    player: Player,
    *,
    cars: Sequence[Car] | None = None,
    reserved_centers: set[tuple[int, int]] | None = None,
    count: int = 1,
) -> FuelStation | None:
    """Pick a spawn spot for the fuel station away from the player/car."""
    placed = _place_collectible(
        walkable_cells,
        cell_size,
        player,
        cars=cars,
        reserved_centers=reserved_centers,
        count=count,
        min_player_dist=260,
        min_car_dist=200,
        factory=FuelStation,
    )
    return placed if isinstance(placed, FuelStation) else None


def _place_collectible(
    walkable_cells: list[tuple[int, int]],
    cell_size: int,
    player: Player,
    *,
    cars: Sequence[Car] | None,
    reserved_centers: set[tuple[int, int]] | None,
    count: int,
    min_player_dist: int,
    min_car_dist: int,
    factory: Callable[[int, int], pygame.sprite.Sprite],
) -> pygame.sprite.Sprite | None:
    if count <= 0 or not walkable_cells:
        return None

    min_player_dist_sq = min_player_dist * min_player_dist
    min_car_dist_sq = min_car_dist * min_car_dist

    for _ in range(200):
        cell = RNG.choice(walkable_cells)
        center = _cell_center(cell, cell_size)
        if reserved_centers and center in reserved_centers:
            continue
        dx = center[0] - player.x
        dy = center[1] - player.y
        if dx * dx + dy * dy < min_player_dist_sq:
            continue
        if cars:
            too_close = False
            for parked_car in cars:
                dx = center[0] - parked_car.rect.centerx
                dy = center[1] - parked_car.rect.centery
                if dx * dx + dy * dy < min_car_dist_sq:
                    too_close = True
                    break
            if too_close:
                continue
        return factory(center[0], center[1])

    cell = RNG.choice(walkable_cells)
    center = _cell_center(cell, cell_size)
    return factory(center[0], center[1])


def _place_flashlight(
    walkable_cells: list[tuple[int, int]],
    cell_size: int,
    player: Player,
    *,
    cars: Sequence[Car] | None = None,
    reserved_centers: set[tuple[int, int]] | None = None,
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
        center = _cell_center(cell, cell_size)
        if reserved_centers and center in reserved_centers:
            continue
        dx = center[0] - player.x
        dy = center[1] - player.y
        if dx * dx + dy * dy < min_player_dist_sq:
            continue
        if cars:
            if any(
                (center[0] - parked.rect.centerx) ** 2
                + (center[1] - parked.rect.centery) ** 2
                < min_car_dist_sq
                for parked in cars
            ):
                continue
        return Flashlight(center[0], center[1])

    cell = RNG.choice(walkable_cells)
    center = _cell_center(cell, cell_size)
    return Flashlight(center[0], center[1])


def place_flashlights(
    walkable_cells: list[tuple[int, int]],
    cell_size: int,
    player: Player,
    *,
    cars: Sequence[Car] | None = None,
    reserved_centers: set[tuple[int, int]] | None = None,
    count: int = DEFAULT_FLASHLIGHT_SPAWN_COUNT,
) -> list[Flashlight]:
    """Spawn flashlights from blueprint cells (with fallback sampling if needed)."""
    if count <= 0 or not walkable_cells:
        return []

    # Blueprint-provided flashlight cells are explicit spawn points.
    placed: list[Flashlight] = []
    for cell in walkable_cells:
        if len(placed) >= count:
            break
        center = _cell_center(cell, cell_size)
        if reserved_centers and center in reserved_centers:
            continue
        placed.append(Flashlight(center[0], center[1]))
    if len(placed) >= count:
        return placed

    # Fallback for legacy/random candidate lists.
    attempts = 0
    max_attempts = max(200, count * 80)
    while len(placed) < count and attempts < max_attempts:
        attempts += 1
        fl = _place_flashlight(
            walkable_cells,
            cell_size,
            player,
            cars=cars,
            reserved_centers=reserved_centers,
        )
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


def _place_shoes(
    walkable_cells: list[tuple[int, int]],
    cell_size: int,
    player: Player,
    *,
    cars: Sequence[Car] | None = None,
    reserved_centers: set[tuple[int, int]] | None = None,
) -> Shoes | None:
    """Pick a spawn spot for the shoes away from the player (and car if given)."""
    if not walkable_cells:
        return None

    min_player_dist = 240
    min_car_dist = 200
    min_player_dist_sq = min_player_dist * min_player_dist
    min_car_dist_sq = min_car_dist * min_car_dist

    for _ in range(200):
        cell = RNG.choice(walkable_cells)
        center = _cell_center(cell, cell_size)
        if reserved_centers and center in reserved_centers:
            continue
        dx = center[0] - player.x
        dy = center[1] - player.y
        if dx * dx + dy * dy < min_player_dist_sq:
            continue
        if cars:
            if any(
                (center[0] - parked.rect.centerx) ** 2
                + (center[1] - parked.rect.centery) ** 2
                < min_car_dist_sq
                for parked in cars
            ):
                continue
        return Shoes(center[0], center[1])

    cell = RNG.choice(walkable_cells)
    center = _cell_center(cell, cell_size)
    return Shoes(center[0], center[1])


def place_shoes(
    walkable_cells: list[tuple[int, int]],
    cell_size: int,
    player: Player,
    *,
    cars: Sequence[Car] | None = None,
    reserved_centers: set[tuple[int, int]] | None = None,
    count: int = DEFAULT_SHOES_SPAWN_COUNT,
) -> list[Shoes]:
    """Spawn multiple shoes using the single-place helper to spread them out."""
    placed: list[Shoes] = []
    attempts = 0
    max_attempts = max(200, count * 80)
    while len(placed) < count and attempts < max_attempts:
        attempts += 1
        shoes = _place_shoes(
            walkable_cells,
            cell_size,
            player,
            cars=cars,
            reserved_centers=reserved_centers,
        )
        if not shoes:
            break
        if any(
            (other.rect.centerx - shoes.rect.centerx) ** 2
            + (other.rect.centery - shoes.rect.centery) ** 2
            < 120 * 120
            for other in placed
        ):
            continue
        placed.append(shoes)
    return placed


def place_buddies(
    walkable_cells: list[tuple[int, int]],
    cell_size: int,
    player: Player,
    *,
    count: int = 1,
) -> list[Survivor]:
    placed: list[Survivor] = []
    if count <= 0 or not walkable_cells:
        return placed
    min_player_dist = 240
    positions = find_interior_spawn_positions(
        walkable_cells,
        cell_size,
        1.0,
        player=player,
        min_player_dist=min_player_dist,
    )
    RNG.shuffle(positions)
    for pos in positions[:count]:
        placed.append(Survivor(pos[0], pos[1], is_buddy=True))
    remaining = count - len(placed)
    for _ in range(max(0, remaining)):
        spawn_pos = find_nearby_offscreen_spawn_position(
            walkable_cells,
            cell_size,
        )
        placed.append(Survivor(spawn_pos[0], spawn_pos[1], is_buddy=True))
    return placed


def place_new_car(
    wall_group: pygame.sprite.Group,
    player: Player,
    walkable_cells: list[tuple[int, int]],
    cell_size: int,
    *,
    existing_cars: Sequence[Car] | None = None,
    appearance: str = "default",
) -> Car | None:
    if not walkable_cells:
        return None

    max_attempts = 150
    for _ in range(max_attempts):
        cell = RNG.choice(walkable_cells)
        c_x, c_y = _cell_center(cell, cell_size)
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
    game_data: GameData, layout_data: Mapping[str, list[tuple[int, int]]]
) -> list[Survivor]:
    """Populate rescue-stage survivors and buddy-stage buddies."""
    survivors: list[Survivor] = []
    spawn_rate = max(0.0, game_data.stage.survivor_spawn_rate)
    if not (spawn_rate > 0.0 or game_data.stage.buddy_required_count > 0):
        return survivors

    walkable = layout_data.get("walkable_cells", [])
    wall_group = game_data.groups.wall_group
    survivor_group = game_data.groups.survivor_group
    all_sprites = game_data.groups.all_sprites
    cell_size = game_data.cell_size

    if spawn_rate > 0.0:
        positions = find_interior_spawn_positions(
            walkable,
            cell_size,
            spawn_rate,
        )
        for pos in positions:
            survivor = Survivor(*pos)
            if spritecollideany_walls(survivor, wall_group):
                continue
            survivor_group.add(survivor)
            all_sprites.add(survivor, layer=LAYER_PLAYERS)
            survivors.append(survivor)

    if game_data.stage.buddy_required_count > 0:
        buddy_count = max(0, game_data.stage.buddy_required_count)
        buddies: list[Survivor] = []
        if game_data.player:
            buddies = place_buddies(
                walkable,
                cell_size,
                game_data.player,
                count=buddy_count,
            )
        for buddy in buddies:
            if spritecollideany_walls(buddy, wall_group):
                continue
            survivor_group.add(buddy)
            all_sprites.add(buddy, layer=LAYER_PLAYERS)
            survivors.append(buddy)

    return survivors


def setup_player_and_cars(
    game_data: GameData,
    layout_data: Mapping[str, list[tuple[int, int]]],
    *,
    car_count: int = 1,
) -> tuple[Player, list[Car]]:
    """Create the player plus one or more parked cars using blueprint candidates."""
    if not game_data.stage.endurance_stage:
        assert car_count > 0, "Non-endurance stages must have at least one car"

    all_sprites = game_data.groups.all_sprites
    walkable_cells: list[tuple[int, int]] = layout_data["walkable_cells"]
    cell_size = game_data.cell_size
    level_rect = game_data.layout.field_rect

    def _pick_center(cells: list[tuple[int, int]]) -> tuple[int, int]:
        return (
            _cell_center(RNG.choice(cells), cell_size) if cells else level_rect.center
        )

    player_pos = _pick_center(layout_data["player_cells"] or walkable_cells)
    player = Player(*player_pos)

    car_spawn_cells = list(layout_data.get("car_spawn_cells", []))
    spiky_plant_set = set(layout_data.get("spiky_plant_cells", []))
    car_candidates = [
        c
        for c in (layout_data["car_cells"] or car_spawn_cells or walkable_cells)
        if c not in spiky_plant_set
    ]
    waiting_cars: list[Car] = []
    car_appearance = _car_appearance_for_stage(game_data.stage)

    def _pick_car_position() -> tuple[int, int]:
        """Favor distant cells for the first car, otherwise fall back to random picks."""
        if not car_candidates:
            return (player_pos[0] + 200, player_pos[1])
        RNG.shuffle(car_candidates)
        for candidate in car_candidates:
            center = _cell_center(candidate, cell_size)
            if (center[0] - player_pos[0]) ** 2 + (
                center[1] - player_pos[1]
            ) ** 2 >= 400 * 400:
                car_candidates.remove(candidate)
                return center
        choice = car_candidates.pop()
        return _cell_center(choice, cell_size)

    for _ in range(max(0, car_count)):
        car_pos = _pick_car_position()
        car = Car(*car_pos, appearance=car_appearance)
        waiting_cars.append(car)
        all_sprites.add(car, layer=LAYER_VEHICLES)
        if not car_candidates:
            break

    all_sprites.add(player, layer=LAYER_PLAYERS)
    return player, waiting_cars


def spawn_initial_zombies(
    game_data: GameData,
    player: Player,
    layout_data: Mapping[str, list[tuple[int, int]]],
    config: dict[str, Any],
) -> None:
    """Spawn initial zombies using blueprint candidate cells."""
    wall_group = game_data.groups.wall_group
    zombie_group = game_data.groups.zombie_group
    all_sprites = game_data.groups.all_sprites

    cell_size = game_data.cell_size
    spawn_cells = layout_data["walkable_cells"]
    if not spawn_cells:
        return

    def _apply_initial_health_gradient(
        zombie: Zombie | ZombieDog,
        *,
        index: int,
        total: int,
        now_ms: int,
    ) -> None:
        if total <= 0:
            return
        if total == 1:
            target_ratio = 1.0
        else:
            progress = index / (total - 1)
            target_ratio = 1.0 - (0.5 * progress)
        max_health = max(1, int(getattr(zombie, "max_health", 1)))
        current_health = max(0, int(getattr(zombie, "health", max_health)))
        target_health = max(1, min(max_health, int(round(max_health * target_ratio))))
        damage = max(0, current_health - target_health)
        if damage <= 0:
            return
        if isinstance(zombie, Zombie):
            zombie.take_damage(damage, source="initial_spawn_gradient", now_ms=now_ms)
        else:
            zombie.take_damage(damage, now_ms=now_ms)

    spawn_rate = max(0.0, game_data.stage.initial_interior_spawn_rate)
    positions = find_interior_spawn_positions(
        spawn_cells,
        cell_size,
        spawn_rate,
        player=player,
        min_player_dist=ZOMBIE_SPAWN_PLAYER_BUFFER,
    )
    kind_plan = _build_initial_zombie_kind_plan(game_data.stage, len(positions))

    for spawn_index, pos in enumerate(positions):
        kind = (
            kind_plan[spawn_index]
            if spawn_index < len(kind_plan)
            else _pick_zombie_variant(game_data.stage)
        )
        if kind == ZombieKind.LINEFORMER:
            _spawn_lineformer_request(
                game_data,
                config,
                start_pos=(int(pos[0]), int(pos[1])),
                check_walls=True,
            )
            continue
        tentative = _create_zombie(
            config,
            start_pos=pos,
            stage=game_data.stage,
            kind=kind,
        )
        if spritecollideany_walls(tentative, wall_group):
            continue
        _apply_initial_health_gradient(
            tentative,
            index=spawn_index,
            total=len(positions),
            now_ms=game_data.state.clock.elapsed_ms,
        )
        zombie_group.add(tentative)
        all_sprites.add(tentative, layer=LAYER_ZOMBIES)

    interval = max(1, game_data.stage.spawn_interval_ms)
    game_data.state.last_zombie_spawn_time = game_data.state.clock.elapsed_ms - interval


def spawn_initial_patrol_bots(
    game_data: GameData,
    player: Player,
    layout_data: Mapping[str, list[tuple[int, int]]],
) -> None:
    """Spawn initial patrol bots using walkable cells and stage spawn rate."""
    spawn_rate = max(0.0, game_data.stage.patrol_bot_spawn_rate)
    if spawn_rate <= 0.0:
        return
    walkable_cells = layout_data.get("walkable_cells", [])
    if not walkable_cells:
        return
    cell_size = game_data.cell_size
    positions = find_interior_spawn_positions(
        walkable_cells,
        cell_size,
        spawn_rate,
        jitter_ratio=0.0,
        player=player,
        min_player_dist=ZOMBIE_SPAWN_PLAYER_BUFFER,
    )
    if not positions:
        return

    patrol_group = game_data.groups.patrol_bot_group
    all_sprites = game_data.groups.all_sprites

    for pos in positions:
        bot = PatrolBot(pos[0], pos[1])
        if not _is_patrol_spawn_position_clear(game_data, bot):
            continue
        patrol_group.add(bot)
        all_sprites.add(bot, layer=LAYER_VEHICLES)


def spawn_initial_transport_bots(game_data: GameData) -> None:
    """Spawn transport bots from stage-defined polyline paths."""
    stage = game_data.stage
    if not stage.transport_bot_paths:
        return
    transport_group = game_data.groups.transport_bot_group
    all_sprites = game_data.groups.all_sprites
    speed = float(TRANSPORT_BOT_SPEED)
    activation_radius = (
        float(stage.transport_bot_activation_radius)
        if stage.transport_bot_activation_radius > 0.0
        else float(TRANSPORT_BOT_ACTIVATION_RADIUS)
    )
    end_wait_ms = (
        int(stage.transport_bot_end_wait_ms)
        if stage.transport_bot_end_wait_ms > 0
        else int(TRANSPORT_BOT_END_WAIT_MS)
    )
    for path in stage.transport_bot_paths:
        if len(path) < 2:
            continue
        world_path = [_cell_center((int(cx), int(cy)), game_data.cell_size) for cx, cy in path]
        bot = TransportBot(
            world_path,
            speed=speed,
            activation_radius=activation_radius,
            end_wait_ms=end_wait_ms,
        )
        if spritecollideany_walls(bot, game_data.groups.wall_group):
            continue
        transport_group.add(bot)
        all_sprites.add(bot, layer=LAYER_VEHICLES)


def spawn_initial_carrier_bots_and_materials(game_data: GameData) -> None:
    """Spawn carrier bots and materials from explicit stage cell definitions."""
    stage = game_data.stage
    if not stage.carrier_bot_spawns and not stage.material_spawns:
        return
    all_sprites = game_data.groups.all_sprites
    material_group = game_data.groups.material_group
    carrier_group = game_data.groups.carrier_bot_group
    cell_size = game_data.cell_size

    for cell_x, cell_y in stage.material_spawns:
        center = _cell_center((int(cell_x), int(cell_y)), cell_size)
        material = Material(center[0], center[1], size=max(4, int(cell_size * 0.8)))
        if spritecollideany_walls(material, game_data.groups.wall_group):
            continue
        material_group.add(material)
        all_sprites.add(material, layer=LAYER_ITEMS)

    for cell_x, cell_y, axis, direction_sign in stage.carrier_bot_spawns:
        center = _cell_center((int(cell_x), int(cell_y)), cell_size)
        bot = CarrierBot(
            center[0],
            center[1],
            axis=str(axis),
            direction_sign=int(direction_sign),
        )
        if spritecollideany_walls(bot, game_data.groups.wall_group):
            continue
        carrier_group.add(bot)
        all_sprites.add(bot, layer=LAYER_VEHICLES)


def spawn_waiting_car(game_data: GameData) -> Car | None:
    """Attempt to place an additional parked car on the map."""
    player = game_data.player
    if not player:
        return None
    # Use only spawn-safe car cells; reachability cells are tracked separately.
    spawn_cells = list(game_data.layout.car_spawn_cells)
    if not spawn_cells:
        return None
    wall_group = game_data.groups.wall_group
    all_sprites = game_data.groups.all_sprites
    cell_size = game_data.cell_size
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
            spawn_cells,
            cell_size,
            existing_cars=obstacles,
            appearance=appearance,
        )
        if not new_car:
            return None
        if rect_visible_on_screen(camera, new_car.rect):
            offscreen_attempts -= 1
            continue
        game_data.waiting_cars.append(new_car)
        all_sprites.add(new_car, layer=LAYER_VEHICLES)
        return new_car
    return None


def maintain_waiting_car_supply(
    game_data: GameData, *, minimum: int | None = None
) -> None:
    """Ensure a baseline count of parked cars exists."""
    if minimum is None:
        minimum = game_data.stage.waiting_car_target_count
    target = max(0, minimum)
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
        key=lambda car: (
            (car.rect.centerx - origin[0]) ** 2 + (car.rect.centery - origin[1]) ** 2
        ),
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
        game_data.cell_size,
        player=player,
        camera=camera,
        min_player_dist=ZOMBIE_SPAWN_PLAYER_BUFFER,
        attempts=50,
    )
    kind = _pick_zombie_variant(game_data.stage)
    if kind == ZombieKind.LINEFORMER:
        return _spawn_lineformer_request(
            game_data,
            config,
            start_pos=spawn_pos,
            check_walls=True,
        )
    new_zombie = _create_zombie(
        config,
        start_pos=spawn_pos,
        stage=game_data.stage,
        kind=kind,
    )
    if spritecollideany_walls(new_zombie, wall_group):
        return None
    zombie_group.add(new_zombie)
    all_sprites.add(new_zombie, layer=LAYER_ZOMBIES)
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
    level_rect = game_data.layout.field_rect
    spawn_pos = find_exterior_spawn_position(
        level_rect.width,
        level_rect.height,
        hint_pos=(player.x, player.y),
    )
    kind = _pick_zombie_variant(game_data.stage)
    if kind == ZombieKind.LINEFORMER:
        return _spawn_lineformer_request(
            game_data,
            config,
            start_pos=spawn_pos,
            check_walls=False,
        )
    new_zombie = _create_zombie(
        config,
        start_pos=spawn_pos,
        stage=game_data.stage,
        kind=kind,
    )
    zombie_group.add(new_zombie)
    all_sprites.add(new_zombie, layer=LAYER_ZOMBIES)
    return new_zombie


def update_falling_zombies(game_data: GameData, config: dict[str, Any]) -> None:
    state = game_data.state
    if not state.falling_zombies:
        return
    now = state.clock.elapsed_ms
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

        if getattr(fall, "mode", "spawn") == "spawn":
            if len(zombie_group) < MAX_ZOMBIES:
                if fall.kind == ZombieKind.LINEFORMER:
                    _spawn_lineformer_request(
                        game_data,
                        config,
                        start_pos=fall.target_pos,
                        allow_player_overlap=True,
                        check_walls=False,
                    )
                    state.falling_zombies.remove(fall)
                    continue
                candidate = _create_zombie(
                    config,
                    start_pos=fall.target_pos,
                    stage=game_data.stage,
                    kind=fall.kind,
                )
                zombie_group.add(candidate)
                all_sprites.add(candidate, layer=LAYER_ZOMBIES)

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


def spawn_spiky_plants(
    game_data: GameData,
    layout_data: Mapping[str, list[tuple[int, int]]],
) -> list[SpikyPlant]:
    """Spawn spiky plants based on blueprint cells."""
    spiky_plants: list[SpikyPlant] = []
    spiky_plant_cells = layout_data.get("spiky_plant_cells", [])
    if not spiky_plant_cells:
        return spiky_plants

    all_sprites = game_data.groups.all_sprites
    cell_size = game_data.cell_size

    for cell in spiky_plant_cells:
        pos = _cell_center(cell, cell_size)
        spiky_plant = SpikyPlant(pos[0], pos[1])
        all_sprites.add(spiky_plant, layer=LAYER_HOUSEPLANTS)
        spiky_plants.append(spiky_plant)

    return spiky_plants
