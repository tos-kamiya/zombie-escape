"""Render-related constants and assets."""

from __future__ import annotations

from .gameplay_constants import FOV_RADIUS, PLAYER_RADIUS
from .level_constants import CELL_SIZE
from .render_assets import FogRing, RenderAssets
from .screen_constants import SCREEN_HEIGHT, SCREEN_WIDTH, STATUS_BAR_HEIGHT

FOG_RADIUS_SCALE = 1.2
FOG_HATCH_PIXEL_SCALE = 2

FLASHLIGHT_FOG_SCALE_STEP = 0.3

FOOTPRINT_RADIUS = 2
FOOTPRINT_OVERVIEW_RADIUS = 3
FOOTPRINT_COLOR = (110, 200, 255)
FOOTPRINT_LIFETIME_MS = 135000
FOOTPRINT_MIN_FADE = 0.3

INTERNAL_WALL_GRID_SNAP = CELL_SIZE

FOG_RINGS = [
    FogRing(radius_factor=0.529, thickness=2),
    FogRing(radius_factor=0.639, thickness=4),
    FogRing(radius_factor=0.748, thickness=6),
    FogRing(radius_factor=0.858, thickness=8),
    FogRing(radius_factor=0.968, thickness=12),
]

RENDER_ASSETS = RenderAssets(
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
    internal_wall_grid_snap=INTERNAL_WALL_GRID_SNAP,
    flashlight_bonus_step=FLASHLIGHT_FOG_SCALE_STEP,
)

__all__ = [
    "FOG_RADIUS_SCALE",
    "FLASHLIGHT_FOG_SCALE_STEP",
    "RENDER_ASSETS",
]
