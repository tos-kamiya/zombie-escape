"""Dataclasses that model persistent game state structures."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

import pygame
from pygame import sprite, surface

from .gameplay_constants import ZOMBIE_AGING_DURATION_FRAMES, ZOMBIE_SPAWN_DELAY_MS
from .localization import translate as tr

if TYPE_CHECKING:  # pragma: no cover - typing-only imports
    from .entities import Camera, Car, Companion, Flashlight, FuelCan, Player


@dataclass
class Areas:
    """Container for level area rectangles."""

    outer_rect: tuple[int, int, int, int]
    inner_rect: tuple[int, int, int, int]
    outside_rects: list[pygame.Rect]
    walkable_cells: list[pygame.Rect]
    outer_wall_cells: set[tuple[int, int]]


@dataclass
class ProgressState:
    """Game progress/state flags."""

    game_over: bool
    game_won: bool
    game_over_message: str | None
    game_over_at: int | None
    scaled_overview: surface.Surface | None
    overview_created: bool
    footprints: list
    last_footprint_pos: tuple | None
    elapsed_play_ms: int
    has_fuel: bool
    flashlight_count: int
    ambient_palette_key: str
    hint_expires_at: int
    hint_target_type: str | None
    fuel_message_until: int
    companion_rescued: bool
    survivors_onboard: int
    survivors_rescued: int
    survivor_messages: list
    survivor_capacity: int
    seed: int | None
    survival_elapsed_ms: int
    survival_goal_ms: int
    dawn_ready: bool
    dawn_prompt_at: int | None
    time_accel_active: bool
    last_zombie_spawn_time: int
    dawn_carbonized: bool
    debug_mode: bool


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
    areas: Areas
    fog: dict
    stage: Stage
    fuel: FuelCan | None = None
    flashlights: list[Flashlight] | None = None
    player: Player | None = None
    car: Car | None = None
    waiting_cars: list[Car] = field(default_factory=list)
    companion: Companion | None = None
    last_logged_waiting_cars: int | None = None


@dataclass(frozen=True)
class Stage:
    id: str
    name_key: str
    description_key: str
    available: bool = True
    requires_fuel: bool = False
    companion_stage: bool = False
    rescue_stage: bool = False
    survival_stage: bool = False
    survival_goal_ms: int = 0
    fuel_spawn_count: int = 1
    spawn_interval_ms: int = ZOMBIE_SPAWN_DELAY_MS
    initial_interior_spawn_rate: float = 0.015
    exterior_spawn_weight: float = 1.0
    interior_spawn_weight: float = 0.0
    zombie_tracker_ratio: float = 0.0
    zombie_wall_follower_ratio: float = 0.0
    zombie_normal_ratio: float = 1.0
    zombie_aging_duration_frames: int = ZOMBIE_AGING_DURATION_FRAMES

    @property
    def name(self) -> str:
        return tr(self.name_key)

    @property
    def description(self) -> str:
        return tr(self.description_key)


__all__ = [
    "Areas",
    "ProgressState",
    "Groups",
    "GameData",
    "Stage",
]
