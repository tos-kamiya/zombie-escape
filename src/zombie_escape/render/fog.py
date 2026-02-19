from __future__ import annotations

import math
from enum import Enum
from typing import Any

import numpy as np  # type: ignore
import pygame
import pygame.surfarray as pg_surfarray  # type: ignore
from pygame import surface

from ..gameplay_constants import DEFAULT_FLASHLIGHT_SPAWN_COUNT
from ..models import Stage
from ..render_assets import RenderAssets
from .hud import _get_fog_scale


def _max_flashlight_pickups() -> int:
    """Return the maximum flashlight pickups available per stage."""
    return max(1, DEFAULT_FLASHLIGHT_SPAWN_COUNT)


class _FogProfile(Enum):
    DARK0 = (0, (0, 0, 0, 255))
    DARK1 = (1, (0, 0, 0, 255))
    DARK2 = (2, (0, 0, 0, 255))

    def __init__(self, flashlight_count: int, color: tuple[int, int, int, int]) -> None:
        self.flashlight_count = flashlight_count
        self.color = color

    def _scale(self, assets: RenderAssets, _stage: Stage | None) -> float:
        count = max(0, min(self.flashlight_count, _max_flashlight_pickups()))
        return _get_fog_scale(assets, count)

    @staticmethod
    def _from_flashlight_count(count: int) -> "_FogProfile":
        safe_count = max(0, count)
        if safe_count >= 2:
            return _FogProfile.DARK2
        if safe_count == 1:
            return _FogProfile.DARK1
        return _FogProfile.DARK0


def prewarm_fog_overlays(
    fog_data: dict[str, Any],
    assets: RenderAssets,
    *,
    stage: Stage | None = None,
) -> None:
    """Populate fog overlay cache for each reachable flashlight count."""

    for profile in _FogProfile:
        _get_fog_overlay_surfaces(
            fog_data,
            assets,
            profile,
            stage=stage,
        )


def _soften_surface(
    source: surface.Surface,
    scale: float,
) -> surface.Surface:
    """Return a softened copy of a surface using smoothscale down/up."""
    safe_scale = max(0.5, min(1.0, scale))
    if safe_scale >= 0.999:
        return source
    width, height = source.get_size()
    softened_size = (max(1, int(width * safe_scale)), max(1, int(height * safe_scale)))
    softened = pygame.transform.smoothscale(source, softened_size)
    return pygame.transform.smoothscale(softened, (width, height))


