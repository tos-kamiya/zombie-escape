from __future__ import annotations

import math
from enum import Enum
from typing import Any

import pygame
import pygame.surfarray as pg_surfarray  # type: ignore
from pygame import sprite, surface

from .colors import (
    BLACK,
    BLUE,
    FOOTPRINT_COLOR,
    LIGHT_GRAY,
    ORANGE,
    WHITE,
    YELLOW,
    get_environment_palette,
)
from .entities import (
    Camera,
    Car,
    Flashlight,
    FuelCan,
    Player,
    Shoes,
    SteelBeam,
    Survivor,
    Wall,
    Zombie,
)
from .entities_constants import (
    INTERNAL_WALL_BEVEL_DEPTH,
    JUMP_SHADOW_OFFSET,
    ZOMBIE_RADIUS,
)
from .font_utils import load_font
from .gameplay_constants import DEFAULT_FLASHLIGHT_SPAWN_COUNT
from .localization import get_font_settings
from .localization import translate as tr
from .models import DustRing, FallingZombie, Footprint, GameData, Stage
from .render_assets import RenderAssets, resolve_steel_beam_colors, resolve_wall_colors
from .render_constants import (
    ENTITY_SHADOW_ALPHA,
    ENTITY_SHADOW_EDGE_SOFTNESS,
    ENTITY_SHADOW_RADIUS_MULT,
    FALLING_DUST_COLOR,
    FALLING_WHIRLWIND_COLOR,
    FALLING_ZOMBIE_COLOR,
    PITFALL_ABYSS_COLOR,
    PITFALL_EDGE_DEPTH_OFFSET,
    PITFALL_EDGE_METAL_COLOR,
    PITFALL_EDGE_STRIPE_COLOR,
    PITFALL_EDGE_STRIPE_SPACING,
    PLAYER_SHADOW_ALPHA_MULT,
    PLAYER_SHADOW_RADIUS_MULT,
    SHADOW_MIN_RATIO,
    SHADOW_OVERSAMPLE,
    SHADOW_RADIUS_RATIO,
    SHADOW_STEPS,
)
from .render_hud import (
    _build_objective_lines,
    _draw_endurance_timer,
    _draw_hint_indicator,
    _draw_inventory_icons,
    _draw_objective,
    _draw_status_bar,
    _draw_survivor_messages,
    _draw_time_accel_indicator,
    _get_fog_scale,
)

_SHADOW_TILE_CACHE: dict[tuple[int, int, float], surface.Surface] = {}
_SHADOW_LAYER_CACHE: dict[tuple[int, int], surface.Surface] = {}
_SHADOW_CIRCLE_CACHE: dict[tuple[int, int, float], surface.Surface] = {}


def _get_shadow_tile_surface(
    cell_size: int,
    alpha: int,
    *,
    edge_softness: float = 0.35,
) -> surface.Surface:
    key = (max(1, cell_size), max(0, min(255, alpha)), edge_softness)
    if key in _SHADOW_TILE_CACHE:
        return _SHADOW_TILE_CACHE[key]
    size = key[0]
    oversample = SHADOW_OVERSAMPLE
    render_size = size * oversample
    render_surf = pygame.Surface((render_size, render_size), pygame.SRCALPHA)
    base_alpha = key[1]
    if edge_softness <= 0:
        render_surf.fill((0, 0, 0, base_alpha))
        if oversample > 1:
            surf = pygame.transform.smoothscale(render_surf, (size, size))
        else:
            surf = render_surf
        _SHADOW_TILE_CACHE[key] = surf
        return surf

    softness = max(0.0, min(1.0, edge_softness))
    fade_band = max(1, int(render_size * softness))
    base_radius = max(1, int(render_size * SHADOW_RADIUS_RATIO))

    render_surf.fill((0, 0, 0, 0))
    steps = SHADOW_STEPS
    min_ratio = SHADOW_MIN_RATIO
    for idx in range(steps):
        t = idx / (steps - 1) if steps > 1 else 1.0
        inset = int(fade_band * t)
        rect_size = render_size - inset * 2
        if rect_size <= 0:
            continue
        radius = max(0, base_radius - inset)
        layer_alpha = int(base_alpha * (min_ratio + (1.0 - min_ratio) * t))
        pygame.draw.rect(
            render_surf,
            (0, 0, 0, layer_alpha),
            pygame.Rect(inset, inset, rect_size, rect_size),
            border_radius=radius,
        )

    if oversample > 1:
        surf = pygame.transform.smoothscale(render_surf, (size, size))
    else:
        surf = render_surf
    _SHADOW_TILE_CACHE[key] = surf
    return surf


