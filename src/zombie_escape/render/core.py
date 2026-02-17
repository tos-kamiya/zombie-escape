from __future__ import annotations

import math
from enum import Enum
from typing import TYPE_CHECKING, Any

import pygame
import pygame.surfarray as pg_surfarray  # type: ignore
import numpy as np  # type: ignore
from pygame import sprite, surface

from ..colors import (
    FOOTPRINT_COLOR,
    LIGHT_GRAY,
    WHITE,
    YELLOW,
    get_environment_palette,
)
from ..entities import (
    Camera,
    Player,
)
from ..entities_constants import (
    INTERNAL_WALL_BEVEL_DEPTH,
    MOVING_FLOOR_SPEED,
    PATROL_BOT_COLLISION_RADIUS,
    ZOMBIE_RADIUS,
)
from ..entities_constants import MovingFloorDirection
from ..font_utils import load_font, render_text_surface
from ..gameplay_constants import DEFAULT_FLASHLIGHT_SPAWN_COUNT
from ..screen_constants import FPS
from ..localization import get_font_settings
from ..localization import translate as tr
from ..models import (
    DustRing,
    FallingEntity,
    FuelProgress,
    Footprint,
    GameData,
    Stage,
)
from ..render_assets import (
    RenderAssets,
    build_zombie_directional_surfaces,
    draw_lineformer_direction_arm,
)
from ..render_constants import (
    ENTITY_SHADOW_ALPHA,
    ENTITY_SHADOW_EDGE_SOFTNESS,
    FALLING_DUST_COLOR,
    FALLING_WHIRLWIND_COLOR,
    FALLING_ZOMBIE_COLOR,
    GAMEPLAY_FONT_SIZE,
    MOVING_FLOOR_BORDER_COLOR,
    MOVING_FLOOR_LINE_COLOR,
    MOVING_FLOOR_TILE_COLOR,
    PITFALL_ABYSS_COLOR,
    PITFALL_EDGE_DEPTH_OFFSET,
    PITFALL_EDGE_METAL_COLOR,
    PITFALL_EDGE_STRIPE_COLOR,
    PITFALL_EDGE_STRIPE_SPACING,
    PLAYER_SHADOW_ALPHA_MULT,
    PLAYER_SHADOW_RADIUS_MULT,
    FADE_IN_DURATION_MS,
    ZOMBIE_OUTLINE_COLOR,
)

if TYPE_CHECKING:  # pragma: no cover - typing-only imports
    from ..gameplay.decay_effects import DecayingEntityEffect
from .hud import (
    _build_objective_lines,
    _draw_endurance_timer,
    _draw_hint_indicator,
    _draw_timed_message,
    _draw_inventory_icons,
    _draw_objective,
    _draw_status_bar,
    _draw_survivor_messages,
    _draw_time_accel_indicator,
    _get_fog_scale,
)
from .shadows import (
    draw_entity_shadows_by_mode,
    draw_single_entity_shadow_by_mode,
    _draw_wall_shadows,
    _get_shadow_layer,
)
from .puddle import draw_puddle_rings, get_puddle_phase, get_puddle_wave_color

ELECTRIFIED_FLOOR_ACCENT_COLOR = (216, 200, 90)
ELECTRIFIED_FLOOR_OVERLAY_ALPHA = 26
ELECTRIFIED_FLOOR_BORDER_ALPHA = 140
_PUDDLE_TILE_CACHE: dict[
    tuple[int, tuple[int, int, int], int, bool], surface.Surface
] = {}
_LINEFORMER_MARKER_SURFACES: dict[int, list[surface.Surface]] = {}


def _get_lineformer_marker_surfaces(radius: int) -> list[surface.Surface]:
    cached = _LINEFORMER_MARKER_SURFACES.get(radius)
    if cached is not None:
        return cached
    base_surfaces = build_zombie_directional_surfaces(radius, draw_hands=False)
    bins = len(base_surfaces)
    step = math.tau / bins
    surfaces: list[surface.Surface] = []
    for idx, base_surface in enumerate(base_surfaces):
        marker_surface = base_surface.copy()
        draw_lineformer_direction_arm(
            marker_surface,
            radius=radius,
            angle_rad=idx * step,
            color=ZOMBIE_OUTLINE_COLOR,
        )
        surfaces.append(marker_surface)
    _LINEFORMER_MARKER_SURFACES[radius] = surfaces
    return surfaces


def blit_message(
    screen: surface.Surface,
    text: str,
    size: int,
    color: tuple[int, int, int],
    position: tuple[int, int],
) -> None:
    try:
        font_settings = get_font_settings()
        scaled_size = font_settings.scaled_size(size)
        font = load_font(font_settings.resource, scaled_size)
        text_surface = render_text_surface(
            font, text, color, line_height_scale=font_settings.line_height_scale
        )
        text_rect = text_surface.get_rect(center=position)

        # Add a semi-transparent background rectangle for better visibility
        bg_padding = 15
        bg_rect = text_rect.inflate(bg_padding * 2, bg_padding * 2)
        bg_surface = pygame.Surface((bg_rect.width, bg_rect.height), pygame.SRCALPHA)
        bg_surface.fill((0, 0, 0, 180))  # Black with 180 alpha (out of 255)
        screen.blit(bg_surface, bg_rect.topleft)

        screen.blit(text_surface, text_rect)
    except pygame.error as e:
        print(f"Error rendering font or surface: {e}")


