from __future__ import annotations

import math
from enum import Enum
from typing import Any, Callable

import pygame
from pygame import sprite, surface
import pygame.surfarray as pg_surfarray  # type: ignore

from .colors import (
    BLACK,
    BLUE,
    FOOTPRINT_COLOR,
    GREEN,
    INTERNAL_WALL_COLOR,
    LIGHT_GRAY,
    ORANGE,
    YELLOW,
    get_environment_palette,
)
from .gameplay_constants import (
    DEFAULT_FLASHLIGHT_SPAWN_COUNT,
    SURVIVAL_FAKE_CLOCK_RATIO,
    SURVIVOR_MAX_SAFE_PASSENGERS,
)
from .entities import Camera, Car, Companion, Flashlight, FuelCan, Player, Survivor
from .font_utils import load_font
from .localization import get_font_settings
from .localization import translate as tr
from .models import GameData, Stage
from .render_assets import RenderAssets

DEBUG_TRACKER_OUTLINE_COLOR = (170, 70, 220)
DEBUG_WALL_FOLLOWER_OUTLINE_COLOR = (140, 140, 140)


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
    footprints: list[dict[str, Any]],
    *,
    fuel: FuelCan | None = None,
    flashlights: list[Flashlight] | None = None,
    stage: Stage | None = None,
    companion: Companion | None = None,
    survivors: list[Survivor] | None = None,
    palette_key: str | None = None,
) -> None:
    palette = get_environment_palette(palette_key)
    base_floor = getattr(palette, "floor_primary", palette.outside)
    dark_floor = tuple(max(0, int(channel * 0.55)) for channel in base_floor)
    surface.fill(dark_floor)
    for wall in wall_group:
        color = getattr(wall, "base_color", INTERNAL_WALL_COLOR)
        pygame.draw.rect(surface, color, wall.rect)
    now = pygame.time.get_ticks()
    for fp in footprints:
        age = now - fp["time"]
        fade = 1 - (age / assets.footprint_lifetime_ms)
        fade = max(assets.footprint_min_fade, fade)
        color = tuple(int(c * fade) for c in FOOTPRINT_COLOR)
        pygame.draw.circle(
            surface,
            color,
            (int(fp["pos"][0]), int(fp["pos"][1])),
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
            if hasattr(survivor, "alive") and survivor.alive():
                pygame.draw.circle(
                    surface,
                    (220, 220, 255),
                    survivor.rect.center,
                    assets.player_radius * 2,
                )
    if player:
        pygame.draw.circle(surface, BLUE, player.rect.center, assets.player_radius * 2)
    if (
        companion
        and hasattr(companion, "alive")
        and companion.alive()
        and not getattr(companion, "rescued", False)
    ):
        buddy_color = (0, 200, 70)
        pygame.draw.circle(
            surface, buddy_color, companion.rect.center, assets.player_radius * 2
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


def get_fog_scale(
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

    def scale(self, assets: RenderAssets, stage: Stage | None) -> float:
        count = max(0, min(self.flashlight_count, _max_flashlight_pickups()))
        return get_fog_scale(assets, stage, count)

    @staticmethod
    def from_flashlight_count(count: int) -> "FogProfile":
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


def get_hatch_pattern(
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

    scale = profile.scale(assets, stage)
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
        pattern = get_hatch_pattern(
            fog_data,
            ring.thickness,
            pixel_scale=assets.fog_hatch_pixel_scale,
            color=base_color,
        )
        p_w, p_h = pattern.get_size()
        for y in range(0, height, p_h):
            for x in range(0, width, p_w):
                ring_surface.blit(pattern, (x, y))
        radius = int(assets.fov_radius * ring.radius_factor * scale)
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


def draw_status_bar(
    screen: surface.Surface,
    assets: RenderAssets,
    config: dict[str, Any],
    *,
    stage: Stage | None = None,
    seed: int | None = None,
    debug_mode: bool = False,
    zombie_group: sprite.Group | None = None,
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
        parts.append(tr("status.debug"))
        if zombie_group is not None:
            zombies = [z for z in zombie_group if getattr(z, "alive", lambda: True)()]
            total = len(zombies)
            tracker = sum(1 for z in zombies if getattr(z, "tracker", False))
            wall = sum(1 for z in zombies if getattr(z, "wall_follower", False))
            normal = max(0, total - tracker - wall)
            parts.append(f"Z:{total} N:{normal} T:{tracker} W:{wall}")

    status_text = " | ".join(parts)
    color = GREEN if all([footprints_on, fast_on, hint_on]) else LIGHT_GRAY

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


def draw(
    assets: RenderAssets,
    screen: surface.Surface,
    game_data: GameData,
    fov_target: pygame.sprite.Sprite | None,
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
    companion = game_data.companion
    outer_rect = game_data.areas.outer_rect
    outside_rects = game_data.areas.outside_rects or []
    all_sprites = game_data.groups.all_sprites
    fog_surfaces = game_data.fog
    footprints = state.footprints
    has_fuel = state.has_fuel
    flashlight_count = state.flashlight_count
    elapsed_play_ms = state.elapsed_play_ms
    fuel_message_until = state.fuel_message_until
    companion_rescued = state.companion_rescued
    survivors_onboard = state.survivors_onboard
    survivor_messages = list(state.survivor_messages)
    zombie_group = game_data.groups.zombie_group

    palette = get_environment_palette(state.ambient_palette_key)
    screen.fill(palette.outside)

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
            if ((x // 2) + (y // 2)) % 2 == 0:
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
                    pygame.draw.rect(screen, palette.floor_secondary, sr)

    if config.get("footprints", {}).get("enabled", True):
        now = pygame.time.get_ticks()
        for fp in footprints:
            age = now - fp["time"]
            fade = 1 - (age / assets.footprint_lifetime_ms)
            fade = max(assets.footprint_min_fade, fade)
            color = tuple(int(c * fade) for c in FOOTPRINT_COLOR)
            fp_rect = pygame.Rect(
                fp["pos"][0] - assets.footprint_radius,
                fp["pos"][1] - assets.footprint_radius,
                assets.footprint_radius * 2,
                assets.footprint_radius * 2,
            )
            sr = camera.apply_rect(fp_rect)
            if sr.colliderect(screen.get_rect().inflate(30, 30)):
                pygame.draw.circle(screen, color, sr.center, assets.footprint_radius)

    screen_rect_inflated = screen.get_rect().inflate(100, 100)
    player_screen_rect: pygame.Rect | None = None
    for entity in all_sprites:
        sprite_screen_rect = camera.apply_rect(entity.rect)
        if sprite_screen_rect.colliderect(screen_rect_inflated):
            screen.blit(entity.image, sprite_screen_rect)
        if entity is player:
            player_screen_rect = sprite_screen_rect

    if zombie_group:
        for zombie in zombie_group:
            if not getattr(zombie, "tracker", False):
                continue
            sprite_screen_rect = camera.apply_rect(zombie.rect)
            if not sprite_screen_rect.colliderect(screen_rect_inflated):
                continue
            radius = int(
                getattr(
                    zombie,
                    "radius",
                    max(sprite_screen_rect.width, sprite_screen_rect.height) // 2,
                )
            )
            pygame.draw.circle(
                screen,
                DEBUG_TRACKER_OUTLINE_COLOR,
                sprite_screen_rect.center,
                radius + 1,
                width=1,
            )
        for zombie in zombie_group:
            if not getattr(zombie, "wall_follower", False):
                continue
            sprite_screen_rect = camera.apply_rect(zombie.rect)
            if not sprite_screen_rect.colliderect(screen_rect_inflated):
                continue
            radius = int(
                getattr(
                    zombie,
                    "radius",
                    max(sprite_screen_rect.width, sprite_screen_rect.height) // 2,
                )
            )
            pygame.draw.circle(
                screen,
                DEBUG_WALL_FOLLOWER_OUTLINE_COLOR,
                sprite_screen_rect.center,
                radius + 1,
                width=1,
            )

    if player_screen_rect is None:
        player_screen_rect = camera.apply_rect(player.rect)

    if has_fuel and player_screen_rect and not player.in_car:
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

    if hint_target and player:
        current_fov_scale = get_fog_scale(
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

    if fov_target is not None:
        fov_center_on_screen = list(camera.apply(fov_target).center)
        cam_rect = camera.camera
        horizontal_span = camera.width - assets.screen_width
        vertical_span = camera.height - assets.screen_height
        if horizontal_span <= 0 or (cam_rect.x != 0 and cam_rect.x != -horizontal_span):
            fov_center_on_screen[0] = assets.screen_width // 2
        if vertical_span <= 0 or (cam_rect.y != 0 and cam_rect.y != -vertical_span):
            fov_center_on_screen[1] = assets.screen_height // 2
        fov_center_tuple = (int(fov_center_on_screen[0]), int(fov_center_on_screen[1]))
        if state.dawn_ready:
            profile = FogProfile.DAWN
        else:
            profile = FogProfile.from_flashlight_count(flashlight_count)
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

    if not has_fuel and fuel_message_until > elapsed_play_ms:
        show_message(
            screen,
            tr("hud.need_fuel"),
            18,
            ORANGE,
            (assets.screen_width // 2, assets.screen_height // 2),
        )

    def _render_objective(lines: list[str]) -> None:
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

    def _render_survival_timer() -> None:
        if not (stage and getattr(stage, "survival_stage", False)):
            return
        goal_ms = getattr(state, "survival_goal_ms", 0)
        if goal_ms <= 0:
            return
        elapsed_ms = max(0, min(goal_ms, getattr(state, "survival_elapsed_ms", 0)))
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
        track_surface = pygame.Surface(
            (bar_rect.width, bar_rect.height), pygame.SRCALPHA
        )
        track_surface.fill((0, 0, 0, 140))
        screen.blit(track_surface, bar_rect.topleft)
        progress_ratio = elapsed_ms / goal_ms if goal_ms else 0.0
        progress_width = int(bar_rect.width * max(0.0, min(1.0, progress_ratio)))
        if progress_width > 0:
            fill_color = (120, 20, 20)
            if getattr(state, "dawn_ready", False):
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
        timer_text = tr("hud.survival_timer_label", time=display_label)
        try:
            font_settings = get_font_settings()
            font = load_font(font_settings.resource, font_settings.scaled_size(12))
            text_surface = font.render(timer_text, False, LIGHT_GRAY)
            text_rect = text_surface.get_rect(
                left=bar_rect.left, bottom=bar_rect.top - 2
            )
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
            print(f"Error rendering survival timer: {e}")

    def _render_time_accel_indicator() -> None:
        if stage and getattr(stage, "survival_stage", False):
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

    objective_lines: list[str] = []
    if stage and getattr(stage, "survival_stage", False):
        if state.dawn_ready:
            objective_lines.append(tr("objectives.get_outside"))
        else:
            objective_lines.append(tr("objectives.survive_until_dawn"))
    elif stage and stage.requires_fuel and not has_fuel:
        objective_lines.append(tr("objectives.find_fuel"))
    elif stage and getattr(stage, "rescue_stage", False):
        if not player.in_car:
            objective_lines.append(tr("objectives.find_car"))
        else:
            objective_lines.append(tr("objectives.escape_with_survivors"))
    elif not player.in_car:
        objective_lines.append(tr("objectives.find_car"))
    else:
        objective_lines.append(tr("objectives.escape"))

    if stage and getattr(stage, "companion_stage", False):
        if not companion_rescued:
            buddy_following = companion and getattr(companion, "following", False)
            if player.in_car:
                # Cannot escape until the buddy is picked up; suppress the redundant find prompt.
                objective_lines[-1] = tr("objectives.pickup_buddy")
            elif not buddy_following:
                objective_lines.append(tr("objectives.find_buddy"))

    if (
        stage
        and getattr(stage, "rescue_stage", False)
        and (survivors_onboard is not None)
    ):
        limit = getattr(state, "survivor_capacity", SURVIVOR_MAX_SAFE_PASSENGERS)
        objective_lines.append(
            tr("objectives.survivors_onboard", count=survivors_onboard, limit=limit)
        )

    if objective_lines:
        _render_objective(objective_lines)
    if survivor_messages:
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
    if stage and getattr(stage, "survival_stage", False):
        _render_survival_timer()
    else:
        _render_time_accel_indicator()
    draw_status_bar(
        screen,
        assets,
        config,
        stage=stage,
        seed=state.seed,
        debug_mode=bool(getattr(state, "debug_mode", False)),
        zombie_group=zombie_group,
    )
    if do_flip:
        if present_fn:
            present_fn(screen)
        else:
            pygame.display.flip()