def _get_shadow_layer(size: tuple[int, int]) -> surface.Surface:
    key = (max(1, size[0]), max(1, size[1]))
    if key in _SHADOW_LAYER_CACHE:
        return _SHADOW_LAYER_CACHE[key]
    layer = pygame.Surface(key, pygame.SRCALPHA)
    _SHADOW_LAYER_CACHE[key] = layer
    return layer


def _get_shadow_circle_surface(
    radius: int,
    alpha: int,
    *,
    edge_softness: float = 0.12,
) -> surface.Surface:
    key = (max(1, radius), max(0, min(255, alpha)), edge_softness)
    if key in _SHADOW_CIRCLE_CACHE:
        return _SHADOW_CIRCLE_CACHE[key]
    radius = key[0]
    oversample = SHADOW_OVERSAMPLE
    render_radius = radius * oversample
    render_size = render_radius * 2
    render_surf = pygame.Surface((render_size, render_size), pygame.SRCALPHA)
    base_alpha = key[1]
    if edge_softness <= 0:
        pygame.draw.circle(
            render_surf,
            (0, 0, 0, base_alpha),
            (render_radius, render_radius),
            render_radius,
        )
        if oversample > 1:
            surf = pygame.transform.smoothscale(render_surf, (radius * 2, radius * 2))
        else:
            surf = render_surf
        _SHADOW_CIRCLE_CACHE[key] = surf
        return surf

    softness = max(0.0, min(1.0, edge_softness))
    fade_band = max(1, int(render_radius * softness))
    steps = SHADOW_STEPS
    min_ratio = SHADOW_MIN_RATIO
    render_surf.fill((0, 0, 0, 0))
    for idx in range(steps):
        t = idx / (steps - 1) if steps > 1 else 1.0
        inset = int(fade_band * t)
        circle_radius = render_radius - inset
        if circle_radius <= 0:
            continue
        layer_alpha = int(base_alpha * (min_ratio + (1.0 - min_ratio) * t))
        pygame.draw.circle(
            render_surf,
            (0, 0, 0, layer_alpha),
            (render_radius, render_radius),
            circle_radius,
        )

    if oversample > 1:
        surf = pygame.transform.smoothscale(render_surf, (radius * 2, radius * 2))
    else:
        surf = render_surf
    _SHADOW_CIRCLE_CACHE[key] = surf
    return surf


def show_message(
    screen: surface.Surface,
    text: str,
    size: int,
    color: tuple[int, int, int],
    position: tuple[int, int],
) -> None:
    try:
        font_settings = get_font_settings()
        font = load_font(font_settings.resource, font_settings.scaled_size(size))
        text_surface = font.render(text, False, color)
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


def wrap_long_segment(segment: str, font: pygame.font.Font, max_width: int) -> list[str]:
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
            lines.extend(wrap_long_segment(paragraph, font, max_width))
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
                lines.extend(wrap_long_segment(word, font, max_width))
                current = ""
        if current:
            lines.append(current)
    return lines


def blit_wrapped_text(
    target: surface.Surface,
    text: str,
    font: pygame.font.Font,
    color: tuple[int, int, int],
    topleft: tuple[int, int],
    max_width: int,
) -> None:
    """Render text with simple wrapping constrained to max_width."""

    x, y = topleft
    line_height = font.get_linesize()
    for line in wrap_text(text, font, max_width):
        if not line:
            y += line_height
            continue
        rendered = font.render(line, False, color)
        target.blit(rendered, (x, y))
        y += line_height


