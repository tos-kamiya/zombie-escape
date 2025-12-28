from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Callable

import pygame
from pygame import sprite, surface

from .colors import (
    BLACK,
    BLUE,
    FLOOR_COLOR_OUTSIDE,
    FLOOR_COLOR_PRIMARY,
    FLOOR_COLOR_SECONDARY,
    FOG_COLOR,
    FOOTPRINT_COLOR,
    GREEN,
    INTERNAL_WALL_COLOR,
    LIGHT_GRAY,
    ORANGE,
    YELLOW,
)
from .font_utils import load_font
from .i18n import get_font_settings, translate as _
from .entities import Camera, Car, Companion, Flashlight, FuelCan, Player, Survivor
from .models import Stage
from .render_assets import FogRing, RenderAssets


@dataclass(frozen=True)
class SurvivorHUDInfo:
    onboard: int
    limit: int
    rescued: int


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
    footprints: list[dict[str, Any]],
    fuel: FuelCan | None = None,
    flashlights: list[Flashlight] | None = None,
    stage: Stage | None = None,
    companion: Companion | None = None,
    survivors: list[Survivor] | None = None,
) -> None:
    surface.fill(BLACK)
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
    if car and car.alive():
        car_rect = car.image.get_rect(center=car.rect.center)
        surface.blit(car.image, car_rect)


def get_fog_scale(
    assets: RenderAssets,
    stage: Stage | None,
    has_flashlight: bool,
    config: dict[str, Any] | None = None,
) -> float:
    """Return current fog scale factoring in flashlight bonus."""
    scale = assets.fog_radius_scale
    flashlight_conf = (config or {}).get("flashlight", {})
    flashlight_enabled = flashlight_conf.get("enabled", True)
    try:
        bonus_scale = float(
            flashlight_conf.get("bonus_scale", assets.default_flashlight_bonus_scale)
        )
    except (TypeError, ValueError):
        bonus_scale = assets.default_flashlight_bonus_scale
    if flashlight_enabled and has_flashlight:
        scale *= max(1.0, bonus_scale)
    return scale


def get_hatch_pattern(
    fog_data: dict[str, Any], thickness: int, pixel_scale: int = 1
) -> surface.Surface:
    """Return cached ordered-dither tile surface (Bayer-style, optionally chunky)."""
    cache = fog_data.setdefault("hatch_patterns", {})
    pixel_scale = max(1, pixel_scale)
    key = (thickness, pixel_scale)
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
                pattern.set_at((x, y), (0, 0, 0, 255))

    if pixel_scale > 1:
        scaled_size = (spacing * pixel_scale, spacing * pixel_scale)
        pattern = pygame.transform.scale(pattern, scaled_size)

    cache[key] = pattern
    return pattern


