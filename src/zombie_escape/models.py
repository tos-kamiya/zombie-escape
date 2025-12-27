"""Dataclasses that model persistent game state structures."""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional, Tuple, TYPE_CHECKING

import pygame
from pygame import sprite, surface

from .i18n import translate as _

if TYPE_CHECKING:  # pragma: no cover - typing-only imports
    from .entities import Camera, Car, Companion, FuelCan, Flashlight, Player


@dataclass
class Areas:
    """Container for level area rectangles."""

    outer_rect: Tuple[int, int, int, int]
    inner_rect: Tuple[int, int, int, int]
    outside_rects: list[pygame.Rect]
    walkable_cells: list[pygame.Rect]


@dataclass
class ProgressState:
    """Game progress/state flags."""

    game_over: bool
    game_won: bool
    game_over_message: str | None
    game_over_at: int | None
    overview_surface: surface.Surface | None
    scaled_overview: surface.Surface | None
    overview_created: bool
    last_zombie_spawn_time: int
    footprints: list
    last_footprint_pos: tuple | None
    elapsed_play_ms: int
    has_fuel: bool
    has_flashlight: bool
    hint_expires_at: int
    hint_target_type: str | None
    fuel_message_until: int
    companion_rescued: bool
    survivors_onboard: int
    survivors_rescued: int
    survivor_messages: list


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
    config: dict
    stage: Stage
    fuel: Optional[FuelCan] = None
    flashlights: List[Flashlight] | None = None
    player: Optional[Player] = None
    car: Optional[Car] = None
    companion: Optional[Companion] = None


@dataclass(frozen=True)
class Stage:
    id: str
    name_key: str
    description_key: str
    available: bool = True
    requires_fuel: bool = False
    requires_companion: bool = False
    survivor_stage: bool = False

    @property
    def name(self) -> str:
        return _(self.name_key)

    @property
    def description(self) -> str:
        return _(self.description_key)


STAGES: List[Stage] = [
    Stage(
        id="stage1",
        name_key="stages.stage1.name",
        description_key="stages.stage1.description",
        available=True,
    ),
    Stage(
        id="stage2",
        name_key="stages.stage2.name",
        description_key="stages.stage2.description",
        available=True,
        requires_fuel=True,
    ),
    Stage(
        id="stage3",
        name_key="stages.stage3.name",
        description_key="stages.stage3.description",
        available=True,
        requires_companion=True,
        requires_fuel=True,
    ),
    Stage(
        id="stage4",
        name_key="stages.stage4.name",
        description_key="stages.stage4.description",
        available=True,
        survivor_stage=True,
    ),
]
DEFAULT_STAGE_ID = "stage1"


__all__ = [
    "Areas",
    "ProgressState",
    "Groups",
    "GameData",
    "Stage",
    "STAGES",
    "DEFAULT_STAGE_ID",
]
