"""Render-related constants and assets."""

from __future__ import annotations

import math
from dataclasses import dataclass

from .entities_constants import FOV_RADIUS, PLAYER_RADIUS
from .screen_constants import SCREEN_HEIGHT, SCREEN_WIDTH, STATUS_BAR_HEIGHT

# Keep constants grouped by subsystem so new values have a predictable home.

# --- Entity colors ---
HUMANOID_OUTLINE_COLOR = (0, 80, 200)
HUMANOID_OUTLINE_WIDTH = 1
BUDDY_COLOR = (0, 155, 140)
SURVIVOR_COLOR = (198, 198, 198)
ZOMBIE_BODY_COLOR = (180, 0, 0)
ZOMBIE_OUTLINE_COLOR = (255, 60, 60)
ZOMBIE_NOSE_COLOR = (255, 80, 80)
TRAPPED_OUTLINE_COLOR = (172, 0, 181)
PATROL_BOT_BODY_COLOR = (200, 200, 200)
PATROL_BOT_OUTLINE_COLOR = (45, 40, 50)
PATROL_BOT_ARROW_COLOR = (140, 70, 200)
HOUSEPLANT_BODY_COLOR = (30, 120, 30)
HOUSEPLANT_SPIKE_COLOR = (61, 196, 115)

# --- Tile/effect colors ---
MOVING_FLOOR_TILE_COLOR = (90, 90, 90)
MOVING_FLOOR_LINE_COLOR = (130, 130, 130)
MOVING_FLOOR_BORDER_COLOR = (10, 10, 10)
PUDDLE_TILE_COLOR = (30, 60, 100)
FALLING_ZOMBIE_COLOR = (45, 45, 45)
FALLING_WHIRLWIND_COLOR = (200, 200, 200, 120)
FALLING_DUST_COLOR = (70, 70, 70, 130)

# --- Overview colors ---
MOVING_FLOOR_OVERVIEW_COLOR = (50, 50, 50)
LINEFORMER_MARKER_OVERVIEW_COLOR = (150, 50, 50)
TRAPPED_ZOMBIE_OVERVIEW_COLOR = (110, 40, 140)
PUDDLE_OVERVIEW_COLOR = (60, 120, 200)

# --- Gameplay/UI tuning ---
ANGLE_BINS = 16
HAND_SPREAD_RAD = math.radians(75)
GAMEPLAY_FONT_SIZE = 11
HUD_ICON_SIZE = 12
FADE_IN_DURATION_MS = 900
TIMED_MESSAGE_LEFT_X = 20
TIMED_MESSAGE_TOP_Y = 48
TIMED_MESSAGE_BAND_ALPHA = 80

# --- Fog/FOV tuning ---
FOG_RADIUS_SCALE = 1.2

FLASHLIGHT_FOG_SCALE_ONE = FOG_RADIUS_SCALE + 0.3
FLASHLIGHT_FOG_SCALE_TWO = FOG_RADIUS_SCALE + 0.6
_FLASHLIGHT_HATCH_EXTRA_SCALE = 0.12
FOG_HATCH_SOFTEN_SCALE = 0.9
FOG_HATCH_DENSITY_RAMPS: list[tuple[float, float]] = [
    (0.5, 0.5),
    (0.97, 0.3),
]

# --- Footprint tuning ---
FOOTPRINT_RADIUS = 2
FOOTPRINT_OVERVIEW_RADIUS = 3
FOOTPRINT_COLOR = (110, 200, 255)
FOOTPRINT_LIFETIME_MS = 135000
FOOTPRINT_MIN_FADE = 0.3

# --- Shadow tuning ---
SHADOW_OVERSAMPLE = 2
SHADOW_STEPS = 10
SHADOW_MIN_RATIO = 0.0
SHADOW_RADIUS_RATIO = 0.3
ENTITY_SHADOW_RADIUS_MULT = 1.8
ENTITY_SHADOW_ALPHA = 48
ENTITY_SHADOW_EDGE_SOFTNESS = 0.32
PLAYER_SHADOW_RADIUS_MULT = 1.6
PLAYER_SHADOW_ALPHA_MULT = 0.8

# --- Pitfall rendering ---
PITFALL_ABYSS_COLOR = (21, 20, 20)
PITFALL_SHADOW_RIM_COLOR = (38, 34, 34)
PITFALL_SHADOW_WIDTH = 6
PITFALL_EDGE_METAL_COLOR = (110, 110, 115)
PITFALL_EDGE_STRIPE_COLOR = (75, 75, 80)
PITFALL_EDGE_STRIPE_SPACING = 6
PITFALL_EDGE_DEPTH_OFFSET = 3