def show_message_wrapped(
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
        lines = wrap_text(text, font, max_width)
        if not lines:
            return
        rendered = [font.render(line, False, color) for line in lines]
        max_line_width = max(surface.get_width() for surface in rendered)
        line_height = font.get_linesize()
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


def draw_pause_overlay(screen: pygame.Surface) -> None:
    screen_width, screen_height = screen.get_size()
    overlay = pygame.Surface((screen_width, screen_height), pygame.SRCALPHA)
    overlay.fill((0, 0, 0, 150))
    pause_radius = 53
    cx = screen_width // 2
    cy = screen_height // 2 - 18
    pygame.draw.circle(
        overlay,
        LIGHT_GRAY,
        (cx, cy),
        pause_radius,
        width=3,
    )
    bar_width = 10
    bar_height = 38
    gap = 12
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
    show_message(
        screen,
        tr("hud.paused"),
        18,
        WHITE,
        (screen_width // 2, 28),
    )
    show_message(
        screen,
        tr("hud.pause_hint"),
        16,
        LIGHT_GRAY,
        (screen_width // 2, screen_height // 2 + 70),
    )


def compute_floor_cells(
    *,
    cols: int,
    rows: int,
    wall_cells: set[tuple[int, int]],
    outer_wall_cells: set[tuple[int, int]],
    pitfall_cells: set[tuple[int, int]],
) -> set[tuple[int, int]]:
    """Return floor cells for the minimap base pass."""
    # The layout wall sets are updated when walls are destroyed, so removing
    # those cells here makes the minimap treat destroyed walls as floor.
    blocked = wall_cells | outer_wall_cells | pitfall_cells
    return {(x, y) for y in range(rows) for x in range(cols) if (x, y) not in blocked}


def draw_level_overview(
    assets: RenderAssets,
    surface: surface.Surface,
    wall_group: sprite.Group,
    floor_cells: set[tuple[int, int]],
    player: Player | None,
    car: Car | None,
    waiting_cars: list[Car] | None,
    footprints: list[Footprint],
    *,
    fuel: FuelCan | None = None,
    flashlights: list[Flashlight] | None = None,
    shoes: list[Shoes] | None = None,
    buddies: list[Survivor] | None = None,
    survivors: list[Survivor] | None = None,
    palette_key: str | None = None,
) -> None:
    palette = get_environment_palette(palette_key)
    base_floor = palette.floor_primary
    dark_floor = tuple(max(0, int(channel * 0.35)) for channel in base_floor)
    floor_color = tuple(max(0, int(channel * 0.65)) for channel in base_floor)
    surface.fill(dark_floor)
    cell_size = assets.internal_wall_grid_snap
    if cell_size > 0:
        for x, y in floor_cells:
            pygame.draw.rect(
                surface,
                floor_color,
                pygame.Rect(
                    x * cell_size,
                    y * cell_size,
                    cell_size,
                    cell_size,
                ),
            )

    for wall in wall_group:
        if wall.max_health > 0:
            health_ratio = max(0.0, min(1.0, wall.health / wall.max_health))
        else:
            health_ratio = 0.0
        if isinstance(wall, Wall):
            if health_ratio <= 0.0:
                pygame.draw.rect(surface, floor_color, wall.rect)
            else:
                fill_color, _ = resolve_wall_colors(
                    health_ratio=health_ratio,
                    palette_category=wall.palette_category,
                    palette=palette,
                )
                pygame.draw.rect(surface, fill_color, wall.rect)
        elif isinstance(wall, SteelBeam):
            if health_ratio <= 0.0:
                pygame.draw.rect(surface, floor_color, wall.rect)
            else:
                fill_color, _ = resolve_steel_beam_colors(
                    health_ratio=health_ratio,
                    palette=palette,
                )
                pygame.draw.rect(surface, fill_color, wall.rect)
    now = pygame.time.get_ticks()
    for fp in footprints:
        if not fp.visible:
            continue
        age = now - fp.time
        fade = 1 - (age / assets.footprint_lifetime_ms)
        fade = max(assets.footprint_min_fade, fade)
        color = tuple(int(c * fade) for c in FOOTPRINT_COLOR)
        pygame.draw.circle(
            surface,
            color,
            (int(fp.pos[0]), int(fp.pos[1])),
            assets.footprint_overview_radius,
        )
    if fuel and fuel.alive():
        pygame.draw.rect(surface, YELLOW, fuel.rect, border_radius=3)
        pygame.draw.rect(surface, BLACK, fuel.rect, width=2, border_radius=3)
    if flashlights:
        for flashlight in flashlights:
            if flashlight.alive():
                pygame.draw.rect(surface, YELLOW, flashlight.rect, border_radius=2)
                pygame.draw.rect(surface, BLACK, flashlight.rect, width=2, border_radius=2)
    if shoes:
        for item in shoes:
            if item.alive():
                surface.blit(item.image, item.rect)
    if survivors:
        for survivor in survivors:
            if survivor.alive():
                pygame.draw.circle(
                    surface,
                    (220, 220, 255),
                    survivor.rect.center,
                    assets.player_radius * 2,
                )
    if player:
        pygame.draw.circle(surface, BLUE, player.rect.center, assets.player_radius * 2)
    if buddies:
        buddy_color = (0, 200, 70)
        for buddy in buddies:
            if buddy.alive() and not buddy.rescued:
                pygame.draw.circle(surface, buddy_color, buddy.rect.center, assets.player_radius * 2)
    drawn_cars: list[Car] = []
    if car and car.alive():
        car_rect = car.image.get_rect(center=car.rect.center)
        surface.blit(car.image, car_rect)
        drawn_cars.append(car)
    if waiting_cars:
        for parked in waiting_cars:
            if not parked.alive() or parked in drawn_cars:
                continue
            parked_rect = parked.image.get_rect(center=parked.rect.center)
            surface.blit(parked.image, parked_rect)


def _max_flashlight_pickups() -> int:
    """Return the maximum flashlight pickups available per stage."""
    return max(1, DEFAULT_FLASHLIGHT_SPAWN_COUNT)


class FogProfile(Enum):
    DARK0 = (0, (0, 0, 0, 255))
    DARK1 = (1, (0, 0, 0, 255))
    DARK2 = (2, (0, 0, 0, 255))
    DAWN = (2, (50, 50, 50, 230))

    def __init__(self, flashlight_count: int, color: tuple[int, int, int, int]) -> None:
        self.flashlight_count = flashlight_count
        self.color = color

    def _scale(self, assets: RenderAssets, stage: Stage | None) -> float:
        count = max(0, min(self.flashlight_count, _max_flashlight_pickups()))
        return _get_fog_scale(assets, count)

    @staticmethod
    def _from_flashlight_count(count: int) -> "FogProfile":
        safe_count = max(0, count)
        if safe_count >= 2:
            return FogProfile.DARK2
        if safe_count == 1:
            return FogProfile.DARK1
        return FogProfile.DARK0


def prewarm_fog_overlays(
    fog_data: dict[str, Any],
    assets: RenderAssets,
    *,
    stage: Stage | None = None,
) -> None:
    """Populate fog overlay cache for each reachable flashlight count."""

    for profile in FogProfile:
        _get_fog_overlay_surfaces(
            fog_data,
            assets,
            profile,
            stage=stage,
        )


def _get_hatch_pattern(
    fog_data: dict[str, Any],
    thickness: int,
    *,
    color: tuple[int, int, int, int] | None = None,
) -> surface.Surface:
    """Return cached dot hatch tile surface (Bayer-ordered, optionally chunky)."""
    cache = fog_data.setdefault("hatch_patterns", {})
    key = (thickness, color)
    if key in cache:
        return cache[key]

    spacing = 4
    oversample = 3
    density = max(1, min(thickness, 16))
    pattern_size = spacing * 8
    hi_spacing = spacing * oversample
    hi_pattern_size = pattern_size * oversample
    pattern = pygame.Surface((hi_pattern_size, hi_pattern_size), pygame.SRCALPHA)

    # 8x8 Bayer matrix values 0..63 for ordered dithering
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
    threshold = int((density / 16) * 64)
    dot_radius = max(
        1,
        min(hi_spacing, int(math.ceil((density / 16) * hi_spacing))),
    )
    dot_color = color or (0, 0, 0, 255)
    for grid_y in range(8):
        for grid_x in range(8):
            if bayer[grid_y][grid_x] < threshold:
                cx = grid_x * hi_spacing + hi_spacing // 2
                cy = grid_y * hi_spacing + hi_spacing // 2
                pygame.draw.circle(pattern, dot_color, (cx, cy), dot_radius)

    if oversample > 1:
        pattern = pygame.transform.smoothscale(pattern, (pattern_size, pattern_size))

    cache[key] = pattern
    return pattern


def _get_fog_overlay_surfaces(
    fog_data: dict[str, Any],
    assets: RenderAssets,
    profile: FogProfile,
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
    for ring in assets.fog_rings:
        ring_surface = pygame.Surface((width, height), pygame.SRCALPHA)
        pattern = _get_hatch_pattern(
            fog_data,
            ring.thickness,
            color=base_color,
        )
        p_w, p_h = pattern.get_size()
        for y in range(0, height, p_h):
            for x in range(0, width, p_w):
                ring_surface.blit(pattern, (x, y))
        radius = int(assets.fov_radius * ring.radius_factor * ring_scale)
        pygame.draw.circle(ring_surface, (0, 0, 0, 0), center, radius)
        ring_surfaces.append(ring_surface)

    combined_surface = hard_surface.copy()
    for ring_surface in ring_surfaces:
        combined_surface.blit(ring_surface, (0, 0))

    visible_fade_surface = _build_flashlight_fade_surface((width, height), center, max_radius)
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
    falling_zombies: list[FallingZombie],
    flashlight_count: int,
    dust_rings: list[DustRing],
) -> None:
    if not falling_zombies and not dust_rings:
        return
    now = pygame.time.get_ticks()
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


def _draw_play_area(
    screen: surface.Surface,
    camera: Camera,
    assets: RenderAssets,
    palette: Any,
    field_rect: pygame.Rect,
    outside_cells: set[tuple[int, int]],
    fall_spawn_cells: set[tuple[int, int]],
    pitfall_cells: set[tuple[int, int]],
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
                if sr.colliderect(screen.get_rect()):
                    pygame.draw.rect(screen, palette.outside, sr)
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
                if not sr.colliderect(screen.get_rect()):
                    continue
                pygame.draw.rect(screen, PITFALL_ABYSS_COLOR, sr)

                if (x, y - 1) not in pitfall_cells:
                    edge_h = max(1, INTERNAL_WALL_BEVEL_DEPTH - PITFALL_EDGE_DEPTH_OFFSET)
                    pygame.draw.rect(screen, PITFALL_EDGE_METAL_COLOR, (sr.x, sr.y, sr.w, edge_h))
                    for sx in range(sr.x - edge_h, sr.right, PITFALL_EDGE_STRIPE_SPACING):
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
                color = palette.fall_zone_secondary if use_secondary else palette.fall_zone_primary
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
            if sr.colliderect(screen.get_rect()):
                pygame.draw.rect(screen, color, sr)

    return xs, ys, xe, ye, outside_cells


def abs_clip(value: float, min_v: float, max_v: float) -> float:
    value_sign = 1.0 if value >= 0.0 else -1.0
    value = abs(value)
    if value < min_v:
        value = min_v
    elif value > max_v:
        value = max_v
    return value_sign * value


def _draw_wall_shadows(
    shadow_layer: surface.Surface,
    camera: Camera,
    *,
    wall_cells: set[tuple[int, int]],
    wall_group: sprite.Group | None,
    outer_wall_cells: set[tuple[int, int]] | None,
    cell_size: int,
    light_source_pos: tuple[int, int] | None,
    alpha: int = 68,
) -> bool:
    if not wall_cells or cell_size <= 0 or light_source_pos is None:
        return False
    inner_wall_cells = set(wall_cells)
    if outer_wall_cells:
        inner_wall_cells.difference_update(outer_wall_cells)
    if wall_group and cell_size > 0:
        for wall in wall_group:
            if isinstance(wall, SteelBeam):
                cell_x = int(wall.rect.centerx // cell_size)
                cell_y = int(wall.rect.centery // cell_size)
                inner_wall_cells.add((cell_x, cell_y))
    if not inner_wall_cells:
        return False
    base_shadow_size = max(cell_size + 2, int(cell_size * 1.35))
    shadow_size = max(1, int(base_shadow_size * 1.5))
    shadow_surface = _get_shadow_tile_surface(
        shadow_size,
        alpha,
        edge_softness=0.12,
    )
    screen_rect = shadow_layer.get_rect()
    px, py = light_source_pos
    drew = False
    clip_max = shadow_size * 0.25
    for cell_x, cell_y in inner_wall_cells:
        world_x = cell_x * cell_size
        world_y = cell_y * cell_size
        wall_rect = pygame.Rect(world_x, world_y, cell_size, cell_size)
        wall_screen_rect = camera.apply_rect(wall_rect)
        if not wall_screen_rect.colliderect(screen_rect):
            continue
        center_x = world_x + cell_size / 2
        center_y = world_y + cell_size / 2
        dx = (center_x - px) * 0.5
        dy = (center_y - py) * 0.5
        dx = int(abs_clip(dx, 0, clip_max))
        dy = int(abs_clip(dy, 0, clip_max))
        shadow_rect = pygame.Rect(0, 0, shadow_size, shadow_size)
        shadow_rect.center = (
            int(center_x + dx),
            int(center_y + dy),
        )
        shadow_screen_rect = camera.apply_rect(shadow_rect)
        if not shadow_screen_rect.colliderect(screen_rect):
            continue
        shadow_layer.blit(
            shadow_surface,
            shadow_screen_rect.topleft,
            special_flags=pygame.BLEND_RGBA_MAX,
        )
        drew = True
    return drew


def _draw_entity_shadows(
    shadow_layer: surface.Surface,
    camera: Camera,
    all_sprites: sprite.LayeredUpdates,
    *,
    light_source_pos: tuple[int, int] | None,
    exclude_car: Car | None,
    outside_cells: set[tuple[int, int]] | None,
    cell_size: int,
    shadow_radius: int = int(ZOMBIE_RADIUS * ENTITY_SHADOW_RADIUS_MULT),
    alpha: int = ENTITY_SHADOW_ALPHA,
) -> bool:
    if light_source_pos is None or shadow_radius <= 0:
        return False
    if cell_size <= 0:
        outside_cells = None
    shadow_surface = _get_shadow_circle_surface(
        shadow_radius,
        alpha,
        edge_softness=ENTITY_SHADOW_EDGE_SOFTNESS,
    )
    screen_rect = shadow_layer.get_rect()
    px, py = light_source_pos
    offset_dist = max(1.0, shadow_radius * 0.6)
    drew = False
    for entity in all_sprites:
        if not entity.alive():
            continue
        if isinstance(entity, Player):
            continue
        if isinstance(entity, Car):
            if exclude_car is not None and entity is exclude_car:
                continue
        if not isinstance(entity, (Zombie, Survivor, Car)):
            continue
        if outside_cells:
            cell = (
                int(entity.rect.centerx // cell_size),
                int(entity.rect.centery // cell_size),
            )
            if cell in outside_cells:
                continue
        cx, cy = entity.rect.center
        dx = cx - px
        dy = cy - py
        dist = math.hypot(dx, dy)
        if dist > 0.001:
            scale = offset_dist / dist
            offset_x = dx * scale
            offset_y = dy * scale
        else:
            offset_x = 0.0
            offset_y = 0.0

        jump_dy = 0.0
        if getattr(entity, "is_jumping", False):
            jump_dy = JUMP_SHADOW_OFFSET

        shadow_rect = shadow_surface.get_rect(center=(int(cx + offset_x), int(cy + offset_y + jump_dy)))
        shadow_screen_rect = camera.apply_rect(shadow_rect)
        if not shadow_screen_rect.colliderect(screen_rect):
            continue
        shadow_layer.blit(
            shadow_surface,
            shadow_screen_rect.topleft,
            special_flags=pygame.BLEND_RGBA_MAX,
        )
        drew = True
    return drew


def _draw_single_entity_shadow(
    shadow_layer: surface.Surface,
    camera: Camera,
    *,
    entity: pygame.sprite.Sprite | None,
    light_source_pos: tuple[int, int] | None,
    outside_cells: set[tuple[int, int]] | None,
    cell_size: int,
    shadow_radius: int,
    alpha: int,
    edge_softness: float = ENTITY_SHADOW_EDGE_SOFTNESS,
) -> bool:
    if entity is None or not entity.alive() or light_source_pos is None or shadow_radius <= 0:
        return False
    if outside_cells and cell_size > 0:
        cell = (
            int(entity.rect.centerx // cell_size),
            int(entity.rect.centery // cell_size),
        )
        if cell in outside_cells:
            return False
    shadow_surface = _get_shadow_circle_surface(
        shadow_radius,
        alpha,
        edge_softness=edge_softness,
    )
    screen_rect = shadow_layer.get_rect()
    px, py = light_source_pos
    cx, cy = entity.rect.center
    dx = cx - px
    dy = cy - py
    dist = math.hypot(dx, dy)
    offset_dist = max(1.0, shadow_radius * 0.6)
    if dist > 0.001:
        scale = offset_dist / dist
        offset_x = dx * scale
        offset_y = dy * scale
    else:
        offset_x = 0.0
        offset_y = 0.0

    jump_dy = 0.0
    if getattr(entity, "is_jumping", False):
        jump_dy = JUMP_SHADOW_OFFSET

    shadow_rect = shadow_surface.get_rect(center=(int(cx + offset_x), int(cy + offset_y + jump_dy)))
    shadow_screen_rect = camera.apply_rect(shadow_rect)
    if not shadow_screen_rect.colliderect(screen_rect):
        return False
    shadow_layer.blit(
        shadow_surface,
        shadow_screen_rect.topleft,
        special_flags=pygame.BLEND_RGBA_MAX,
    )
    return True


def _draw_footprints(
    screen: surface.Surface,
    camera: Camera,
    assets: RenderAssets,
    footprints: list[Footprint],
    *,
    config: dict[str, Any],
) -> None:
    if not config.get("footprints", {}).get("enabled", True):
        return
    now = pygame.time.get_ticks()
    for fp in footprints:
        if not fp.visible:
            continue
        age = now - fp.time
        fade = 1 - (age / assets.footprint_lifetime_ms)
        fade = max(assets.footprint_min_fade, fade)
        color = tuple(int(c * fade) for c in FOOTPRINT_COLOR)
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
) -> pygame.Rect:
    screen_rect_inflated = screen.get_rect().inflate(100, 100)
    player_screen_rect: pygame.Rect | None = None
    for entity in all_sprites:
        sprite_screen_rect = camera.apply_rect(entity.rect)
        if sprite_screen_rect.colliderect(screen_rect_inflated):
            screen.blit(entity.image, sprite_screen_rect)
        if entity is player:
            player_screen_rect = sprite_screen_rect
            _draw_fuel_indicator(
                screen,
                player_screen_rect,
                has_fuel=has_fuel,
                in_car=player.in_car,
            )
    return player_screen_rect or camera.apply_rect(player.rect)


def _draw_fuel_indicator(
    screen: surface.Surface,
    player_screen_rect: pygame.Rect,
    *,
    has_fuel: bool,
    in_car: bool,
) -> None:
    if not has_fuel or in_car:
        return
    indicator_size = 4
    padding = 1
    indicator_rect = pygame.Rect(
        player_screen_rect.right - indicator_size - padding,
        player_screen_rect.bottom - indicator_size - padding,
        indicator_size,
        indicator_size,
    )
    pygame.draw.rect(screen, YELLOW, indicator_rect)
    pygame.draw.rect(screen, (180, 160, 40), indicator_rect, width=1)


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
    fov_center_on_screen = list(camera.apply(fov_target).center)
    cam_rect = camera.camera
    horizontal_span = camera.width - assets.screen_width
    vertical_span = camera.height - assets.screen_height
    if horizontal_span <= 0 or (cam_rect.x != 0 and cam_rect.x != -horizontal_span):
        fov_center_on_screen[0] = assets.screen_width // 2
    if vertical_span <= 0 or (cam_rect.y != 0 and cam_rect.y != -vertical_span):
        fov_center_on_screen[1] = assets.screen_height // 2
    fov_center_tuple = (int(fov_center_on_screen[0]), int(fov_center_on_screen[1]))
    if dawn_ready:
        profile = FogProfile.DAWN
    else:
        profile = FogProfile._from_flashlight_count(flashlight_count)
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


def _draw_need_fuel_message(
    screen: surface.Surface,
    assets: RenderAssets,
    *,
    has_fuel: bool,
    fuel_message_until: int,
    elapsed_play_ms: int,
) -> None:
    if has_fuel or fuel_message_until <= elapsed_play_ms:
        return
    show_message(
        screen,
        tr("hud.need_fuel"),
        18,
        ORANGE,
        (assets.screen_width // 2, assets.screen_height // 2),
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
    has_fuel = state.has_fuel
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
    )
    shadow_layer = _get_shadow_layer(screen.get_size())
    shadow_layer.fill((0, 0, 0, 0))
    drew_shadow = _draw_wall_shadows(
        shadow_layer,
        camera,
        wall_cells=game_data.layout.wall_cells,
        wall_group=game_data.groups.wall_group,
        outer_wall_cells=game_data.layout.outer_wall_cells,
        cell_size=game_data.cell_size,
        light_source_pos=(None if (stage and stage.endurance_stage and state.dawn_ready) else fov_target.rect.center)
        if fov_target
        else None,
    )
    drew_shadow |= _draw_entity_shadows(
        shadow_layer,
        camera,
        all_sprites,
        light_source_pos=fov_target.rect.center if fov_target else None,
        exclude_car=active_car if player.in_car else None,
        outside_cells=outside_cells,
        cell_size=game_data.cell_size,
    )
    player_shadow_alpha = max(1, int(ENTITY_SHADOW_ALPHA * PLAYER_SHADOW_ALPHA_MULT))
    player_shadow_radius = int(ZOMBIE_RADIUS * PLAYER_SHADOW_RADIUS_MULT)
    if player.in_car:
        drew_shadow |= _draw_single_entity_shadow(
            shadow_layer,
            camera,
            entity=active_car,
            light_source_pos=fov_target.rect.center if fov_target else None,
            outside_cells=outside_cells,
            cell_size=game_data.cell_size,
            shadow_radius=player_shadow_radius,
            alpha=player_shadow_alpha,
        )
    else:
        drew_shadow |= _draw_single_entity_shadow(
            shadow_layer,
            camera,
            entity=player,
            light_source_pos=fov_target.rect.center if fov_target else None,
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
    )
    _draw_entities(
        screen,
        camera,
        all_sprites,
        player,
        has_fuel=has_fuel,
    )

    _draw_falling_fx(
        screen,
        camera,
        state.falling_zombies,
        state.flashlight_count,
        state.dust_rings,
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
    _draw_need_fuel_message(
        screen,
        assets,
        has_fuel=has_fuel,
        fuel_message_until=state.fuel_message_until,
        elapsed_play_ms=state.elapsed_play_ms,
    )

    objective_lines = _build_objective_lines(
        stage=stage,
        state=state,
        player=player,
        active_car=active_car,
        has_fuel=has_fuel,
        buddy_onboard=state.buddy_onboard,
        buddy_required=stage.buddy_required_count if stage else 0,
        survivors_onboard=state.survivors_onboard,
    )
    if objective_lines:
        _draw_objective(objective_lines, screen=screen)
    _draw_inventory_icons(
        screen,
        assets,
        has_fuel=has_fuel,
        flashlight_count=flashlight_count,
        shoes_count=state.shoes_count,
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
        falling_spawn_carry=state.falling_spawn_carry,
        show_fps=state.show_fps,
        fps=fps,
    )
