"""Dataclasses that model persistent game state structures."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import IntEnum
from typing import TYPE_CHECKING

import pygame
from pygame import sprite, surface

from .entities_constants import (
    SPIKY_PLANT_RADIUS,
    MovingFloorDirection,
    ZOMBIE_DECAY_DURATION_FRAMES,
    ZombieKind,
)
from .gameplay_constants import (
    DEFAULT_FLASHLIGHT_SPAWN_COUNT,
    DEFAULT_SHOES_SPAWN_COUNT,
    ZOMBIE_SPAWN_DELAY_MS,
)
from .level_constants import DEFAULT_CELL_SIZE, DEFAULT_GRID_COLS, DEFAULT_GRID_ROWS
from .localization import translate as tr

if TYPE_CHECKING:  # pragma: no cover - typing-only imports
    from .entities import (
        Camera,
        Car,
        EmptyFuelCan,
        Flashlight,
        FuelCan,
        FuelStation,
        Player,
        Shoes,
    )
    from .entities.spiky_plant import SpikyPlant
    from .render.decay_effects import DecayingEntityEffect
    from .gameplay.lineformer_trains import LineformerTrainManager
    from .gameplay.spatial_index import SpatialIndex
    from .level_blueprints import Blueprint
    from .world_grid import WallIndex


def _make_lineformer_manager():
    from .gameplay.lineformer_trains import LineformerTrainManager

    return LineformerTrainManager()


class FuelMode(IntEnum):
    REFUEL_CHAIN = 0
    FUEL_CAN = 1
    START_FULL = 2


class FuelProgress(IntEnum):
    NONE = 0
    EMPTY_CAN = 1
    FULL_CAN = 2


@dataclass
class LevelLayout:
    """Container for level layout rectangles and cell sets."""

    field_rect: pygame.Rect
    grid_cols: int
    grid_rows: int
    outside_cells: set[tuple[int, int]]
    walkable_cells: list[tuple[int, int]]
    outer_wall_cells: set[tuple[int, int]]
    wall_cells: set[tuple[int, int]]
    steel_beam_cells: set[tuple[int, int]]
    pitfall_cells: set[tuple[int, int]]
    car_walkable_cells: set[tuple[int, int]]
    car_spawn_cells: list[tuple[int, int]]
    fall_spawn_cells: set[tuple[int, int]]
    spiky_plant_cells: set[tuple[int, int]]
    fire_floor_cells: set[tuple[int, int]] = field(default_factory=set)
    metal_floor_cells: set[tuple[int, int]] = field(default_factory=set)
    zombie_contaminated_cells: set[tuple[int, int]] = field(default_factory=set)
    puddle_cells: set[tuple[int, int]] = field(default_factory=set)
    bevel_corners: dict[tuple[int, int], tuple[bool, bool, bool, bool]] = field(
        default_factory=dict
    )
    moving_floor_cells: dict[tuple[int, int], MovingFloorDirection] = field(
        default_factory=dict
    )

@dataclass
class FallingEntity:
    """Represents an entity falling toward a target position or into a pit."""

    start_pos: tuple[int, int]
    target_pos: tuple[int, int]
    started_at_ms: int
    pre_fx_ms: int
    fall_duration_ms: int
    dust_duration_ms: int
    kind: ZombieKind | None
    dust_started: bool = False
    mode: str = "spawn"  # "spawn" (falling in) or "pitfall" (falling out)


@dataclass
class DustRing:
    """Short-lived dust ring spawned on impact."""

    pos: tuple[int, int]
    started_at_ms: int
    duration_ms: int


@dataclass
class PuddleSplash:
    """Short-lived splash ring spawned while walking through a puddle."""

    pos: tuple[int, int]
    started_at_ms: int
    duration_ms: int


@dataclass
class GameClock:
    """Frame-driven gameplay clock with time scaling."""

    elapsed_ms: int = 0
    time_scale: float = 1.0

    def tick(self, frame_ms: int) -> int:
        step = max(1, int(frame_ms * self.time_scale))
        self.elapsed_ms += step
        return step


@dataclass(frozen=True)
class Footprint:
    """Tracked player footprint."""

    pos: tuple[int, int]
    time: int
    visible: bool = True


@dataclass
class ProgressState:
    """Game progress/state flags."""

    game_over: bool
    game_won: bool
    timed_message: "TimedMessage | None"
    fade_in_started_at_ms: int | None
    game_over_at: int | None
    scaled_overview: surface.Surface | None
    overview_created: bool
    footprints: list[Footprint]
    puddle_splashes: list[PuddleSplash]
    spatial_index: "SpatialIndex"
    decay_effects: list["DecayingEntityEffect"]
    last_footprint_pos: tuple[int, int] | None
    last_puddle_splash_pos: tuple[int, int] | None
    footprint_visible_toggle: bool
    clock: GameClock
    fuel_progress: FuelProgress
    flashlight_count: int
    shoes_count: int
    ambient_palette_key: str
    hint_expires_at: int
    hint_target_type: str | None
    contact_hint_records: list["ContactHintRecord"]
    buddy_rescued: int
    buddy_onboard: int
    buddy_merged_count: int
    survivors_onboard: int
    survivors_rescued: int
    survivor_messages: list
    survivor_capacity: int
    seed: int | None
    endurance_elapsed_ms: int
    endurance_goal_ms: int
    dawn_ready: bool
    dawn_prompt_at: int | None
    time_accel_active: bool
    time_accel_multiplier: float
    last_zombie_spawn_time: int
    dawn_carbonized: bool
    debug_mode: bool
    show_fps: bool
    falling_zombies: list[FallingEntity]
    falling_spawn_carry: int
    dust_rings: list[DustRing]
    electrified_cells: set[tuple[int, int]]
    player_wall_target_cell: tuple[int, int] | None
    player_wall_target_ttl: int


@dataclass(frozen=True)
class TimedMessage:
    """Timed HUD message with styling and behavior."""

    text: str
    expires_at_ms: int
    clear_on_input: bool
    color: tuple[int, int, int] | None
    align: str


@dataclass
class ContactHintRecord:
    """Persistent hint anchor for contacted objectives."""

    kind: str
    target_id: int
    anchor_pos: tuple[int, int]


@dataclass
class Groups:
    """Sprite groups container."""

    all_sprites: sprite.LayeredUpdates
    wall_group: sprite.Group
    zombie_group: sprite.Group
    survivor_group: sprite.Group
    patrol_bot_group: sprite.Group


@dataclass
class GameData:
    """Aggregated handles for the core game entities."""

    state: ProgressState
    groups: Groups
    camera: Camera
    layout: LevelLayout
    fog: dict
    stage: Stage
    cell_size: int
    wall_index: "WallIndex | None" = None
    wall_index_dirty: bool = True
    blueprint: Blueprint | None = None
    fuel: FuelCan | None = None
    empty_fuel_can: EmptyFuelCan | None = None
    fuel_station: FuelStation | None = None
    flashlights: list[Flashlight] | None = None
    shoes: list[Shoes] | None = None
    player: Player | None = None
    car: Car | None = None
    waiting_cars: list[Car] = field(default_factory=list)
    spiky_plants: dict[tuple[int, int], "SpikyPlant"] = field(default_factory=dict)
    last_logged_waiting_cars: int | None = None
    lineformer_trains: "LineformerTrainManager" = field(
        default_factory=_make_lineformer_manager
    )

@dataclass(frozen=True)
class Stage:
    # Id, name, description
    id: str
    name_key: str
    description_key: str
    available: bool = True
    intro_key: str | None = None

    # Map layout
    cell_size: int = DEFAULT_CELL_SIZE
    grid_cols: int = DEFAULT_GRID_COLS
    grid_rows: int = DEFAULT_GRID_ROWS
    wall_algorithm: str = "default"
    exit_sides: list[str] = field(
        default_factory=lambda: ["top", "bottom", "left", "right"]
    )
    wall_rubble_ratio: float = 0.0
    reinforced_wall_density: float = 0.0
    reinforced_wall_zones: list[tuple[int, int, int, int]] = field(default_factory=list)
    fall_spawn_zones: list[tuple[int, int, int, int]] = field(default_factory=list)
    fall_spawn_cell_ratio: float = 0.0
    pitfall_density: float = 0.0
    pitfall_zones: list[tuple[int, int, int, int]] = field(default_factory=list)
    fire_floor_density: float = 0.0
    fire_floor_zones: list[tuple[int, int, int, int]] = field(default_factory=list)
    metal_floor_density: float = 0.0
    metal_floor_zones: list[tuple[int, int, int, int]] = field(default_factory=list)
    moving_floor_zones: dict[str, list[tuple[int, int, int, int]]] = field(
        default_factory=dict
    )
    moving_floor_cells: dict[tuple[int, int], MovingFloorDirection] = field(
        default_factory=dict
    )
    spiky_plant_density: float = 0.0
    spiky_plant_zones: list[tuple[int, int, int, int]] = field(default_factory=list)
    puddle_density: float = 0.0
    puddle_zones: list[tuple[int, int, int, int]] = field(default_factory=list)

    # Stage objective
    fuel_mode: FuelMode = FuelMode.START_FULL
    buddy_required_count: int = 0
    survivor_rescue_stage: bool = False
    endurance_stage: bool = False
    endurance_goal_ms: int = 0

    # Items
    fuel_spawn_count: int = 1
    empty_fuel_can_spawn_count: int = 1
    fuel_station_spawn_count: int = 1
    initial_flashlight_count: int = DEFAULT_FLASHLIGHT_SPAWN_COUNT
    initial_shoes_count: int = DEFAULT_SHOES_SPAWN_COUNT
    waiting_car_target_count: int = 1

    # Zombie spawning/aging
    # - initial_interior_spawn_rate: fraction of interior floor cells to seed.
    # - spawn weights: pick area by weight (normalized).
    # - zombie ratios: pick variant by weight (normalized).
    spawn_interval_ms: int = ZOMBIE_SPAWN_DELAY_MS
    zombie_spawn_count_per_interval: int = 1
    initial_interior_spawn_rate: float = 0.015
    exterior_spawn_weight: float = 1.0
    interior_spawn_weight: float = 0.0
    interior_fall_spawn_weight: float = 0.0
    zombie_tracker_ratio: float = 0.0
    zombie_wall_hugging_ratio: float = 0.0
    zombie_lineformer_ratio: float = 0.0
    zombie_solitary_ratio: float = 0.0
    zombie_normal_ratio: float = 0.0
    zombie_dog_ratio: float = 0.0
    zombie_nimble_dog_ratio: float = 0.0
    zombie_decay_duration_frames: int = ZOMBIE_DECAY_DURATION_FRAMES

    # Patrol bot spawning
    patrol_bot_spawn_rate: float = 0.0

    # Survivor spawning
    survivor_spawn_rate: float = 0.0

    def __post_init__(self) -> None:
        mode_raw = self.fuel_mode
        mode = mode_raw if isinstance(mode_raw, FuelMode) else FuelMode(int(mode_raw))
        object.__setattr__(self, "fuel_mode", mode)
        if mode == FuelMode.FUEL_CAN:
            assert self.fuel_spawn_count >= 1, (
                "fuel_can stages must set fuel_spawn_count >= 1"
            )
        if mode == FuelMode.REFUEL_CHAIN:
            assert self.empty_fuel_can_spawn_count >= 1, (
                "refuel_chain stages must set empty_fuel_can_spawn_count >= 1"
            )
            assert self.fuel_station_spawn_count >= 1, (
                "refuel_chain stages must set fuel_station_spawn_count >= 1"
            )
        if self.spiky_plant_density > 0 or self.spiky_plant_zones:
            assert self.cell_size * 0.5 > SPIKY_PLANT_RADIUS + 2, (
                f"cell_size ({self.cell_size}) is too small for spiky_plant optimization "
                f"(requires half-cell > {SPIKY_PLANT_RADIUS + 2})"
            )
        total_zombie_ratio = (
            float(self.zombie_normal_ratio)
            + float(self.zombie_tracker_ratio)
            + float(self.zombie_wall_hugging_ratio)
            + float(self.zombie_lineformer_ratio)
            + float(self.zombie_solitary_ratio)
            + float(self.zombie_dog_ratio)
            + float(self.zombie_nimble_dog_ratio)
        )
        assert total_zombie_ratio > 0.0, (
            f"Stage {self.id}: at least one zombie ratio must be > 0"
        )

        # Exclusivity validation for zone-based gimmicks
        self._validate_zone_exclusivity()

    def _validate_zone_exclusivity(self) -> None:
        """Ensure that exclusive gimmicks do not overlap in zones."""

        def _get_cells(zones: list[tuple[int, int, int, int]]) -> set[tuple[int, int]]:
            cells = set()
            for x, y, w, h in zones:
                for dy in range(h):
                    for dx in range(w):
                        cells.add((x + dx, y + dy))
            return cells

        # Collect all cells from different gimmicks
        pitfall_cells = _get_cells(self.pitfall_zones)
        fire_floor_cells = _get_cells(self.fire_floor_zones)
        metal_floor_cells = _get_cells(self.metal_floor_zones)
        reinforced_cells = _get_cells(self.reinforced_wall_zones)

        floor_cells = set()
        for zones in self.moving_floor_zones.values():
            floor_cells.update(_get_cells(zones))

        plant_cells = _get_cells(self.spiky_plant_zones)
        water_cells = _get_cells(self.puddle_zones)

        # Check overlaps
        # 1. Pitfall vs others
        assert not (pitfall_cells & floor_cells), (
            f"Stage {self.id}: Pitfall and Moving Floor zones overlap"
        )
        assert not (pitfall_cells & fire_floor_cells), (
            f"Stage {self.id}: Pitfall and Fire Floor zones overlap"
        )
        assert not (pitfall_cells & metal_floor_cells), (
            f"Stage {self.id}: Pitfall and Metal Floor zones overlap"
        )
        assert not (pitfall_cells & plant_cells), (
            f"Stage {self.id}: Pitfall and SpikyPlant zones overlap"
        )
        assert not (pitfall_cells & water_cells), (
            f"Stage {self.id}: Pitfall and Puddle zones overlap"
        )

        # 2. Moving Floor vs others
        assert not (floor_cells & plant_cells), (
            f"Stage {self.id}: Moving Floor and SpikyPlant zones overlap"
        )
        assert not (floor_cells & water_cells), (
            f"Stage {self.id}: Moving Floor and Puddle zones overlap"
        )
        assert not (floor_cells & reinforced_cells), (
            f"Stage {self.id}: Moving Floor and Reinforced Wall zones overlap"
        )
        assert not (floor_cells & fire_floor_cells), (
            f"Stage {self.id}: Moving Floor and Fire Floor zones overlap"
        )
        assert not (floor_cells & metal_floor_cells), (
            f"Stage {self.id}: Moving Floor and Metal Floor zones overlap"
        )

        # 3. SpikyPlant vs Puddle
        assert not (plant_cells & water_cells), (
            f"Stage {self.id}: SpikyPlant and Puddle zones overlap"
        )
        assert not (plant_cells & fire_floor_cells), (
            f"Stage {self.id}: SpikyPlant and Fire Floor zones overlap"
        )
        assert not (plant_cells & metal_floor_cells), (
            f"Stage {self.id}: SpikyPlant and Metal Floor zones overlap"
        )
        assert not (water_cells & fire_floor_cells), (
            f"Stage {self.id}: Puddle and Fire Floor zones overlap"
        )
        assert not (water_cells & metal_floor_cells), (
            f"Stage {self.id}: Puddle and Metal Floor zones overlap"
        )
        assert not (reinforced_cells & fire_floor_cells), (
            f"Stage {self.id}: Reinforced Wall and Fire Floor zones overlap"
        )
        assert not (reinforced_cells & metal_floor_cells), (
            f"Stage {self.id}: Reinforced Wall and Metal Floor zones overlap"
        )
        assert not (fire_floor_cells & metal_floor_cells), (
            f"Stage {self.id}: Fire Floor and Metal Floor zones overlap"
        )

    @property
    def requires_fuel(self) -> bool:
        return self.fuel_mode != FuelMode.START_FULL

    @property
    def requires_refuel(self) -> bool:
        return self.fuel_mode == FuelMode.REFUEL_CHAIN

    @property
    def name(self) -> str:
        return tr(self.name_key)

    @property
    def description(self) -> str:
        return tr(self.description_key)


__all__ = [
    "LevelLayout",
    "FallingEntity",
    "DustRing",
    "ProgressState",
    "Groups",
    "GameData",
    "Stage",
    "FuelMode",
    "FuelProgress",
]
