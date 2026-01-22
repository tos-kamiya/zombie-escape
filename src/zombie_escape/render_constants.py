"""Render-related constants and assets."""

from __future__ import annotations

from dataclasses import dataclass

from .entities_constants import FOV_RADIUS, PLAYER_RADIUS
from .screen_constants import SCREEN_HEIGHT, SCREEN_WIDTH, STATUS_BAR_HEIGHT

HUMANOID_OUTLINE_COLOR = (0, 80, 200)
HUMANOID_OUTLINE_WIDTH = 1
BUDDY_COLOR = (0, 180, 63)
SURVIVOR_COLOR = (198, 198, 198)
FALLING_ZOMBIE_COLOR = (45, 45, 45)
FALLING_WHIRLWIND_COLOR = (200, 200, 200, 120)
FALLING_DUST_COLOR = (70, 70, 70, 130)


@dataclass(frozen=True)
class FogRing:
    radius_factor: float
    thickness: int


@dataclass(frozen=True)
class RenderAssets:
    screen_width: int
    screen_height: int
    status_bar_height: int
    player_radius: int
    fov_radius: int
    fog_radius_scale: float
    fog_hatch_pixel_scale: int
    fog_rings: list[FogRing]
    footprint_radius: int
    footprint_overview_radius: int
    footprint_lifetime_ms: int
    footprint_min_fade: float
    internal_wall_grid_snap: int
    flashlight_bonus_step: float
    flashlight_hatch_extra_scale: float


FOG_RADIUS_SCALE = 1.2
FOG_HATCH_PIXEL_SCALE = 2

FLASHLIGHT_FOG_SCALE_STEP = 0.3
FLASHLIGHT_HATCH_EXTRA_SCALE = 0.12

FOOTPRINT_RADIUS = 2
FOOTPRINT_OVERVIEW_RADIUS = 3
FOOTPRINT_COLOR = (110, 200, 255)
FOOTPRINT_LIFETIME_MS = 135000
FOOTPRINT_MIN_FADE = 0.3

FOG_RINGS = [
    FogRing(radius_factor=0.529, thickness=2),
    FogRing(radius_factor=0.639, thickness=4),
    FogRing(radius_factor=0.748, thickness=6),
    FogRing(radius_factor=0.858, thickness=8),
    FogRing(radius_factor=0.968, thickness=12),
]


def build_render_assets(cell_size: int) -> RenderAssets:
    return RenderAssets(
        screen_width=SCREEN_WIDTH,
        screen_height=SCREEN_HEIGHT,
        status_bar_height=STATUS_BAR_HEIGHT,
        player_radius=PLAYER_RADIUS,
        fov_radius=FOV_RADIUS,
        fog_radius_scale=FOG_RADIUS_SCALE,
        fog_hatch_pixel_scale=FOG_HATCH_PIXEL_SCALE,
        fog_rings=FOG_RINGS,
        footprint_radius=FOOTPRINT_RADIUS,
        footprint_overview_radius=FOOTPRINT_OVERVIEW_RADIUS,
        footprint_lifetime_ms=FOOTPRINT_LIFETIME_MS,
        footprint_min_fade=FOOTPRINT_MIN_FADE,
        internal_wall_grid_snap=cell_size,
        flashlight_bonus_step=FLASHLIGHT_FOG_SCALE_STEP,
        flashlight_hatch_extra_scale=FLASHLIGHT_HATCH_EXTRA_SCALE,
    )


__all__ = [
    "BUDDY_COLOR",
    "FALLING_ZOMBIE_COLOR",
    "FALLING_WHIRLWIND_COLOR",
    "FALLING_DUST_COLOR",
    "HUMANOID_OUTLINE_COLOR",
    "HUMANOID_OUTLINE_WIDTH",
    "SURVIVOR_COLOR",
    "FogRing",
    "RenderAssets",
    "FOG_RADIUS_SCALE",
    "FLASHLIGHT_FOG_SCALE_STEP",
    "FLASHLIGHT_HATCH_EXTRA_SCALE",
    "build_render_assets",
]
