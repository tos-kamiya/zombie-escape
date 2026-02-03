"""Dataclasses that model persistent game state structures."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

import pygame
from pygame import sprite, surface

from .entities_constants import ZOMBIE_AGING_DURATION_FRAMES
from .gameplay_constants import (
    DEFAULT_FLASHLIGHT_SPAWN_COUNT,
    DEFAULT_SHOES_SPAWN_COUNT,
    SURVIVOR_SPAWN_RATE,
    ZOMBIE_SPAWN_DELAY_MS,
)
from .level_constants import DEFAULT_GRID_COLS, DEFAULT_GRID_ROWS
from .localization import translate as tr

if TYPE_CHECKING:  # pragma: no cover - typing-only imports
    from .entities import Camera, Car, Flashlight, FuelCan, Player, Shoes


@dataclass
class LevelLayout:
    """Container for level layout rectangles and cell sets."""

    field_rect: pygame.Rect
    outside_cells: set[tuple[int, int]]
    walkable_cells: list[tuple[int, int]]
    outer_wall_cells: set[tuple[int, int]]
    wall_cells: set[tuple[int, int]]
    pitfall_cells: set[tuple[int, int]]
    car_walkable_cells: set[tuple[int, int]]
    fall_spawn_cells: set[tuple[int, int]]
    bevel_corners: dict[tuple[int, int], tuple[bool, bool, bool, bool]]


@dataclass
class FallingZombie:
    """Represents a zombie falling toward a target position or into a pit."""

    start_pos: tuple[int, int]
    target_pos: tuple[int, int]
    started_at_ms: int
    pre_fx_ms: int
    fall_duration_ms: int
    dust_duration_ms: int
    tracker: bool
    wall_hugging: bool
    dust_started: bool = False
    mode: str = "spawn"  # "spawn" (falling in) or "pitfall" (falling out)


@dataclass
class DustRing:
    """Short-lived dust ring spawned on impact."""

    pos: tuple[int, int]
    started_at_ms: int
    duration_ms: int


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
    game_over_message: str | None
    game_over_at: int | None
    scaled_overview: surface.Surface | None
    overview_created: bool
    footprints: list[Footprint]
    last_footprint_pos: tuple[int, int] | None
    footprint_visible_toggle: bool
    elapsed_play_ms: int
    has_fuel: bool
    flashlight_count: int
    shoes_count: int
    ambient_palette_key: str
    hint_expires_at: int
    hint_target_type: str | None
    fuel_message_until: int
    buddy_rescued: int
    buddy_onboard: int
    buddy_merged_count: int
    intro_message: str | None
    intro_message_until: int
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
    last_zombie_spawn_time: int
    dawn_carbonized: bool
    debug_mode: bool
    show_fps: bool
    falling_zombies: list[FallingZombie]
    falling_spawn_carry: int
    dust_rings: list[DustRing]
    player_wall_target_cell: tuple[int, int] | None
    player_wall_target_ttl: int


@dataclass
class Groups:
    """Sprite groups container."""

    all_sprites: sprite.LayeredUpdates
    wall_group: sprite.Group
    zombie_group: sprite.Group
    survivor_group: sprite.Group


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
    level_width: int
    level_height: int
    fuel: FuelCan | None = None
    flashlights: list[Flashlight] | None = None
    shoes: list[Shoes] | None = None
    player: Player | None = None
    car: Car | None = None
    waiting_cars: list[Car] = field(default_factory=list)
    last_logged_waiting_cars: int | None = None


@dataclass(frozen=True)
class Stage:
    # Id, name, description
    id: str
    name_key: str
    description_key: str
    available: bool = True
    intro_key: str | None = None

    # Map layout
    cell_size: int = 50
    grid_cols: int = DEFAULT_GRID_COLS
    grid_rows: int = DEFAULT_GRID_ROWS
    wall_algorithm: str = "default"
    wall_rubble_ratio: float = 0.0
    fall_spawn_zones: list[tuple[int, int, int, int]] = field(default_factory=list)
    fall_spawn_floor_ratio: float = 0.0
    pitfall_density: float = 0.0
    pitfall_zones: list[tuple[int, int, int, int]] = field(default_factory=list)

    # Stage objective
    requires_fuel: bool = False
    buddy_required_count: int = 0
    rescue_stage: bool = False
    endurance_stage: bool = False
    endurance_goal_ms: int = 0

    # Items
    fuel_spawn_count: int = 1
    initial_flashlight_count: int = DEFAULT_FLASHLIGHT_SPAWN_COUNT
    initial_shoes_count: int = DEFAULT_SHOES_SPAWN_COUNT
    waiting_car_target_count: int = 1

    # Zombie spawning/aging
    # - initial_interior_spawn_rate: fraction of interior floor cells to seed.
    # - spawn weights: pick area by weight (normalized).
    # - zombie ratios: pick variant by weight (normalized).
    spawn_interval_ms: int = ZOMBIE_SPAWN_DELAY_MS
    initial_interior_spawn_rate: float = 0.015
    exterior_spawn_weight: float = 1.0
    interior_spawn_weight: float = 0.0
    interior_fall_spawn_weight: float = 0.0
    zombie_tracker_ratio: float = 0.0
    zombie_wall_hugging_ratio: float = 0.0
    zombie_normal_ratio: float = 1.0
    zombie_aging_duration_frames: int = ZOMBIE_AGING_DURATION_FRAMES

    # Survivor spawning
    survivor_spawn_rate: float = SURVIVOR_SPAWN_RATE

    @property
    def name(self) -> str:
        return tr(self.name_key)

    @property
    def description(self) -> str:
        return tr(self.description_key)


__all__ = [
    "LevelLayout",
    "FallingZombie",
    "DustRing",
    "ProgressState",
    "Groups",
    "GameData",
    "Stage",
]
