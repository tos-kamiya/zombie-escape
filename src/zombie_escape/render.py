from __future__ import annotations

import math
from enum import Enum
from typing import Any, Callable

import pygame
import pygame.surfarray as pg_surfarray  # type: ignore
from pygame import sprite, surface

from .colors import (
    BLACK,
    BLUE,
    FOOTPRINT_COLOR,
    LIGHT_GRAY,
    ORANGE,
    YELLOW,
    get_environment_palette,
)
from .entities import (
    Camera,
    Car,
    Flashlight,
    FuelCan,
    Player,
    SteelBeam,
    Survivor,
    Wall,
)
from .entities_constants import ZOMBIE_RADIUS
from .font_utils import load_font
from .gameplay_constants import (
    DEFAULT_FLASHLIGHT_SPAWN_COUNT,
    SURVIVAL_FAKE_CLOCK_RATIO,
)
from .localization import get_font_settings
from .localization import translate as tr
from .models import DustRing, FallingZombie, Footprint, GameData, Stage
from .render_assets import RenderAssets, resolve_steel_beam_colors, resolve_wall_colors
from .render_constants import (
    FALLING_DUST_COLOR,
    FALLING_WHIRLWIND_COLOR,
    FALLING_ZOMBIE_COLOR,
)

_SHADOW_TILE_CACHE: dict[tuple[int, int, float], surface.Surface] = {}
_SHADOW_LAYER_CACHE: dict[tuple[int, int], surface.Surface] = {}


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
    surf = pygame.Surface((size, size), pygame.SRCALPHA)
    base_alpha = key[1]
    if edge_softness <= 0:
        surf.fill((0, 0, 0, base_alpha))
        _SHADOW_TILE_CACHE[key] = surf
        return surf

    softness = max(0.0, min(1.0, edge_softness))
    fade_band = max(1, int(size * softness))
    base_radius = max(1, int(size * 0.18))

    def draw_layer(inset: int, layer_alpha: int) -> None:
        rect_size = size - inset * 2
        if rect_size <= 0:
            return
        radius = max(0, base_radius - inset)
        pygame.draw.rect(
            surf,
            (0, 0, 0, layer_alpha),
            pygame.Rect(inset, inset, rect_size, rect_size),
            border_radius=radius,
        )

    outer_alpha = int(base_alpha * 0.45)
    mid_alpha = int(base_alpha * 0.7)
    draw_layer(0, outer_alpha)
    draw_layer(max(1, fade_band // 2), mid_alpha)
    draw_layer(fade_band, base_alpha)
    _SHADOW_TILE_CACHE[key] = surf
    return surf


def _get_shadow_layer(size: tuple[int, int]) -> surface.Surface:
    key = (max(1, size[0]), max(1, size[1]))
    if key in _SHADOW_LAYER_CACHE:
        return _SHADOW_LAYER_CACHE[key]
    layer = pygame.Surface(key, pygame.SRCALPHA)
    _SHADOW_LAYER_CACHE[key] = layer
    return layer


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


def draw_level_overview(
    assets: RenderAssets,
    surface: surface.Surface,
    wall_group: sprite.Group,
    player: Player | None,
    car: Car | None,
    waiting_cars: list[Car] | None,
    footprints: list[Footprint],
    *,
    fuel: FuelCan | None = None,
    flashlights: list[Flashlight] | None = None,
    stage: Stage | None = None,
    buddies: list[Survivor] | None = None,
    survivors: list[Survivor] | None = None,
    palette_key: str | None = None,
) -> None:
    palette = get_environment_palette(palette_key)
    base_floor = palette.floor_primary
    dark_floor = tuple(max(0, int(channel * 0.55)) for channel in base_floor)
    surface.fill(dark_floor)
    for wall in wall_group:
        if wall.max_health > 0:
            health_ratio = max(0.0, min(1.0, wall.health / wall.max_health))
        else:
            health_ratio = 0.0
        if isinstance(wall, Wall):
            fill_color, _ = resolve_wall_colors(
                health_ratio=health_ratio,
                palette_category=wall.palette_category,
                palette=palette,
            )
            pygame.draw.rect(surface, fill_color, wall.rect)
        elif isinstance(wall, SteelBeam):
            fill_color, _ = resolve_steel_beam_colors(
                health_ratio=health_ratio,
                palette=palette,
            )
            pygame.draw.rect(surface, fill_color, wall.rect)
    now = pygame.time.get_ticks()
    for fp in footprints:
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
                pygame.draw.rect(
                    surface, (240, 230, 150), flashlight.rect, border_radius=2
                )
                pygame.draw.rect(
                    surface, BLACK, flashlight.rect, width=2, border_radius=2
                )
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
                pygame.draw.circle(
                    surface, buddy_color, buddy.rect.center, assets.player_radius * 2
                )
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


def _get_fog_scale(
    assets: RenderAssets,
    stage: Stage | None,
    flashlight_count: int,
) -> float:
    """Return current fog scale factoring in flashlight bonus."""
    scale = assets.fog_radius_scale
    flashlight_count = max(0, int(flashlight_count))
    if flashlight_count <= 0:
        return scale
    bonus_step = max(0.0, assets.flashlight_bonus_step)
    return scale + bonus_step * flashlight_count


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
        return _get_fog_scale(assets, stage, count)

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
    pixel_scale: int = 1,
    color: tuple[int, int, int, int] | None = None,
) -> surface.Surface:
    """Return cached ordered-dither tile surface (Bayer-style, optionally chunky)."""
    cache = fog_data.setdefault("hatch_patterns", {})
    pixel_scale = max(1, pixel_scale)
    key = (thickness, pixel_scale, color)
    if key in cache:
        return cache[key]

    spacing = 20
    density = max(1, min(thickness, 16))
    pattern = pygame.Surface((spacing, spacing), pygame.SRCALPHA)

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
    for y in range(spacing):
        for x in range(spacing):
            if bayer[y % 8][x % 8] < threshold:
                pattern.set_at((x, y), color or (0, 0, 0, 255))

    if pixel_scale > 1:
        scaled_size = (spacing * pixel_scale, spacing * pixel_scale)
        pattern = pygame.transform.scale(pattern, scaled_size)

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
            pixel_scale=assets.fog_hatch_pixel_scale,
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
    outer_extension: int = 50,
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
    swirl_radius = max(2, int(ZOMBIE_RADIUS * 1.1))
    offset = max(1, int(ZOMBIE_RADIUS * 0.6))
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
                _draw_fall_whirlwind(screen, camera, fall.target_pos, fx_progress)
            continue
        if now >= impact_at:
            continue
        fall_progress = max(0.0, min(1.0, (now - fall_start) / fall_duration_ms))
        eased = 1.0 - (1.0 - fall_progress) * (1.0 - fall_progress)
        x = fall.target_pos[0]
        y = int(fall.start_pos[1] + (fall.target_pos[1] - fall.start_pos[1]) * eased)
        world_rect = pygame.Rect(0, 0, ZOMBIE_RADIUS * 2, ZOMBIE_RADIUS * 2)
        world_rect.center = (x, y)
        screen_rect = camera.apply_rect(world_rect)
        pygame.draw.circle(
            screen,
            FALLING_ZOMBIE_COLOR,
            screen_rect.center,
            ZOMBIE_RADIUS,
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


def _draw_hint_arrow(
    screen: surface.Surface,
    camera: Camera,
    assets: RenderAssets,
    player: Player,
    target_pos: tuple[int, int],
    *,
    color: tuple[int, int, int] | None = None,
    ring_radius: float | None = None,
) -> None:
    """Draw a soft directional hint from player to a target position."""
    color = color or YELLOW
    player_screen = camera.apply(player).center
    target_rect = pygame.Rect(target_pos[0], target_pos[1], 0, 0)
    target_screen = camera.apply_rect(target_rect).center
    dx = target_screen[0] - player_screen[0]
    dy = target_screen[1] - player_screen[1]
    dist = math.hypot(dx, dy)
    if dist < 10:
        return
    dir_x = dx / dist
    dir_y = dy / dist
    ring_radius = (
        ring_radius
        if ring_radius is not None
        else assets.fov_radius * 0.5 * assets.fog_radius_scale
    )
    center_x = player_screen[0] + dir_x * ring_radius
    center_y = player_screen[1] + dir_y * ring_radius
    arrow_len = 6
    tip = (center_x + dir_x * arrow_len, center_y + dir_y * arrow_len)
    base = (center_x - dir_x * 6, center_y - dir_y * 6)
    left = (
        base[0] - dir_y * 5,
        base[1] + dir_x * 5,
    )
    right = (
        base[0] + dir_y * 5,
        base[1] - dir_x * 5,
    )
    pygame.draw.polygon(screen, color, [tip, left, right])


def _draw_status_bar(
    screen: surface.Surface,
    assets: RenderAssets,
    config: dict[str, Any],
    *,
    stage: Stage | None = None,
    seed: int | None = None,
    debug_mode: bool = False,
    zombie_group: sprite.Group | None = None,
    falling_spawn_carry: int | None = None,
) -> None:
    """Render a compact status bar with current config flags and stage info."""
    bar_rect = pygame.Rect(
        0,
        assets.screen_height - assets.status_bar_height,
        assets.screen_width,
        assets.status_bar_height,
    )
    overlay = pygame.Surface((bar_rect.width, bar_rect.height), pygame.SRCALPHA)
    overlay.fill((0, 0, 0, 140))
    screen.blit(overlay, bar_rect.topleft)

    footprints_on = config.get("footprints", {}).get("enabled", True)
    fast_on = config.get("fast_zombies", {}).get("enabled", True)
    hint_on = config.get("car_hint", {}).get("enabled", True)
    steel_on = config.get("steel_beams", {}).get("enabled", False)
    if stage:
        # Keep the label compact for the status bar
        stage_label = f"#{stage.id[-1]}" if stage.id.startswith("stage") else stage.id
    else:
        stage_label = "#1"

    parts = [tr("status.stage", label=stage_label)]
    if footprints_on:
        parts.append(tr("status.footprints"))
    if hint_on:
        parts.append(tr("status.car_hint"))
    if fast_on:
        parts.append(tr("status.fast"))
    if steel_on:
        parts.append(tr("status.steel"))
    if debug_mode:
        if zombie_group is not None:
            zombies = [z for z in zombie_group if z.alive()]
            total = len(zombies)
            tracker = sum(1 for z in zombies if z.tracker)
            wall = sum(1 for z in zombies if z.wall_follower)
            normal = max(0, total - tracker - wall)
            parts.append(f"Z:{total} N:{normal} T:{tracker} W:{wall}")
            if falling_spawn_carry is not None:
                parts.append(f"C:{max(0, falling_spawn_carry)}")

    status_text = " | ".join(parts)
    color = LIGHT_GRAY

    try:
        font_settings = get_font_settings()
        font = load_font(font_settings.resource, font_settings.scaled_size(11))
        text_surface = font.render(status_text, False, color)
        text_rect = text_surface.get_rect(left=12, centery=bar_rect.centery)
        screen.blit(text_surface, text_rect)
        if seed is not None:
            seed_text = tr("status.seed", value=str(seed))
            seed_surface = font.render(seed_text, False, LIGHT_GRAY)
            seed_rect = seed_surface.get_rect(
                right=bar_rect.right - 12, centery=bar_rect.centery
            )
            screen.blit(seed_surface, seed_rect)
    except pygame.error as e:
        print(f"Error rendering status bar: {e}")


def _draw_play_area(
    screen: surface.Surface,
    camera: Camera,
    assets: RenderAssets,
    palette: Any,
    outer_rect: tuple[int, int, int, int],
    outside_rects: list[pygame.Rect],
    fall_spawn_cells: set[tuple[int, int]],
) -> tuple[int, int, int, int, set[tuple[int, int]]]:
    xs, ys, xe, ye = outer_rect
    xs //= assets.internal_wall_grid_snap
    ys //= assets.internal_wall_grid_snap
    xe //= assets.internal_wall_grid_snap
    ye //= assets.internal_wall_grid_snap

    play_area_rect = pygame.Rect(
        xs * assets.internal_wall_grid_snap,
        ys * assets.internal_wall_grid_snap,
        (xe - xs) * assets.internal_wall_grid_snap,
        (ye - ys) * assets.internal_wall_grid_snap,
    )
    play_area_screen_rect = camera.apply_rect(play_area_rect)
    pygame.draw.rect(screen, palette.floor_primary, play_area_screen_rect)

    outside_cells = {
        (r.x // assets.internal_wall_grid_snap, r.y // assets.internal_wall_grid_snap)
        for r in outside_rects
    }
    for rect_obj in outside_rects:
        sr = camera.apply_rect(rect_obj)
        if sr.colliderect(screen.get_rect()):
            pygame.draw.rect(screen, palette.outside, sr)

    view_world = pygame.Rect(
        -camera.camera.x,
        -camera.camera.y,
        assets.screen_width,
        assets.screen_height,
    )
    margin = assets.internal_wall_grid_snap * 2
    view_world.inflate_ip(margin * 2, margin * 2)
    min_world_x = max(xs * assets.internal_wall_grid_snap, view_world.left)
    max_world_x = min(xe * assets.internal_wall_grid_snap, view_world.right)
    min_world_y = max(ys * assets.internal_wall_grid_snap, view_world.top)
    max_world_y = min(ye * assets.internal_wall_grid_snap, view_world.bottom)
    start_x = max(xs, int(min_world_x // assets.internal_wall_grid_snap))
    end_x = min(xe, int(math.ceil(max_world_x / assets.internal_wall_grid_snap)))
    start_y = max(ys, int(min_world_y // assets.internal_wall_grid_snap))
    end_y = min(ye, int(math.ceil(max_world_y / assets.internal_wall_grid_snap)))

    for y in range(start_y, end_y):
        for x in range(start_x, end_x):
            if (x, y) in outside_cells:
                continue
            use_secondary = ((x // 2) + (y // 2)) % 2 == 0
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
                x * assets.internal_wall_grid_snap,
                y * assets.internal_wall_grid_snap,
            )
            r = pygame.Rect(
                lx,
                ly,
                assets.internal_wall_grid_snap,
                assets.internal_wall_grid_snap,
            )
            sr = camera.apply_rect(r)
            if sr.colliderect(screen.get_rect()):
                pygame.draw.rect(screen, color, sr)

    return xs, ys, xe, ye, outside_cells


def _draw_wall_shadows(
    screen: surface.Surface,
    camera: Camera,
    *,
    wall_cells: set[tuple[int, int]],
    wall_group: sprite.Group | None,
    outer_wall_cells: set[tuple[int, int]] | None,
    cell_size: int,
    light_source_pos: tuple[int, int] | None,
    alpha: int = 54,
) -> None:
    if not wall_cells or cell_size <= 0 or light_source_pos is None:
        return
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
        return
    base_shadow_size = max(cell_size + 2, int(cell_size * 1.35))
    shadow_size = max(1, int(base_shadow_size * 1.5))
    shadow_surface = _get_shadow_tile_surface(shadow_size, 255, edge_softness=0.12)
    shadow_layer = _get_shadow_layer(screen.get_size())
    shadow_layer.fill((0, 0, 0, 0))
    screen_rect = screen.get_rect()
    px, py = light_source_pos
    offset = max(2, int(cell_size * 0.3 * (shadow_size / cell_size) * 1.2))
    drew = False
    for cell_x, cell_y in inner_wall_cells:
        world_x = cell_x * cell_size
        world_y = cell_y * cell_size
        center_x = world_x + cell_size / 2
        center_y = world_y + cell_size / 2
        dx = center_x - px
        dy = center_y - py
        dist = math.hypot(dx, dy)
        if dist <= 1e-3:
            continue
        nx = dx / dist
        ny = dy / dist
        shadow_rect = pygame.Rect(0, 0, shadow_size, shadow_size)
        shadow_rect.center = (
            int(center_x + nx * offset),
            int(center_y + ny * offset),
        )
        shadow_screen_rect = camera.apply_rect(shadow_rect)
        if not shadow_screen_rect.colliderect(screen_rect):
            continue
        shadow_layer.blit(shadow_surface, shadow_screen_rect.topleft)
        drew = True
    if drew:
        shadow_layer.set_alpha(alpha)
        screen.blit(shadow_layer, (0, 0))


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


def _draw_hint_indicator(
    screen: surface.Surface,
    camera: Camera,
    assets: RenderAssets,
    player: Player,
    hint_target: tuple[int, int] | None,
    *,
    hint_color: tuple[int, int, int],
    stage: Stage | None,
    flashlight_count: int,
) -> None:
    if not hint_target:
        return
    current_fov_scale = _get_fog_scale(
        assets,
        stage,
        flashlight_count,
    )
    hint_ring_radius = assets.fov_radius * 0.5 * current_fov_scale
    _draw_hint_arrow(
        screen,
        camera,
        assets,
        player,
        hint_target,
        color=hint_color,
        ring_radius=hint_ring_radius,
    )


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


def _draw_objective(lines: list[str], *, screen: surface.Surface) -> None:
    try:
        font_settings = get_font_settings()
        font = load_font(font_settings.resource, font_settings.scaled_size(11))
        y = 8
        for line in lines:
            text_surface = font.render(line, False, YELLOW)
            text_rect = text_surface.get_rect(topleft=(12, y))
            screen.blit(text_surface, text_rect)
            y += text_rect.height + 4
    except pygame.error as e:
        print(f"Error rendering objective: {e}")


def _draw_endurance_timer(
    screen: surface.Surface,
    assets: RenderAssets,
    *,
    stage: Stage | None,
    state: Any,
) -> None:
    if not (stage and stage.endurance_stage):
        return
    goal_ms = state.endurance_goal_ms
    if goal_ms <= 0:
        return
    elapsed_ms = max(0, min(goal_ms, state.endurance_elapsed_ms))
    remaining_ms = max(0, goal_ms - elapsed_ms)
    padding = 12
    bar_height = 8
    y_pos = assets.screen_height - assets.status_bar_height - bar_height - 10
    bar_rect = pygame.Rect(
        padding,
        y_pos,
        assets.screen_width - padding * 2,
        bar_height,
    )
    track_surface = pygame.Surface((bar_rect.width, bar_rect.height), pygame.SRCALPHA)
    track_surface.fill((0, 0, 0, 140))
    screen.blit(track_surface, bar_rect.topleft)
    progress_ratio = elapsed_ms / goal_ms if goal_ms else 0.0
    progress_width = int(bar_rect.width * max(0.0, min(1.0, progress_ratio)))
    if progress_width > 0:
        fill_color = (120, 20, 20)
        if state.dawn_ready:
            fill_color = (25, 40, 120)
        fill_rect = pygame.Rect(
            bar_rect.left,
            bar_rect.top,
            progress_width,
            bar_rect.height,
        )
        pygame.draw.rect(screen, fill_color, fill_rect)
    display_ms = int(remaining_ms * SURVIVAL_FAKE_CLOCK_RATIO)
    display_ms = max(0, display_ms)
    display_hours = display_ms // 3_600_000
    display_minutes = (display_ms % 3_600_000) // 60_000
    display_label = f"{int(display_hours):02d}:{int(display_minutes):02d}"
    timer_text = tr("hud.endurance_timer_label", time=display_label)
    try:
        font_settings = get_font_settings()
        font = load_font(font_settings.resource, font_settings.scaled_size(12))
        text_surface = font.render(timer_text, False, LIGHT_GRAY)
        text_rect = text_surface.get_rect(left=bar_rect.left, bottom=bar_rect.top - 2)
        screen.blit(text_surface, text_rect)
        if state.time_accel_active:
            accel_text = tr("hud.time_accel")
            accel_surface = font.render(accel_text, False, YELLOW)
            accel_rect = accel_surface.get_rect(
                right=bar_rect.right, bottom=bar_rect.top - 2
            )
            screen.blit(accel_surface, accel_rect)
        else:
            hint_text = tr("hud.time_accel_hint")
            hint_surface = font.render(hint_text, False, LIGHT_GRAY)
            hint_rect = hint_surface.get_rect(
                right=bar_rect.right, bottom=bar_rect.top - 2
            )
            screen.blit(hint_surface, hint_rect)
    except pygame.error as e:
        print(f"Error rendering endurance timer: {e}")


def _draw_time_accel_indicator(
    screen: surface.Surface,
    assets: RenderAssets,
    *,
    stage: Stage | None,
    state: Any,
) -> None:
    if stage and stage.endurance_stage:
        return
    try:
        font_settings = get_font_settings()
        font = load_font(font_settings.resource, font_settings.scaled_size(12))
        if state.time_accel_active:
            text = tr("hud.time_accel")
            color = YELLOW
        else:
            text = tr("hud.time_accel_hint")
            color = LIGHT_GRAY
        text_surface = font.render(text, False, color)
        bottom_margin = assets.status_bar_height + 6
        text_rect = text_surface.get_rect(
            right=assets.screen_width - 12,
            bottom=assets.screen_height - bottom_margin,
        )
        screen.blit(text_surface, text_rect)
    except pygame.error as e:
        print(f"Error rendering acceleration indicator: {e}")


def _draw_survivor_messages(
    screen: surface.Surface,
    assets: RenderAssets,
    survivor_messages: list[dict[str, Any]],
) -> None:
    if not survivor_messages:
        return
    try:
        font_settings = get_font_settings()
        font = load_font(font_settings.resource, font_settings.scaled_size(14))
        base_y = assets.screen_height // 2 - 70
        for idx, message in enumerate(survivor_messages[:3]):
            text = message.get("text", "")
            if not text:
                continue
            msg_surface = font.render(text, False, ORANGE)
            msg_rect = msg_surface.get_rect(
                center=(assets.screen_width // 2, base_y + idx * 18)
            )
            screen.blit(msg_surface, msg_rect)
    except pygame.error as e:
        print(f"Error rendering survivor message: {e}")


def _build_objective_lines(
    *,
    stage: Stage | None,
    state: Any,
    player: Player,
    active_car: Car | None,
    has_fuel: bool,
    buddy_onboard: int,
    buddy_required: int,
    survivors_onboard: int,
) -> list[str]:
    objective_lines: list[str] = []
    if stage and stage.endurance_stage:
        if state.dawn_ready:
            objective_lines.append(tr("objectives.get_outside"))
        else:
            objective_lines.append(tr("objectives.survive_until_dawn"))
    elif stage and stage.buddy_required_count > 0:
        buddy_ready = buddy_onboard >= buddy_required
        if not active_car:
            objective_lines.append(tr("objectives.pickup_buddy"))
            if stage.requires_fuel and not has_fuel:
                objective_lines.append(tr("objectives.find_fuel"))
            else:
                objective_lines.append(tr("objectives.find_car"))
        else:
            if stage.requires_fuel and not has_fuel:
                objective_lines.append(tr("objectives.find_fuel"))
            elif not buddy_ready:
                objective_lines.append(tr("objectives.board_buddy"))
                objective_lines.append(
                    tr("objectives.buddy_onboard", count=buddy_onboard)
                )
                objective_lines.append(tr("objectives.escape"))
            else:
                objective_lines.append(tr("objectives.escape"))
    elif stage and stage.requires_fuel and not has_fuel:
        objective_lines.append(tr("objectives.find_fuel"))
    elif stage and stage.rescue_stage:
        if not player.in_car:
            objective_lines.append(tr("objectives.find_car"))
        else:
            objective_lines.append(tr("objectives.escape_with_survivors"))
    elif not player.in_car:
        objective_lines.append(tr("objectives.find_car"))
    else:
        objective_lines.append(tr("objectives.escape"))

    if stage and stage.rescue_stage and (survivors_onboard is not None):
        limit = state.survivor_capacity
        objective_lines.append(
            tr("objectives.survivors_onboard", count=survivors_onboard, limit=limit)
        )
    return objective_lines


def draw(
    assets: RenderAssets,
    screen: surface.Surface,
    game_data: GameData,
    *,
    config: dict[str, Any],
    hint_target: tuple[int, int] | None = None,
    hint_color: tuple[int, int, int] | None = None,
    do_flip: bool = True,
    present_fn: Callable[[surface.Surface], None] | None = None,
) -> None:
    hint_color = hint_color or YELLOW
    state = game_data.state
    player = game_data.player
    if player is None:
        raise ValueError("draw requires an active player on game_data")

    camera = game_data.camera
    stage = game_data.stage
    outer_rect = game_data.layout.outer_rect
    outside_rects = game_data.layout.outside_rects or []
    all_sprites = game_data.groups.all_sprites
    fog_surfaces = game_data.fog
    footprints = state.footprints
    has_fuel = state.has_fuel
    flashlight_count = state.flashlight_count
    elapsed_play_ms = state.elapsed_play_ms
    fuel_message_until = state.fuel_message_until
    buddy_onboard = state.buddy_onboard
    buddy_required = stage.buddy_required_count if stage else 0
    survivors_onboard = state.survivors_onboard
    survivor_messages = list(state.survivor_messages)
    zombie_group = game_data.groups.zombie_group
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
        outer_rect,
        outside_rects,
        game_data.layout.fall_spawn_cells,
    )
    _draw_wall_shadows(
        screen,
        camera,
        wall_cells=game_data.layout.wall_cells,
        wall_group=game_data.groups.wall_group,
        outer_wall_cells=game_data.layout.outer_wall_cells,
        cell_size=game_data.cell_size,
        light_source_pos=(
            None if (stage and stage.endurance_stage and state.dawn_ready) else fov_target.rect.center
        )
        if fov_target
        else None,
    )
    _draw_footprints(
        screen,
        camera,
        assets,
        footprints,
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
        fog_surfaces,
        fov_target,
        stage=stage,
        flashlight_count=flashlight_count,
        dawn_ready=state.dawn_ready,
    )
    _draw_need_fuel_message(
        screen,
        assets,
        has_fuel=has_fuel,
        fuel_message_until=fuel_message_until,
        elapsed_play_ms=elapsed_play_ms,
    )

    objective_lines = _build_objective_lines(
        stage=stage,
        state=state,
        player=player,
        active_car=active_car,
        has_fuel=has_fuel,
        buddy_onboard=buddy_onboard,
        buddy_required=buddy_required,
        survivors_onboard=survivors_onboard,
    )
    if objective_lines:
        _draw_objective(objective_lines, screen=screen)
    _draw_survivor_messages(screen, assets, survivor_messages)
    _draw_endurance_timer(screen, assets, stage=stage, state=state)
    _draw_time_accel_indicator(screen, assets, stage=stage, state=state)
    _draw_status_bar(
        screen,
        assets,
        config,
        stage=stage,
        seed=state.seed,
        debug_mode=state.debug_mode,
        zombie_group=zombie_group,
        falling_spawn_carry=state.falling_spawn_carry,
    )
    if do_flip:
        if present_fn:
            present_fn(screen)
        else:
            pygame.display.flip()