def _get_fog_overlay_surfaces(
    fog_data: dict[str, Any],
    assets: RenderAssets,
    scale: float,
) -> dict[str, Any]:
    overlays = fog_data.setdefault("overlays", {})
    key = round(scale, 4)
    if key in overlays:
        return overlays[key]

    max_radius = int(assets.fov_radius * assets.fog_max_radius_factor * scale)
    padding = 32
    coverage_width = max(assets.screen_width * 2, max_radius * 2)
    coverage_height = max(assets.screen_height * 2, max_radius * 2)
    width = coverage_width + padding * 2
    height = coverage_height + padding * 2
    center = (width // 2, height // 2)

    hard_surface = pygame.Surface((width, height), pygame.SRCALPHA)
    hard_surface.fill(FOG_COLOR)
    pygame.draw.circle(hard_surface, (0, 0, 0, 0), center, max_radius)

    ring_surfaces: list[surface.Surface] = []
    for ring in assets.fog_rings:
        ring_surface = pygame.Surface((width, height), pygame.SRCALPHA)
        pattern = get_hatch_pattern(
            fog_data, ring.thickness, assets.fog_hatch_pixel_scale
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

    overlay_entry = {
        "hard": hard_surface,
        "rings": ring_surfaces,
        "combined": combined_surface,
    }
    overlays[key] = overlay_entry
    return overlay_entry


def _draw_hint_arrow(
    screen: surface.Surface,
    camera: Camera,
    assets: RenderAssets,
    player: Player,
    target_pos: tuple[int, int],
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
    stage: Stage | None = None,
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
    flashlight_conf = config.get("flashlight", {})
    flashlight_on = flashlight_conf.get("enabled", True)
    steel_on = config.get("steel_beams", {}).get("enabled", False)
    if stage:
        # Keep the label compact for the status bar
        stage_label = f"#{stage.id[-1]}" if stage.id.startswith("stage") else stage.id
    else:
        stage_label = "#1"

    parts = [_("status.stage", label=stage_label)]
    if footprints_on:
        parts.append(_("status.footprints"))
    if fast_on:
        parts.append(_("status.fast"))
    if hint_on:
        parts.append(_("status.car_hint"))
    if flashlight_on:
        parts.append(_("status.flashlight"))
    if steel_on:
        parts.append(_("status.steel"))

    status_text = " | ".join(parts)
    color = (
        GREEN if all([footprints_on, fast_on, hint_on, flashlight_on]) else LIGHT_GRAY
    )

    try:
        font_settings = get_font_settings()
        font = load_font(font_settings.resource, font_settings.scaled_size(11))
        text_surface = font.render(status_text, False, color)
        text_rect = text_surface.get_rect(left=12, centery=bar_rect.centery)
        screen.blit(text_surface, text_rect)
    except pygame.error as e:
        print(f"Error rendering status bar: {e}")


def draw(
    assets: RenderAssets,
    screen: surface.Surface,
    outer_rect: tuple[int, int, int, int],
    camera: Camera,
    all_sprites: sprite.LayeredUpdates,
    fov_target: pygame.sprite.Sprite | None,
    fog_surfaces: dict[str, Any],
    footprints: list[dict[str, Any]],
    config: dict[str, Any],
    player: Player,
    hint_target: tuple[int, int] | None,
    hint_color: tuple[int, int, int] | None = None,
    do_flip: bool = True,
    outside_rects: list[pygame.Rect] | None = None,
    stage: Stage | None = None,
    has_fuel: bool = False,
    has_flashlight: bool = False,
    elapsed_play_ms: int = 0,
    fuel_message_until: int = 0,
    companion: Companion | None = None,
    companion_rescued: bool = False,
    survivor_info: SurvivorHUDInfo | None = None,
    survivor_messages: list[dict[str, Any]] | None = None,
    present_fn: Callable[[surface.Surface], None] | None = None,
) -> None:
    hint_color = hint_color or YELLOW
    screen.fill(FLOOR_COLOR_OUTSIDE)

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
    pygame.draw.rect(screen, FLOOR_COLOR_PRIMARY, play_area_screen_rect)

    outside_rects = outside_rects or []
    outside_cells = {
        (r.x // assets.internal_wall_grid_snap, r.y // assets.internal_wall_grid_snap)
        for r in outside_rects
    }
    for rect_obj in outside_rects:
        sr = camera.apply_rect(rect_obj)
        if sr.colliderect(screen.get_rect()):
            pygame.draw.rect(screen, FLOOR_COLOR_OUTSIDE, sr)

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
            if (x + y) % 2 == 0:
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
                    pygame.draw.rect(screen, FLOOR_COLOR_SECONDARY, sr)

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
    for entity in all_sprites:
        sprite_screen_rect = camera.apply_rect(entity.rect)
        if sprite_screen_rect.colliderect(screen_rect_inflated):
            screen.blit(entity.image, sprite_screen_rect)

    if hint_target and player:
        current_fov_scale = get_fog_scale(assets, stage, has_flashlight, config)
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
        if horizontal_span <= 0 or (
            cam_rect.x != 0 and cam_rect.x != -horizontal_span
        ):
            fov_center_on_screen[0] = assets.screen_width // 2
        if vertical_span <= 0 or (
            cam_rect.y != 0 and cam_rect.y != -vertical_span
        ):
            fov_center_on_screen[1] = assets.screen_height // 2
        fov_center_tuple = (int(fov_center_on_screen[0]), int(fov_center_on_screen[1]))
        fog_scale = get_fog_scale(assets, stage, has_flashlight, config)
        overlay = _get_fog_overlay_surfaces(fog_surfaces, assets, fog_scale)
        combined_surface: surface.Surface = overlay["combined"]
        screen.blit(
            combined_surface,
            combined_surface.get_rect(center=fov_center_tuple),
        )

    if not has_fuel and fuel_message_until > elapsed_play_ms:
        show_message(
            screen,
            _("hud.need_fuel"),
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

    objective_lines: list[str] = []
    if stage and stage.requires_fuel and not has_fuel:
        objective_lines.append(_("objectives.find_fuel"))
    elif stage and getattr(stage, "survivor_stage", False):
        if not player.in_car:
            objective_lines.append(_("objectives.find_car"))
        else:
            objective_lines.append(_("objectives.escape_with_survivors"))
    elif not player.in_car:
        objective_lines.append(_("objectives.find_car"))
    else:
        objective_lines.append(_("objectives.escape"))

    if stage and getattr(stage, "requires_companion", False):
        if not companion_rescued:
            buddy_following = companion and getattr(companion, "following", False)
            if player.in_car:
                # Cannot escape until the buddy is picked up; suppress the redundant find prompt.
                objective_lines[-1] = _("objectives.pickup_buddy")
            elif not buddy_following:
                objective_lines.append(_("objectives.find_buddy"))

    if survivor_info:
        onboard = survivor_info.onboard
        limit = survivor_info.limit
        rescued = survivor_info.rescued
        objective_lines.append(
            _("objectives.survivors_onboard", count=onboard, limit=limit)
        )
        if rescued:
            objective_lines.append(
                _("objectives.survivors_rescued", count=rescued)
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
    _draw_status_bar(screen, assets, config, stage=stage)
    if do_flip:
        if present_fn:
            present_fn(screen)
        else:
            pygame.display.flip()
