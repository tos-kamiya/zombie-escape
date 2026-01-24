"""Dataclasses that model persistent game state structures."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

import pygame
from pygame import sprite, surface

from .entities_constants import ZOMBIE_AGING_DURATION_FRAMES
from .gameplay_constants import (
    DEFAULT_FLASHLIGHT_SPAWN_COUNT,
    SURVIVOR_SPAWN_RATE,
    ZOMBIE_SPAWN_DELAY_MS,
)
from .level_constants import DEFAULT_GRID_COLS, DEFAULT_GRID_ROWS
from .localization import translate as tr

if TYPE_CHECKING:  # pragma: no cover - typing-only imports
    from .entities import Camera, Car, Flashlight, FuelCan, Player


@dataclass
class LevelLayout:
    """Container for level layout rectangles and cell sets."""

    outer_rect: tuple[int, int, int, int]
    inner_rect: tuple[int, int, int, int]
    outside_rects: list[pygame.Rect]
    walkable_cells: list[pygame.Rect]
    outer_wall_cells: set[tuple[int, int]]
    wall_cells: set[tuple[int, int]]
    fall_spawn_cells: set[tuple[int, int]]
    bevel_corners: dict[tuple[int, int], tuple[bool, bool, bool, bool]]


@dataclass
class FallingZombie:
    """Represents a zombie falling toward a target position."""

    start_pos: tuple[int, int]
    target_pos: tuple[int, int]
    started_at_ms: int
    pre_fx_ms: int
    fall_duration_ms: int
    dust_duration_ms: int
    tracker: bool
    wall_follower: bool
    dust_started: bool = False


@dataclass
class DustRing:
    """Short-lived dust ring spawned on impact."""

    pos: tuple[int, int]
    started_at_ms: int
    duration_ms: int


@dataclass(frozen=True)
class Footprint:
    """Tracked player footprint."""

    pos: tuple[float, float]
    time: int


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
    last_footprint_pos: tuple[float, float] | None
    elapsed_play_ms: int
    has_fuel: bool
    flashlight_count: int
    ambient_palette_key: str
    hint_expires_at: int
    hint_target_type: str | None
    fuel_message_until: int
    buddy_rescued: int
    buddy_onboard: int
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
    falling_zombies: list[FallingZombie]
    falling_spawn_carry: int
    dust_rings: list[DustRing]


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
    player: Player | None = None
    car: Car | None = None
    waiting_cars: list[Car] = field(default_factory=list)
    last_logged_waiting_cars: int | None = None


@dataclass(frozen=True)
class Stage:
    id: str
    name_key: str
    description_key: str
    available: bool = True
    tile_size: int = 50
    grid_cols: int = DEFAULT_GRID_COLS
    grid_rows: int = DEFAULT_GRID_ROWS
    requires_fuel: bool = False
    buddy_required_count: int = 0
    rescue_stage: bool = False
    endurance_stage: bool = False
    endurance_goal_ms: int = 0
    fuel_spawn_count: int = 1
    initial_flashlight_count: int = DEFAULT_FLASHLIGHT_SPAWN_COUNT
    survivor_spawn_rate: float = SURVIVOR_SPAWN_RATE
    spawn_interval_ms: int = ZOMBIE_SPAWN_DELAY_MS
    initial_interior_spawn_rate: float = 0.015
    exterior_spawn_weight: float = 1.0
    interior_spawn_weight: float = 0.0
    interior_fall_spawn_weight: float = 0.0
    fall_spawn_zones: list[tuple[int, int, int, int]] = field(default_factory=list)
    zombie_tracker_ratio: float = 0.0
    zombie_wall_follower_ratio: float = 0.0
    zombie_normal_ratio: float = 1.0
    zombie_aging_duration_frames: int = ZOMBIE_AGING_DURATION_FRAMES
    waiting_car_target_count: int = 1
    wall_algorithm: str = "default"

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