@dataclass(frozen=True)
class RenderAssets:
    screen_width: int
    screen_height: int
    status_bar_height: int
    player_radius: int
    fov_radius: int
    fog_radius_scale: float
    footprint_radius: int
    footprint_overview_radius: int
    footprint_lifetime_ms: int
    footprint_min_fade: float
    internal_wall_grid_snap: int
    flashlight_hatch_extra_scale: float
    fog_hatch_soften_scale: float
    fog_hatch_density_ramps: list[tuple[float, float]]


def build_render_assets(cell_size: int) -> RenderAssets:
    return RenderAssets(
        screen_width=SCREEN_WIDTH,
        screen_height=SCREEN_HEIGHT,
        status_bar_height=STATUS_BAR_HEIGHT,
        player_radius=PLAYER_RADIUS,
        fov_radius=FOV_RADIUS,
        fog_radius_scale=FOG_RADIUS_SCALE,
        footprint_radius=FOOTPRINT_RADIUS,
        footprint_overview_radius=FOOTPRINT_OVERVIEW_RADIUS,
        footprint_lifetime_ms=FOOTPRINT_LIFETIME_MS,
        footprint_min_fade=FOOTPRINT_MIN_FADE,
        internal_wall_grid_snap=cell_size,
        flashlight_hatch_extra_scale=_FLASHLIGHT_HATCH_EXTRA_SCALE,
        fog_hatch_soften_scale=FOG_HATCH_SOFTEN_SCALE,
        fog_hatch_density_ramps=FOG_HATCH_DENSITY_RAMPS,
    )


__all__ = [
    # Entity colors
    "HUMANOID_OUTLINE_COLOR",
    "HUMANOID_OUTLINE_WIDTH",
    "BUDDY_COLOR",
    "SURVIVOR_COLOR",
    "ZOMBIE_BODY_COLOR",
    "ZOMBIE_OUTLINE_COLOR",
    "ZOMBIE_NOSE_COLOR",
    "TRAPPED_OUTLINE_COLOR",
    "PATROL_BOT_BODY_COLOR",
    "PATROL_BOT_OUTLINE_COLOR",
    "PATROL_BOT_ARROW_COLOR",
    "HOUSEPLANT_BODY_COLOR",
    "HOUSEPLANT_SPIKE_COLOR",
    # Tile/effect colors
    "FALLING_ZOMBIE_COLOR",
    "FALLING_WHIRLWIND_COLOR",
    "FALLING_DUST_COLOR",
    "MOVING_FLOOR_TILE_COLOR",
    "MOVING_FLOOR_LINE_COLOR",
    "MOVING_FLOOR_BORDER_COLOR",
    "PUDDLE_TILE_COLOR",
    # Overview colors
    "MOVING_FLOOR_OVERVIEW_COLOR",
    "LINEFORMER_MARKER_OVERVIEW_COLOR",
    "TRAPPED_ZOMBIE_OVERVIEW_COLOR",
    "PUDDLE_OVERVIEW_COLOR",
    # Gameplay/UI tuning
    "ANGLE_BINS",
    "HAND_SPREAD_RAD",
    "GAMEPLAY_FONT_SIZE",
    "HUD_ICON_SIZE",
    "FADE_IN_DURATION_MS",
    "TIMED_MESSAGE_LEFT_X",
    "TIMED_MESSAGE_TOP_Y",
    "TIMED_MESSAGE_BAND_ALPHA",
    # Fog/FOV tuning
    "FOG_RADIUS_SCALE",
    "FLASHLIGHT_FOG_SCALE_ONE",
    "FLASHLIGHT_FOG_SCALE_TWO",
    "FOG_HATCH_SOFTEN_SCALE",
    "FOG_HATCH_DENSITY_RAMPS",
    # Shadow tuning
    "SHADOW_OVERSAMPLE",
    "SHADOW_STEPS",
    "SHADOW_MIN_RATIO",
    "SHADOW_RADIUS_RATIO",
    "ENTITY_SHADOW_RADIUS_MULT",
    "ENTITY_SHADOW_ALPHA",
    "ENTITY_SHADOW_EDGE_SOFTNESS",
    "PLAYER_SHADOW_RADIUS_MULT",
    "PLAYER_SHADOW_ALPHA_MULT",
    # Pitfall rendering
    "PITFALL_ABYSS_COLOR",
    "PITFALL_SHADOW_RIM_COLOR",
    "PITFALL_SHADOW_WIDTH",
    "PITFALL_EDGE_METAL_COLOR",
    "PITFALL_EDGE_STRIPE_COLOR",
    "PITFALL_EDGE_STRIPE_SPACING",
    "PITFALL_EDGE_DEPTH_OFFSET",
    # Data/builder API
    "RenderAssets",
    "build_render_assets",
]
