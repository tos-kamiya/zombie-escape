"""Shared render asset helpers and factories."""

from __future__ import annotations

from ..colors import EnvironmentPalette
from ..render_constants import RenderAssets
from .common import angle_bin_from_vector
from .geometry import build_beveled_polygon
from .characters import (
    build_patrol_bot_directional_surfaces,
    build_player_directional_surfaces,
    build_survivor_directional_surfaces,
    build_zombie_directional_surfaces,
    build_zombie_dog_directional_surfaces,
    draw_humanoid_hand,
    draw_lightning_marker,
    draw_lineformer_direction_arm,
    draw_tracker_nose,
)
from .icons import get_character_icon, get_tile_icon
from .items import (
    build_empty_fuel_can_surface,
    build_flashlight_surface,
    build_fuel_can_surface,
    build_fuel_station_surface,
    build_shoes_surface,
)
from .vehicle import (
    build_car_directional_surfaces,
    build_car_surface,
    paint_car_surface,
    resolve_car_color,
)
from .walls import (
    RUBBLE_ROTATION_DEG,
    build_rubble_wall_surface,
    paint_steel_beam_surface,
    paint_wall_damage_overlay,
    paint_wall_surface,
    resolve_steel_beam_colors,
    resolve_wall_colors,
    resolve_wall_outline_color,
    rubble_offset_for_size,
)

__all__ = [
    "angle_bin_from_vector",
    "EnvironmentPalette",
    "RenderAssets",
    "build_beveled_polygon",
    "resolve_wall_colors",
    "resolve_wall_outline_color",
    "paint_wall_damage_overlay",
    "resolve_car_color",
    "resolve_steel_beam_colors",
    "build_player_directional_surfaces",
    "draw_humanoid_hand",
    "draw_tracker_nose",
    "draw_lineformer_direction_arm",
    "draw_lightning_marker",
    "build_survivor_directional_surfaces",
    "build_zombie_directional_surfaces",
    "build_zombie_dog_directional_surfaces",
    "build_patrol_bot_directional_surfaces",
    "build_car_surface",
    "build_car_directional_surfaces",
    "paint_car_surface",
    "paint_wall_surface",
    "build_rubble_wall_surface",
    "rubble_offset_for_size",
    "RUBBLE_ROTATION_DEG",
    "paint_steel_beam_surface",
    "build_fuel_can_surface",
    "build_empty_fuel_can_surface",
    "build_fuel_station_surface",
    "build_flashlight_surface",
    "build_shoes_surface",
    "get_character_icon",
    "get_tile_icon",
]