def _draw_fade_in_overlay(screen: surface.Surface, state: GameData | Any) -> None:
    started_at = getattr(state, "fade_in_started_at_ms", None)
    if started_at is None:
        return
    elapsed = max(0, int(state.clock.elapsed_ms) - int(started_at))
    if elapsed <= 0:
        alpha = 255
    else:
        alpha = int(255 * max(0.0, 1.0 - (elapsed / FADE_IN_DURATION_MS)))
    if alpha <= 0:
        return
    overlay = pygame.Surface(screen.get_size())
    overlay.fill((0, 0, 0))
    overlay.set_alpha(alpha)
    screen.blit(overlay, (0, 0))


def _build_moving_floor_pattern(
    direction: MovingFloorDirection,
    cell_size: int,
) -> surface.Surface:
    pattern_size = cell_size * 2
    surface_out = pygame.Surface((pattern_size, pattern_size), pygame.SRCALPHA)
    thickness = 2
    line_color = MOVING_FLOOR_LINE_COLOR
    inset = max(2, int(cell_size * 0.12))
    min_corner = inset
    max_corner = cell_size - inset
    mid = cell_size // 2
    chevron_span = max(3, int(cell_size * 0.12))

    def _draw_chevron(origin_x: int, origin_y: int, center: int) -> None:
        if direction is MovingFloorDirection.UP:
            apex_y = center - chevron_span
            base_y = center + chevron_span
            points = [
                (origin_x + min_corner, origin_y + base_y),
                (origin_x + mid, origin_y + apex_y),
                (origin_x + max_corner, origin_y + base_y),
            ]
        elif direction is MovingFloorDirection.DOWN:
            apex_y = center + chevron_span
            base_y = center - chevron_span
            points = [
                (origin_x + min_corner, origin_y + base_y),
                (origin_x + mid, origin_y + apex_y),
                (origin_x + max_corner, origin_y + base_y),
            ]
        elif direction is MovingFloorDirection.RIGHT:
            apex_x = center + chevron_span
            base_x = center - chevron_span
            points = [
                (origin_x + base_x, origin_y + min_corner),
                (origin_x + apex_x, origin_y + mid),
                (origin_x + base_x, origin_y + max_corner),
            ]
        else:
            apex_x = center - chevron_span
            base_x = center + chevron_span
            points = [
                (origin_x + base_x, origin_y + min_corner),
                (origin_x + apex_x, origin_y + mid),
                (origin_x + base_x, origin_y + max_corner),
            ]

        pygame.draw.lines(surface_out, line_color, False, points, thickness)

    spacing = max(6, cell_size // 2)
    if direction in (MovingFloorDirection.UP, MovingFloorDirection.DOWN):
        for y in range(-spacing, pattern_size + spacing, spacing):
            _draw_chevron(0, 0, y)
    else:
        for x in range(-spacing, pattern_size + spacing, spacing):
            _draw_chevron(0, 0, x)
    return surface_out


def _get_puddle_tile_surface(
    *,
    cell_size: int,
    base_color: tuple[int, int, int],
    phase: int,
    fall_spawn: bool,
) -> surface.Surface:
    key = (
        max(1, int(cell_size)),
        (int(base_color[0]), int(base_color[1]), int(base_color[2])),
        int(phase) % 4,
        bool(fall_spawn),
    )
    cached = _PUDDLE_TILE_CACHE.get(key)
    if cached is not None:
        return cached

    size = key[0]
    puddle_tile = pygame.Surface((size, size), pygame.SRCALPHA)
    tile_rect = puddle_tile.get_rect()

    pygame.draw.rect(puddle_tile, key[1], tile_rect)

    draw_puddle_rings(
        puddle_tile,
        rect=tile_rect,
        phase=key[2],
        color=get_puddle_wave_color(alpha=140),
        width=1,
    )

    _PUDDLE_TILE_CACHE[key] = puddle_tile
    return puddle_tile


def _wrap_long_segment(
    segment: str, font: pygame.font.Font, max_width: int
) -> list[str]:
    lines: list[str] = []
    current = ""
    for char in segment:
        candidate = current + char
        if font.size(candidate)[0] <= max_width or not current:
            current = candidate
        else:
            lines.append(current)
            current = char
    if current:
        lines.append(current)
    return lines


def wrap_text(text: str, font: pygame.font.Font, max_width: int) -> list[str]:
    if max_width <= 0:
        return [text]
    paragraphs = text.splitlines() or [text]
    lines: list[str] = []
    for paragraph in paragraphs:
        if not paragraph:
            lines.append("")
            continue
        words = paragraph.split(" ")
        if len(words) == 1:
            lines.extend(_wrap_long_segment(paragraph, font, max_width))
            continue
        current = ""
        for word in words:
            candidate = f"{current} {word}".strip() if current else word
            if font.size(candidate)[0] <= max_width:
                current = candidate
                continue
            if current:
                lines.append(current)
            if font.size(word)[0] <= max_width:
                current = word
            else:
                lines.extend(_wrap_long_segment(word, font, max_width))
                current = ""
        if current:
            lines.append(current)
    return lines


def blit_text_wrapped(
    target: surface.Surface,
    text: str,
    font: pygame.font.Font,
    color: tuple[int, int, int],
    topleft: tuple[int, int],
    max_width: int,
    *,
    line_height_scale: float = 1.0,
) -> None:
    """Render text with simple wrapping constrained to max_width."""

    x, y = topleft
    line_height = int(round(font.get_linesize() * line_height_scale))
    for line in wrap_text(text, font, max_width):
        if not line:
            y += line_height
            continue
        rendered = render_text_surface(
            font, line, color, line_height_scale=line_height_scale
        )
        target.blit(rendered, (x, y))
        y += line_height


def blit_message_wrapped(
    screen: surface.Surface,
    text: str,
    size: int,
    color: tuple[int, int, int],
    position: tuple[int, int],
    *,
    max_width: int,
    line_spacing: int = 2,
) -> None:
    try:
        font_settings = get_font_settings()
        font = load_font(font_settings.resource, font_settings.scaled_size(size))
        line_height_scale = font_settings.line_height_scale
        lines = wrap_text(text, font, max_width)
        if not lines:
            return
        rendered = [
            render_text_surface(
                font, line, color, line_height_scale=line_height_scale
            )
            for line in lines
        ]
        max_line_width = max(surface.get_width() for surface in rendered)
        line_height = int(round(font.get_linesize() * line_height_scale))
        total_height = line_height * len(rendered) + line_spacing * (len(rendered) - 1)

        center_x, center_y = position
        top = center_y - total_height // 2

        bg_padding = 15
        bg_width = max_line_width + bg_padding * 2
        bg_height = total_height + bg_padding * 2
        bg_rect = pygame.Rect(0, 0, bg_width, bg_height)
        bg_rect.center = (center_x, center_y)
        bg_surface = pygame.Surface((bg_rect.width, bg_rect.height), pygame.SRCALPHA)
        bg_surface.fill((0, 0, 0, 180))
        screen.blit(bg_surface, bg_rect.topleft)

        y = top
        for text_surface in rendered:
            text_rect = text_surface.get_rect(centerx=center_x, y=y)
            screen.blit(text_surface, text_rect)
            y += line_height + line_spacing
    except pygame.error as e:
        print(f"Error rendering font or surface: {e}")


def draw_pause_overlay(
    screen: pygame.Surface,
    *,
    menu_labels: list[str] | None = None,
    selected_index: int = 0,
) -> list[pygame.Rect]:
    screen_width, screen_height = screen.get_size()
    overlay = pygame.Surface((screen_width, screen_height), pygame.SRCALPHA)
    overlay.fill((0, 0, 0, 150))
    pause_radius = 34
    cx = screen_width // 2
    cy = screen_height // 2 - 20
    pygame.draw.circle(
        overlay,
        LIGHT_GRAY,
        (cx, cy),
        pause_radius,
        width=3,
    )
    bar_width = 6
    bar_height = 22
    gap = 8
    pygame.draw.rect(
        overlay,
        LIGHT_GRAY,
        (cx - gap - bar_width, cy - bar_height // 2, bar_width, bar_height),
    )
    pygame.draw.rect(
        overlay,
        LIGHT_GRAY,
        (cx + gap, cy - bar_height // 2, bar_width, bar_height),
    )
    screen.blit(overlay, (0, 0))
    blit_message(
        screen,
        tr("hud.paused"),
        GAMEPLAY_FONT_SIZE,
        WHITE,
        (screen_width // 2, cy - pause_radius - 14),
    )
    option_rects: list[pygame.Rect] = []
    if menu_labels:
        font_settings = get_font_settings()
        menu_font = load_font(font_settings.resource, font_settings.scaled_size(11))
        line_height = int(round(menu_font.get_linesize() * font_settings.line_height_scale))
        row_height = line_height + 6
        menu_width = max(140, int(screen_width * 0.34))
        menu_top = cy + pause_radius + 10
        highlight_color = (70, 70, 70)
        for idx, label in enumerate(menu_labels):
            rect = pygame.Rect(
                screen_width // 2 - menu_width // 2,
                menu_top + idx * row_height,
                menu_width,
                row_height,
            )
            if idx == selected_index:
                pygame.draw.rect(screen, highlight_color, rect)
            text_surface = render_text_surface(
                menu_font,
                label,
                WHITE,
                line_height_scale=font_settings.line_height_scale,
            )
            text_rect = text_surface.get_rect(center=rect.center)
            screen.blit(text_surface, text_rect)
            option_rects.append(rect)
    return option_rects


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

    def _scale(self, assets: RenderAssets, stage: Stage | None) -> float:
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
    ring_scale = scale
    if profile.flashlight_count >= 2:
        ring_scale += max(0.0, assets.flashlight_hatch_extra_scale)
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


def _draw_fall_whirlwind(
    screen: surface.Surface,
    camera: Camera,
    center: tuple[int, int],
    progress: float,
    *,
    scale: float = 1.0,
) -> None:
    base_alpha = FALLING_WHIRLWIND_COLOR[3]
    alpha = int(max(0, min(255, base_alpha * (1.0 - progress))))
    if alpha <= 0:
        return
    color = (
        FALLING_WHIRLWIND_COLOR[0],
        FALLING_WHIRLWIND_COLOR[1],
        FALLING_WHIRLWIND_COLOR[2],
        alpha,
    )
    safe_scale = max(0.4, scale)
    swirl_radius = max(2, int(ZOMBIE_RADIUS * 1.1 * safe_scale))
    offset = max(1, int(ZOMBIE_RADIUS * 0.6 * safe_scale))
    size = swirl_radius * 4
    swirl = pygame.Surface((size, size), pygame.SRCALPHA)
    cx = cy = size // 2
    for idx in range(2):
        angle = progress * math.tau * 0.3 + idx * (math.tau / 2)
        ox = int(math.cos(angle) * offset)
        oy = int(math.sin(angle) * offset)
        pygame.draw.circle(swirl, color, (cx + ox, cy + oy), swirl_radius, width=2)
    world_rect = pygame.Rect(0, 0, 1, 1)
    world_rect.center = center
    screen_center = camera.apply_rect(world_rect).center
    screen.blit(swirl, swirl.get_rect(center=screen_center))


def _draw_falling_fx(
    screen: surface.Surface,
    camera: Camera,
    falling_zombies: list[FallingEntity],
    flashlight_count: int,
    dust_rings: list[DustRing],
    now_ms: int,
) -> None:
    if not falling_zombies and not dust_rings:
        return
    now = now_ms
    for fall in falling_zombies:
        pre_fx_ms = max(0, fall.pre_fx_ms)
        fall_duration_ms = max(1, fall.fall_duration_ms)
        fall_start = fall.started_at_ms + pre_fx_ms
        impact_at = fall_start + fall_duration_ms
        if now < fall_start:
            if flashlight_count > 0 and pre_fx_ms > 0:
                fx_progress = max(0.0, min(1.0, (now - fall.started_at_ms) / pre_fx_ms))
                # Make the premonition grow with the impending drop scale.
                pre_scale = 1.0 + (0.9 * fx_progress)
                _draw_fall_whirlwind(
                    screen,
                    camera,
                    fall.start_pos,
                    fx_progress,
                    scale=pre_scale,
                )
            continue
        if now >= impact_at:
            continue
        fall_progress = max(0.0, min(1.0, (now - fall_start) / fall_duration_ms))

        if getattr(fall, "mode", "spawn") == "pitfall":
            scale = 1.0 - fall_progress
            scale = scale * scale
            y_offset = 0.0
        else:
            eased = 1.0 - (1.0 - fall_progress) * (1.0 - fall_progress)
            scale = 2.0 - (1.0 * eased)
            # Add an extra vertical drop from above (1.5x wall depth)
            y_offset = -INTERNAL_WALL_BEVEL_DEPTH * 1.5 * (1.0 - eased)

        radius = ZOMBIE_RADIUS * scale
        cx = fall.target_pos[0]
        cy = fall.target_pos[1] + ZOMBIE_RADIUS - radius + y_offset

        world_rect = pygame.Rect(0, 0, radius * 2, radius * 2)
        world_rect.center = (int(cx), int(cy))
        screen_rect = camera.apply_rect(world_rect)
        pygame.draw.circle(
            screen,
            FALLING_ZOMBIE_COLOR,
            screen_rect.center,
            max(1, int(screen_rect.width / 2)),
        )

    for ring in list(dust_rings):
        elapsed = now - ring.started_at_ms
        if elapsed >= ring.duration_ms:
            dust_rings.remove(ring)
            continue
        progress = max(0.0, min(1.0, elapsed / ring.duration_ms))
        alpha = int(max(0, min(255, FALLING_DUST_COLOR[3] * (1.0 - progress))))
        if alpha <= 0:
            continue
        radius = int(ZOMBIE_RADIUS * (0.7 + progress * 1.9))
        color = (
            FALLING_DUST_COLOR[0],
            FALLING_DUST_COLOR[1],
            FALLING_DUST_COLOR[2],
            alpha,
        )
        world_rect = pygame.Rect(0, 0, 1, 1)
        world_rect.center = ring.pos
        screen_center = camera.apply_rect(world_rect).center
        pygame.draw.circle(screen, color, screen_center, radius, width=2)


def _draw_decay_fx(
    screen: surface.Surface,
    camera: Camera,
    decay_effects: list["DecayingEntityEffect"],
) -> None:
    if not decay_effects:
        return
    for effect in decay_effects:
        screen.blit(effect.surface, camera.apply_rect(effect.rect))


def _draw_play_area(
    screen: surface.Surface,
    camera: Camera,
    assets: RenderAssets,
    palette: Any,
    field_rect: pygame.Rect,
    outside_cells: set[tuple[int, int]],
    fall_spawn_cells: set[tuple[int, int]],
    pitfall_cells: set[tuple[int, int]],
    puddle_cells: set[tuple[int, int]],
    moving_floor_cells: dict[tuple[int, int], MovingFloorDirection],
    electrified_cells: set[tuple[int, int]],
    cell_size: int,
    *,
    elapsed_ms: int,
) -> tuple[int, int, int, int, set[tuple[int, int]]]:
    grid_snap = assets.internal_wall_grid_snap
    xs, ys, xe, ye = (
        field_rect.left,
        field_rect.top,
        field_rect.right,
        field_rect.bottom,
    )
    xs //= grid_snap
    ys //= grid_snap
    xe //= grid_snap
    ye //= grid_snap

    play_area_rect = pygame.Rect(
        xs * grid_snap,
        ys * grid_snap,
        (xe - xs) * grid_snap,
        (ye - ys) * grid_snap,
    )
    play_area_screen_rect = camera.apply_rect(play_area_rect)
    pygame.draw.rect(screen, palette.floor_primary, play_area_screen_rect)

    view_world = pygame.Rect(
        -camera.camera.x,
        -camera.camera.y,
        assets.screen_width,
        assets.screen_height,
    )
    margin = grid_snap * 2
    view_world.inflate_ip(margin * 2, margin * 2)
    min_world_x = max(xs * grid_snap, view_world.left)
    max_world_x = min(xe * grid_snap, view_world.right)
    min_world_y = max(ys * grid_snap, view_world.top)
    max_world_y = min(ye * grid_snap, view_world.bottom)
    start_x = max(xs, int(min_world_x // grid_snap))
    end_x = min(xe, int(math.ceil(max_world_x / grid_snap)))
    start_y = max(ys, int(min_world_y // grid_snap))
    end_y = min(ye, int(math.ceil(max_world_y / grid_snap)))

    base_offset_px = (elapsed_ms / 1000.0) * MOVING_FLOOR_SPEED * FPS
    pattern_cache: dict[MovingFloorDirection, surface.Surface] = {}
    screen_rect = screen.get_rect()

    for y in range(start_y, end_y):
        for x in range(start_x, end_x):
            if (x, y) in outside_cells:
                lx, ly = (
                    x * grid_snap,
                    y * grid_snap,
                )
                r = pygame.Rect(
                    lx,
                    ly,
                    grid_snap,
                    grid_snap,
                )
                sr = camera.apply_rect(r)
                if sr.colliderect(screen_rect):
                    pygame.draw.rect(screen, palette.outside, sr)
                continue

            direction = moving_floor_cells.get((x, y))
            if direction is not None:
                use_secondary = ((x // 2) + (y // 2)) % 2 == 0
                lx, ly = (
                    x * grid_snap,
                    y * grid_snap,
                )
                r = pygame.Rect(
                    lx,
                    ly,
                    grid_snap,
                    grid_snap,
                )
                sr = camera.apply_rect(r)
                if sr.colliderect(screen_rect):
                    if (x, y) in fall_spawn_cells:
                        color = (
                            palette.fall_zone_secondary
                            if use_secondary
                            else palette.fall_zone_primary
                        )
                        pygame.draw.rect(screen, color, sr)
                    elif use_secondary:
                        pygame.draw.rect(screen, palette.floor_secondary, sr)
                    inset = 4
                    inner_rect = sr.inflate(-2 * inset, -2 * inset)
                    pygame.draw.rect(screen, MOVING_FLOOR_TILE_COLOR, inner_rect)
                    pattern = pattern_cache.get(direction)
                    if pattern is None:
                        pattern = _build_moving_floor_pattern(direction, grid_snap)
                        pattern_cache[direction] = pattern
                    signed_offset = (
                        base_offset_px
                        if direction
                        in (MovingFloorDirection.UP, MovingFloorDirection.LEFT)
                        else -base_offset_px
                    )
                    offset_px = int(signed_offset % grid_snap)
                    clip_prev = screen.get_clip()
                    screen.set_clip(inner_rect)
                    if direction in (MovingFloorDirection.UP, MovingFloorDirection.DOWN):
                        blit_pos = (sr.left, sr.top - offset_px)
                    else:
                        blit_pos = (sr.left - offset_px, sr.top)
                    screen.blit(pattern, blit_pos)
                    screen.set_clip(clip_prev)
                    border_rect = inner_rect
                    pygame.draw.rect(
                        screen,
                        MOVING_FLOOR_BORDER_COLOR,
                        border_rect,
                        width=3,
                        border_radius=4,
                    )
                continue

            if (x, y) in pitfall_cells:
                lx, ly = (
                    x * grid_snap,
                    y * grid_snap,
                )
                r = pygame.Rect(
                    lx,
                    ly,
                    grid_snap,
                    grid_snap,
                )
                sr = camera.apply_rect(r)
                if not sr.colliderect(screen_rect):
                    continue
                pygame.draw.rect(screen, PITFALL_ABYSS_COLOR, sr)

                if (x, y - 1) not in pitfall_cells:
                    edge_h = max(
                        1, INTERNAL_WALL_BEVEL_DEPTH - PITFALL_EDGE_DEPTH_OFFSET
                    )
                    pygame.draw.rect(
                        screen, PITFALL_EDGE_METAL_COLOR, (sr.x, sr.y, sr.w, edge_h)
                    )
                    for sx in range(
                        sr.x - edge_h, sr.right, PITFALL_EDGE_STRIPE_SPACING
                    ):
                        pygame.draw.line(
                            screen,
                            PITFALL_EDGE_STRIPE_COLOR,
                            (max(sr.x, sx), sr.y),
                            (min(sr.right - 1, sx + edge_h), sr.y + edge_h - 1),
                            width=2,
                        )

                continue

            use_secondary = ((x // 2) + (y // 2)) % 2 == 0
            if (x, y) in fall_spawn_cells:
                base_color = (
                    palette.fall_zone_secondary
                    if use_secondary
                    else palette.fall_zone_primary
                )
            elif use_secondary:
                base_color = palette.floor_secondary
            else:
                base_color = palette.floor_primary

            if (x, y) in puddle_cells:
                lx, ly = (
                    x * grid_snap,
                    y * grid_snap,
                )
                r = pygame.Rect(
                    lx,
                    ly,
                    grid_snap,
                    grid_snap,
                )
                sr = camera.apply_rect(r)
                if sr.colliderect(screen_rect):
                    puddle_tile = _get_puddle_tile_surface(
                        cell_size=grid_snap,
                        base_color=base_color,
                        phase=get_puddle_phase(elapsed_ms, x, y, cycle_ms=400),
                        fall_spawn=((x, y) in fall_spawn_cells),
                    )
                    screen.blit(puddle_tile, sr.topleft)
                continue

            if (x, y) in fall_spawn_cells:
                color = (
                    palette.fall_zone_secondary
                    if use_secondary
                    else palette.fall_zone_primary
                )
            elif not use_secondary:
                continue
            else:
                color = palette.floor_secondary
            lx, ly = (
                x * grid_snap,
                y * grid_snap,
            )
            r = pygame.Rect(
                lx,
                ly,
                grid_snap,
                grid_snap,
            )
            sr = camera.apply_rect(r)
            if sr.colliderect(screen_rect):
                pygame.draw.rect(screen, color, sr)

    if cell_size > 0 and electrified_cells:
        for cell_x, cell_y in electrified_cells:
            world_rect = pygame.Rect(
                cell_x * cell_size,
                cell_y * cell_size,
                cell_size,
                cell_size,
            )
            sr = camera.apply_rect(world_rect)
            if sr.colliderect(screen_rect):
                inner_rect = sr.inflate(-2, -2)
                if inner_rect.width > 0 and inner_rect.height > 0:
                    overlay = pygame.Surface(
                        (inner_rect.width, inner_rect.height), pygame.SRCALPHA
                    )
                    overlay.fill(
                        (
                            ELECTRIFIED_FLOOR_ACCENT_COLOR[0],
                            ELECTRIFIED_FLOOR_ACCENT_COLOR[1],
                            ELECTRIFIED_FLOOR_ACCENT_COLOR[2],
                            ELECTRIFIED_FLOOR_OVERLAY_ALPHA,
                        )
                    )
                    screen.blit(overlay, inner_rect.topleft)
                if sr.width > 0 and sr.height > 0:
                    border_surface = pygame.Surface((sr.width, sr.height), pygame.SRCALPHA)
                    pygame.draw.rect(
                        border_surface,
                        (
                            ELECTRIFIED_FLOOR_ACCENT_COLOR[0],
                            ELECTRIFIED_FLOOR_ACCENT_COLOR[1],
                            ELECTRIFIED_FLOOR_ACCENT_COLOR[2],
                            ELECTRIFIED_FLOOR_BORDER_ALPHA,
                        ),
                        border_surface.get_rect(),
                        width=1,
                    )
                    screen.blit(border_surface, sr.topleft)

    return xs, ys, xe, ye, outside_cells


def _draw_footprints(
    screen: surface.Surface,
    camera: Camera,
    assets: RenderAssets,
    footprints: list[Footprint],
    *,
    config: dict[str, Any],
    now_ms: int,
) -> None:
    if not config.get("footprints", {}).get("enabled", True):
        return
    now = now_ms
    for fp in footprints:
        if not fp.visible:
            continue
        age = now - fp.time
        fade = 1 - (age / assets.footprint_lifetime_ms)
        fade = max(assets.footprint_min_fade, fade)
        color = tuple(max(0, min(255, int(c * fade))) for c in FOOTPRINT_COLOR)
        fp_rect = pygame.Rect(
            fp.pos[0] - assets.footprint_radius,
            fp.pos[1] - assets.footprint_radius,
            assets.footprint_radius * 2,
            assets.footprint_radius * 2,
        )
        sr = camera.apply_rect(fp_rect)
        if sr.colliderect(screen.get_rect().inflate(30, 30)):
            pygame.draw.circle(screen, color, sr.center, assets.footprint_radius)


def _draw_entities(
    screen: surface.Surface,
    camera: Camera,
    all_sprites: sprite.LayeredUpdates,
    player: Player,
    *,
    has_fuel: bool,
    has_empty_fuel_can: bool,
    show_fuel_indicator: bool,
) -> pygame.Rect:
    screen_rect_inflated = screen.get_rect().inflate(100, 100)
    player_screen_rect: pygame.Rect | None = None
    for entity in all_sprites:
        sprite_screen_rect = camera.apply_rect(entity.rect)
        if sprite_screen_rect.colliderect(screen_rect_inflated):
            screen.blit(entity.image, sprite_screen_rect)
        if entity is player:
            player_screen_rect = sprite_screen_rect
            if show_fuel_indicator:
                _draw_fuel_indicator(
                    screen,
                    player_screen_rect,
                    has_fuel=has_fuel,
                    has_empty_fuel_can=has_empty_fuel_can,
                    in_car=player.in_car,
                )
    return player_screen_rect or camera.apply_rect(player.rect)


def _draw_lineformer_train_markers(
    screen: surface.Surface,
    camera: Camera,
    marker_draw_data: list[tuple[float, float, float]],
) -> None:
    if not marker_draw_data:
        return
    marker_radius = max(2, int(ZOMBIE_RADIUS))
    marker_surfaces = _get_lineformer_marker_surfaces(marker_radius)
    bins = len(marker_surfaces)
    angle_step = math.tau / bins
    screen_rect_inflated = screen.get_rect().inflate(100, 100)
    for world_x, world_y, angle_rad in marker_draw_data:
        bin_idx = int(round(angle_rad / angle_step)) % bins
        marker_image = marker_surfaces[bin_idx]
        world_center = pygame.Rect(
            int(round(world_x)),
            int(round(world_y)),
            0,
            0,
        )
        screen_center = camera.apply_rect(world_center).topleft
        marker_rect = marker_image.get_rect(center=screen_center)
        if not marker_rect.colliderect(screen_rect_inflated):
            continue
        screen.blit(marker_image, marker_rect)


def _draw_fuel_indicator(
    screen: surface.Surface,
    player_screen_rect: pygame.Rect,
    *,
    has_fuel: bool,
    has_empty_fuel_can: bool,
    in_car: bool,
) -> None:
    if in_car:
        return
    if not has_fuel and not has_empty_fuel_can:
        return
    indicator_size = 4
    padding = 1
    indicator_rect = pygame.Rect(
        player_screen_rect.right - indicator_size - padding,
        player_screen_rect.bottom - indicator_size - padding,
        indicator_size,
        indicator_size,
    )
    if has_fuel:
        fill_color = YELLOW
        border_color = (180, 160, 40)
    else:
        fill_color = (235, 235, 235)
        border_color = (180, 180, 180)
    pygame.draw.rect(screen, fill_color, indicator_rect)
    pygame.draw.rect(screen, border_color, indicator_rect, width=1)


def _draw_fog_of_war(
    screen: surface.Surface,
    camera: Camera,
    assets: RenderAssets,
    fog_surfaces: dict[str, Any],
    fov_target: pygame.sprite.Sprite | None,
    *,
    stage: Stage | None,
    flashlight_count: int,
    dawn_ready: bool,
) -> None:
    if fov_target is None:
        return
    if stage and stage.endurance_stage and dawn_ready:
        return
    fov_center_tuple = tuple(map(int, camera.apply(fov_target).center))
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
        combined_surface.get_rect(center=fov_center_tuple),
    )


def draw(
    assets: RenderAssets,
    screen: surface.Surface,
    game_data: GameData,
    *,
    config: dict[str, Any],
    hint_target: tuple[int, int] | None = None,
    hint_color: tuple[int, int, int] | None = None,
    fps: float | None = None,
) -> None:
    hint_color = hint_color or YELLOW
    state = game_data.state
    player = game_data.player
    if player is None:
        raise ValueError("draw requires an active player on game_data")

    camera = game_data.camera
    stage = game_data.stage
    outside_cells = game_data.layout.outside_cells
    all_sprites = game_data.groups.all_sprites
    has_fuel = state.fuel_progress == FuelProgress.FULL_CAN
    has_empty_fuel_can = state.fuel_progress == FuelProgress.EMPTY_CAN
    flashlight_count = state.flashlight_count
    active_car = game_data.car if game_data.car and game_data.car.alive() else None
    if player.in_car and game_data.car and game_data.car.alive():
        fov_target = game_data.car
    else:
        fov_target = player

    palette = get_environment_palette(state.ambient_palette_key)
    screen.fill(palette.outside)

    _draw_play_area(
        screen,
        camera,
        assets,
        palette,
        game_data.layout.field_rect,
        outside_cells,
        game_data.layout.fall_spawn_cells,
        game_data.layout.pitfall_cells,
        game_data.layout.puddle_cells,
        game_data.layout.moving_floor_cells,
        state.electrified_cells,
        game_data.cell_size,
        elapsed_ms=int(state.clock.elapsed_ms),
    )
    shadows_enabled = config.get("visual", {}).get("shadows", {}).get("enabled", True)
    if shadows_enabled:
        dawn_shadow_mode = bool(stage and stage.endurance_stage and state.dawn_ready)
        lsp = (
            None if dawn_shadow_mode else (fov_target.rect.center if fov_target else None)
        )
        light_source_pos: tuple[float, float] | None = (float(lsp[0]), float(lsp[1])) if lsp is not None else None
        shadow_layer = _get_shadow_layer(screen.get_size())
        shadow_layer.fill((0, 0, 0, 0))
        drew_shadow = _draw_wall_shadows(
            shadow_layer,
            camera,
            wall_cells=game_data.layout.wall_cells,
            wall_group=game_data.groups.wall_group,
            outer_wall_cells=game_data.layout.outer_wall_cells,
            cell_size=game_data.cell_size,
            light_source_pos=light_source_pos,
        )
        drew_shadow |= draw_entity_shadows_by_mode(
            shadow_layer,
            camera,
            all_sprites,
            dawn_shadow_mode=dawn_shadow_mode,
            light_source_pos=light_source_pos,
            exclude_car=active_car if player.in_car else None,
            outside_cells=outside_cells,
            cell_size=game_data.cell_size,
            flashlight_count=flashlight_count,
        )
        # Patrol bot shadows: low profile, small offset, slightly larger than body.
        patrol_bots = game_data.groups.patrol_bot_group
        if patrol_bots:
            bot_radius = max(1, int(PATROL_BOT_COLLISION_RADIUS * 1.2))
            bot_alpha = max(1, int(ENTITY_SHADOW_ALPHA * 0.6))
            for bot in patrol_bots:
                if not bot.alive():
                    continue
                drew_shadow |= draw_single_entity_shadow_by_mode(
                    shadow_layer,
                    camera,
                    entity=bot,
                    dawn_shadow_mode=dawn_shadow_mode,
                    light_source_pos=light_source_pos,
                    outside_cells=outside_cells,
                    cell_size=game_data.cell_size,
                    shadow_radius=bot_radius,
                    alpha=bot_alpha,
                    edge_softness=ENTITY_SHADOW_EDGE_SOFTNESS,
                    offset_scale=1 / 3,
                )
        player_shadow_alpha = max(
            1, int(ENTITY_SHADOW_ALPHA * PLAYER_SHADOW_ALPHA_MULT)
        )
        player_shadow_radius = int(ZOMBIE_RADIUS * PLAYER_SHADOW_RADIUS_MULT)
        car_shadow_radius = player_shadow_radius
        if active_car is not None:
            car_shadow_radius = max(
                1, int(min(active_car.rect.width, active_car.rect.height) * 0.5 * 1.2)
            )
        if player.in_car:
            drew_shadow |= draw_single_entity_shadow_by_mode(
                shadow_layer,
                camera,
                entity=active_car,
                dawn_shadow_mode=dawn_shadow_mode,
                light_source_pos=light_source_pos,
                outside_cells=outside_cells,
                cell_size=game_data.cell_size,
                shadow_radius=car_shadow_radius,
                alpha=player_shadow_alpha,
            )
        else:
            drew_shadow |= draw_single_entity_shadow_by_mode(
                shadow_layer,
                camera,
                entity=player,
                dawn_shadow_mode=dawn_shadow_mode,
                light_source_pos=light_source_pos,
                outside_cells=outside_cells,
                cell_size=game_data.cell_size,
                shadow_radius=player_shadow_radius,
                alpha=player_shadow_alpha,
            )
        if drew_shadow:
            screen.blit(shadow_layer, (0, 0))
    _draw_footprints(
        screen,
        camera,
        assets,
        state.footprints,
        config=config,
        now_ms=state.clock.elapsed_ms,
    )
    _draw_entities(
        screen,
        camera,
        all_sprites,
        player,
        has_fuel=has_fuel,
        has_empty_fuel_can=has_empty_fuel_can,
        show_fuel_indicator=not (stage and stage.endurance_stage),
    )
    _draw_lineformer_train_markers(
        screen,
        camera,
        game_data.lineformer_trains.iter_marker_draw_data(game_data.groups.zombie_group),
    )

    _draw_decay_fx(
        screen,
        camera,
        state.decay_effects,
    )

    _draw_falling_fx(
        screen,
        camera,
        state.falling_zombies,
        state.flashlight_count,
        state.dust_rings,
        state.clock.elapsed_ms,
    )

    _draw_hint_indicator(
        screen,
        camera,
        assets,
        player,
        hint_target,
        hint_color=hint_color,
        stage=stage,
        flashlight_count=flashlight_count,
    )
    _draw_fog_of_war(
        screen,
        camera,
        assets,
        game_data.fog,
        fov_target,
        stage=stage,
        flashlight_count=flashlight_count,
        dawn_ready=state.dawn_ready,
    )

    objective_lines = _build_objective_lines(
        stage=stage,
        state=state,
        player=player,
        active_car=active_car,
        fuel_progress=state.fuel_progress,
        buddy_merged_count=state.buddy_merged_count,
        buddy_required=stage.buddy_required_count if stage else 0,
    )
    if objective_lines:
        _draw_objective(objective_lines, screen=screen)
    _draw_inventory_icons(
        screen,
        assets,
        has_fuel=has_fuel,
        has_empty_fuel_can=has_empty_fuel_can,
        flashlight_count=flashlight_count,
        shoes_count=state.shoes_count,
        player_in_car=player.in_car,
        buddy_onboard=state.buddy_onboard,
        survivors_onboard=state.survivors_onboard,
        passenger_capacity=state.survivor_capacity,
    )
    _draw_survivor_messages(screen, assets, list(state.survivor_messages))
    _draw_endurance_timer(screen, assets, stage=stage, state=state)
    _draw_time_accel_indicator(screen, assets, stage=stage, state=state)
    _draw_status_bar(
        screen,
        assets,
        config,
        stage=stage,
        seed=state.seed,
        debug_mode=state.debug_mode,
        zombie_group=game_data.groups.zombie_group,
        lineformer_marker_count=game_data.lineformer_trains.total_marker_count(),
        falling_spawn_carry=state.falling_spawn_carry,
        show_fps=state.show_fps,
        fps=fps,
    )

    _draw_fade_in_overlay(screen, state)
    _draw_timed_message(
        screen,
        assets,
        message=state.timed_message,
        elapsed_play_ms=state.clock.elapsed_ms,
    )
