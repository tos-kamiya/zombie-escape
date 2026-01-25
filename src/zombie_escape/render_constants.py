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
    fog_rings: list[FogRing]
    footprint_radius: int
    footprint_overview_radius: int
    footprint_lifetime_ms: int
    footprint_min_fade: float
    internal_wall_grid_snap: int
    flashlight_hatch_extra_scale: float


FOG_RADIUS_SCALE = 1.2

FLASHLIGHT_FOG_SCALE_ONE = FOG_RADIUS_SCALE + 0.3
FLASHLIGHT_FOG_SCALE_TWO = FOG_RADIUS_SCALE + 0.6
FLASHLIGHT_HATCH_EXTRA_SCALE = 0.12

FOOTPRINT_RADIUS = 2
FOOTPRINT_OVERVIEW_RADIUS = 3
FOOTPRINT_COLOR = (110, 200, 255)
FOOTPRINT_LIFETIME_MS = 135000
FOOTPRINT_MIN_FADE = 0.3

SHADOW_OVERSAMPLE = 2
SHADOW_STEPS = 10
SHADOW_MIN_RATIO = 0.0
SHADOW_RADIUS_RATIO = 0.3
ENTITY_SHADOW_RADIUS_MULT = 1.8
ENTITY_SHADOW_ALPHA = 48
ENTITY_SHADOW_EDGE_SOFTNESS = 0.32
PLAYER_SHADOW_RADIUS_MULT = 1.6
PLAYER_SHADOW_ALPHA_MULT = 0.8

FOG_RINGS = [
    FogRing(radius_factor=0.536, thickness=2),
    FogRing(radius_factor=0.645, thickness=3),
    FogRing(radius_factor=0.754, thickness=5),
    FogRing(radius_factor=0.863, thickness=8),
    FogRing(radius_factor=0.972, thickness=12),
]


def build_render_assets(cell_size: int) -> RenderAssets:
    return RenderAssets(
        screen_width=SCREEN_WIDTH,
        screen_height=SCREEN_HEIGHT,
        status_bar_height=STATUS_BAR_HEIGHT,
        player_radius=PLAYER_RADIUS,
        fov_radius=FOV_RADIUS,
        fog_radius_scale=FOG_RADIUS_SCALE,
        fog_rings=FOG_RINGS,
        footprint_radius=FOOTPRINT_RADIUS,
        footprint_overview_radius=FOOTPRINT_OVERVIEW_RADIUS,
        footprint_lifetime_ms=FOOTPRINT_LIFETIME_MS,
        footprint_min_fade=FOOTPRINT_MIN_FADE,
        internal_wall_grid_snap=cell_size,
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
    "FLASHLIGHT_FOG_SCALE_ONE",
    "FLASHLIGHT_FOG_SCALE_TWO",
    "SHADOW_OVERSAMPLE",
    "SHADOW_STEPS",
    "SHADOW_MIN_RATIO",
    "SHADOW_RADIUS_RATIO",
    "ENTITY_SHADOW_RADIUS_MULT",
    "ENTITY_SHADOW_ALPHA",
    "ENTITY_SHADOW_EDGE_SOFTNESS",
    "PLAYER_SHADOW_RADIUS_MULT",
    "PLAYER_SHADOW_ALPHA_MULT",
    "FLASHLIGHT_HATCH_EXTRA_SCALE",
    "build_render_assets",
]
