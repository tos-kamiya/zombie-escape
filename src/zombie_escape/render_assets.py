"""Shared render asset dataclasses used by multiple modules."""

from __future__ import annotations

from dataclasses import dataclass


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


__all__ = ["FogRing", "RenderAssets"]
