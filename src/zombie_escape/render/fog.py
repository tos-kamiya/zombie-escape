from __future__ import annotations
from enum import Enum
from typing import Any, Callable

import numpy as np  # type: ignore
import pygame
import pygame.surfarray as pg_surfarray  # type: ignore
from pygame import surface

from ..gameplay_constants import DEFAULT_FLASHLIGHT_SPAWN_COUNT
from ..models import Stage
from ..render_assets import RenderAssets
from .hud import _get_fog_scale


def _build_bayer_matrix(size: int) -> np.ndarray:
    """Build an NxN Bayer threshold matrix where N is a power of two."""
    if size < 2 or (size & (size - 1)) != 0:
        raise ValueError("Bayer matrix size must be a power of two >= 2")
    matrix = np.array([[0, 2], [3, 1]], dtype=np.int32)
    while matrix.shape[0] < size:
        matrix = np.block(
            [
                [4 * matrix + 0, 4 * matrix + 2],
                [4 * matrix + 3, 4 * matrix + 1],
            ]
        )
    return matrix


_BAYER_MATRIX_16 = _build_bayer_matrix(16)


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
    progress_callback: Callable[[int, int], None] | None = None,
) -> None:
    """Populate fog overlay cache for each reachable flashlight count."""

    profiles = list(_FogProfile)
    total = len(profiles)
    for index, profile in enumerate(profiles, start=1):
        _get_fog_overlay_surfaces(
            fog_data,
            assets,
            profile,
            stage=stage,
        )
        if progress_callback is not None:
            progress_callback(index, total)


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

    bayer = _BAYER_MATRIX_16
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
    bayer_size = bayer.shape[0]
    threshold = (density * (bayer_size * bayer_size)).astype(np.int32)
    grid_x = (xx // spacing) % bayer_size
    grid_y = (yy // spacing) % bayer_size
    bayer_vals = bayer[grid_y, grid_x]
    mask = bayer_vals < threshold

    dot_radius = np.maximum(1.0, density * spacing)
    local_x = (xx % spacing) - cell_center
    local_y = (yy % spacing) - cell_center
    mask &= (local_x * local_x + local_y * local_y) <= (dot_radius * dot_radius)

    alpha_view[:, :] = (mask.T * base_alpha).astype(np.uint8)
    del alpha_view

    return hatch


def _build_edge_feather_surface(
    size: tuple[int, int],
    center: tuple[int, int],
    max_radius: int,
    softness_px: int,
) -> surface.Surface:
    """Return a radial alpha feather around the FOV edge."""
    width, height = size
    feather = pygame.Surface((width, height), pygame.SRCALPHA)
    feather.fill((0, 0, 0, 0))
    if softness_px <= 0:
        return feather

    inner_radius = max(0.0, float(max_radius - softness_px))
    outer_radius = float(max_radius + softness_px)
    transition = max(1.0, outer_radius - inner_radius)

    alpha_view = pg_surfarray.pixels_alpha(feather)
    yy, xx = np.indices((height, width))
    dx = xx - center[0]
    dy = yy - center[1]
    dist = np.hypot(dx, dy)
    progress = np.clip((dist - inner_radius) / transition, 0.0, 1.0)
    alpha_view[:, :] = (progress.T * 255).astype(np.uint8)
    del alpha_view
    return feather


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

    aa_scale = max(1, int(assets.fog_layer_aa_scale))
    render_width = max(1, width * aa_scale)
    render_height = max(1, height * aa_scale)
    render_center = (render_width // 2, render_height // 2)
    render_radius = max(1, int(max_radius * aa_scale))

    hard_surface_render = pygame.Surface((render_width, render_height), pygame.SRCALPHA)
    base_color = profile.color
    hard_surface_render.fill(base_color)
    pygame.draw.circle(hard_surface_render, (0, 0, 0, 0), render_center, render_radius)

    ring_surfaces: list[surface.Surface] = []

    combined_surface_render = hard_surface_render.copy()
    edge_feather = _build_edge_feather_surface(
        (render_width, render_height),
        render_center,
        render_radius,
        max(0, int(assets.fog_edge_softness_px * aa_scale)),
    )
    combined_surface_render.blit(edge_feather, (0, 0))
    hatch_surface = _build_continuous_hatch_surface(
        (render_width, render_height),
        render_center,
        base_color,
        render_radius,
        assets.fog_hatch_density_ramps,
        spacing=max(1, 4 * aa_scale),
    )
    if assets.fog_hatch_soften_scale < 1.0:
        hatch_surface = _soften_surface(
            hatch_surface,
            assets.fog_hatch_soften_scale,
        )
    combined_surface_render.blit(hatch_surface, (0, 0))

    visible_fade_surface = _build_flashlight_fade_surface(
        (render_width, render_height),
        render_center,
        render_radius,
        outer_extension=max(1, 30 * aa_scale),
    )
    combined_surface_render.blit(visible_fade_surface, (0, 0))
    if aa_scale > 1:
        hard_surface = pygame.transform.smoothscale(hard_surface_render, (width, height))
        combined_surface = pygame.transform.smoothscale(
            combined_surface_render, (width, height)
        )
    else:
        hard_surface = hard_surface_render
        combined_surface = combined_surface_render

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

    cx, cy = center
    yy, xx = np.indices((height, width))
    dx = xx - cx
    dy = yy - cy
    dist = np.hypot(dx, dy)
    dist = np.minimum(dist, end_radius)
    progress = np.clip((dist - start_radius) / fade_range, 0.0, 1.0)
    alpha = (progress * max_alpha).astype(np.uint8)
    alpha_view = pg_surfarray.pixels_alpha(fade_surface)
    alpha_view[:, :] = alpha.T
    del alpha_view

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