def _build_continuous_hatch_surface(
    size: tuple[int, int],
    center: tuple[int, int],
    base_color: tuple[int, int, int, int],
    max_radius: float,
    density_ramps: list[tuple[float, float]],
    spacing: int = 4,
) -> surface.Surface:
    width, height = size
    hatch = pygame.Surface((width, height), pygame.SRCALPHA)
    hatch.fill((base_color[0], base_color[1], base_color[2], 0))

    bayer = [
        [0, 32, 8, 40, 2, 34, 10, 42],
        [48, 16, 56, 24, 50, 18, 58, 26],
        [12, 44, 4, 36, 14, 46, 6, 38],
        [60, 28, 52, 20, 62, 30, 54, 22],
        [3, 35, 11, 43, 1, 33, 9, 41],
        [51, 19, 59, 27, 49, 17, 57, 25],
        [15, 47, 7, 39, 13, 45, 5, 37],
        [63, 31, 55, 23, 61, 29, 53, 21],
    ]
    ramps: list[tuple[float, float, float]] = []
    for ramp_start_ratio, ramp_max_density in density_ramps:
        safe_start = max(0.0, min(1.0, ramp_start_ratio))
        safe_max_density = max(0.0, min(1.0, ramp_max_density))
        start_radius = max(0.0, max_radius * safe_start)
        fade_range = max(1.0, max_radius - start_radius)
        ramps.append((safe_max_density, start_radius, fade_range))
    base_alpha = base_color[3]
    cell_center = (spacing - 1) / 2.0

    cx, cy = center
    alpha_view = pg_surfarray.pixels_alpha(hatch)
    yy, xx = np.indices((height, width))
    dx = xx - cx
    dy = yy - cy
    radius = np.hypot(dx, dy)
    density = np.zeros_like(radius)
    for ramp_max_density, ramp_start, ramp_range in ramps:
        progress = (radius - ramp_start) / ramp_range
        progress = np.clip(progress, 0.0, 1.0)
        density += ramp_max_density * progress
    density = np.clip(density, 0.0, 1.0)
    threshold = (density * 64).astype(np.int32)

    bayer_np = np.array(bayer, dtype=np.int32)
    grid_x = (xx // spacing) % 8
    grid_y = (yy // spacing) % 8
    bayer_vals = bayer_np[grid_y, grid_x]
    mask = bayer_vals < threshold

    dot_radius = np.maximum(1.0, density * spacing)
    local_x = (xx % spacing) - cell_center
    local_y = (yy % spacing) - cell_center
    mask &= (local_x * local_x + local_y * local_y) <= (dot_radius * dot_radius)

    alpha_view[:, :] = (mask.T * base_alpha).astype(np.uint8)
    del alpha_view

    return hatch


def _get_fog_overlay_surfaces(
    fog_data: dict[str, Any],
    assets: RenderAssets,
    profile: _FogProfile,
    *,
    stage: Stage | None = None,
) -> dict[str, Any]:
    overlays = fog_data.setdefault("overlays", {})
    key = profile
    if key in overlays:
        return overlays[key]

    scale = profile._scale(assets, stage)
    max_radius = int(assets.fov_radius * scale)
    padding = 32
    coverage_width = max(assets.screen_width * 2, max_radius * 2)
    coverage_height = max(assets.screen_height * 2, max_radius * 2)
    width = coverage_width + padding * 2
    height = coverage_height + padding * 2
    center = (width // 2, height // 2)

    hard_surface = pygame.Surface((width, height), pygame.SRCALPHA)
    base_color = profile.color
    hard_surface.fill(base_color)
    pygame.draw.circle(hard_surface, (0, 0, 0, 0), center, max_radius)

    ring_surfaces: list[surface.Surface] = []

    combined_surface = hard_surface.copy()
    hatch_surface = _build_continuous_hatch_surface(
        (width, height),
        center,
        base_color,
        max_radius,
        assets.fog_hatch_density_ramps,
    )
    if assets.fog_hatch_soften_scale < 1.0:
        hatch_surface = _soften_surface(
            hatch_surface,
            assets.fog_hatch_soften_scale,
        )
    combined_surface.blit(hatch_surface, (0, 0))

    visible_fade_surface = _build_flashlight_fade_surface(
        (width, height), center, max_radius
    )
    combined_surface.blit(visible_fade_surface, (0, 0))

    overlay_entry = {
        "hard": hard_surface,
        "rings": ring_surfaces,
        "combined": combined_surface,
    }
    overlays[key] = overlay_entry
    return overlay_entry


def _build_flashlight_fade_surface(
    size: tuple[int, int],
    center: tuple[int, int],
    max_radius: int,
    *,
    start_ratio: float = 0.2,
    max_alpha: int = 220,
    outer_extension: int = 30,
) -> surface.Surface:
    """Return a radial gradient so flashlight edges softly darken again."""

    width, height = size
    fade_surface = pygame.Surface((width, height), pygame.SRCALPHA)
    fade_surface.fill((0, 0, 0, 0))

    start_radius = max(0.0, min(max_radius, max_radius * start_ratio))
    end_radius = max(start_radius + 1, max_radius + outer_extension)
    fade_range = max(1.0, end_radius - start_radius)

    alpha_view = None
    if pg_surfarray is not None:
        alpha_view = pg_surfarray.pixels_alpha(fade_surface)
    else:  # pragma: no cover - numpy-less fallback
        fade_surface.lock()

    cx, cy = center
    for y in range(height):
        dy = y - cy
        for x in range(width):
            dx = x - cx
            dist = math.hypot(dx, dy)
            if dist > end_radius:
                dist = end_radius
            if dist <= start_radius:
                alpha = 0
            else:
                progress = min(1.0, (dist - start_radius) / fade_range)
                alpha = int(max_alpha * progress)
            if alpha <= 0:
                continue
            if alpha_view is not None:
                alpha_view[x, y] = alpha
            else:
                fade_surface.set_at((x, y), (0, 0, 0, alpha))

    if alpha_view is not None:
        del alpha_view
    else:  # pragma: no cover
        fade_surface.unlock()

    return fade_surface


def _draw_fog_of_war(
    screen: surface.Surface,
    assets: RenderAssets,
    fog_surfaces: dict[str, Any],
    fov_center_screen: tuple[int, int] | None,
    *,
    stage: Stage | None,
    flashlight_count: int,
    dawn_ready: bool,
) -> None:
    if fov_center_screen is None:
        return
    if stage and stage.endurance_stage and dawn_ready:
        return
    profile = _FogProfile._from_flashlight_count(flashlight_count)
    overlay = _get_fog_overlay_surfaces(
        fog_surfaces,
        assets,
        profile,
        stage=stage,
    )
    combined_surface: surface.Surface = overlay["combined"]
    screen.blit(
        combined_surface,
        combined_surface.get_rect(center=fov_center_screen),
    )
