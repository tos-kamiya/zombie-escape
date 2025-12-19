from __future__ import annotations

import math
from dataclasses import dataclass
from typing import List, Tuple

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
    fog_max_radius_factor: float
    fog_hatch_pixel_scale: int
    fog_rings: List[FogRing]
    footprint_radius: int
    footprint_overview_radius: int
    footprint_lifetime_ms: int
    footprint_min_fade: float
    internal_wall_grid_snap: int
    default_flashlight_bonus_scale: float


def show_message(
    screen: surface.Surface,
    text: str,
    size: int,
    color: Tuple[int, int, int],
    position: Tuple[int, int],
) -> None:
    try:
        font = load_font(size)
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
    player,
    car,
    footprints,
    fuel=None,
    flashlights=None,
    stage=None,
    companion=None,
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
    assets: RenderAssets, stage, has_flashlight: bool, config: dict | None = None
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
    fog_data, thickness: int, pixel_scale: int = 1
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


def _blit_hatch_ring(
    screen,
    overlay: surface.Surface,
    pattern: surface.Surface,
    clear_center,
    radius: float,
):
    """Draw a single hatched fog ring using pattern transparency only (no global alpha)."""
    overlay.fill((0, 0, 0, 0))
    p_w, p_h = pattern.get_size()
    for y in range(0, overlay.get_height(), p_h):
        for x in range(0, overlay.get_width(), p_w):
            overlay.blit(pattern, (x, y))
    pygame.draw.circle(overlay, (0, 0, 0, 0), clear_center, int(radius))
    screen.blit(overlay, (0, 0))


def _draw_hint_arrow(
    screen,
    camera,
    assets: RenderAssets,
    player,
    target_pos: Tuple[int, int],
    color=None,
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


def _draw_status_bar(screen, assets: RenderAssets, config, stage=None):
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
    try:
        flashlight_scale = float(
            flashlight_conf.get("bonus_scale", assets.default_flashlight_bonus_scale)
        )
    except (TypeError, ValueError):
        flashlight_scale = assets.default_flashlight_bonus_scale
    steel_on = config.get("steel_beams", {}).get("enabled", False)
    if stage:
        # Keep the label compact for the status bar
        stage_label = f"#{stage.id[-1]}" if stage.id.startswith("stage") else stage.id
    else:
        stage_label = "#1"

    parts = [f"Stage {stage_label}"]
    if footprints_on:
        parts.append("Footprints")
    if fast_on:
        parts.append("FastZ")
    if hint_on:
        parts.append("CarHint")
    if flashlight_on:
        parts.append("Flashlight")
    if steel_on:
        parts.append("Steel")

    status_text = " | ".join(parts)
    color = (
        GREEN if all([footprints_on, fast_on, hint_on, flashlight_on]) else LIGHT_GRAY
    )

    try:
        font = load_font(12)
        text_surface = font.render(status_text, False, color)
        text_rect = text_surface.get_rect(left=12, centery=bar_rect.centery)
        screen.blit(text_surface, text_rect)
    except pygame.error as e:
        print(f"Error rendering status bar: {e}")


def draw(
    assets: RenderAssets,
    screen,
    outer_rect,
    camera,
    all_sprites,
    fov_target,
    fog_surfaces,
    footprints,
    config,
    player,
    hint_target: Tuple[int, int] | None,
    hint_color=None,
    do_flip: bool = True,
    outside_rects: List[pygame.Rect] | None = None,
    stage=None,
    has_fuel: bool = False,
    has_flashlight: bool = False,
    elapsed_play_ms: int = 0,
    fuel_message_until: int = 0,
    companion=None,
    companion_rescued: bool = False,
    present_fn=None,
):
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

    for y in range(ys, ye):
        for x in range(xs, xe):
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

    for entity in all_sprites:
        sprite_screen_rect = camera.apply_rect(entity.rect)
        if sprite_screen_rect.colliderect(screen.get_rect().inflate(100, 100)):
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
        fov_center_on_screen = camera.apply(fov_target).center
        fog_hard = fog_surfaces["hard"]
        fog_soft = fog_surfaces["soft"]
        fog_scale = get_fog_scale(assets, stage, has_flashlight, config)

        fog_hard.fill(FOG_COLOR)
        max_radius = int(assets.fov_radius * assets.fog_max_radius_factor * fog_scale)
        pygame.draw.circle(fog_hard, (0, 0, 0, 0), fov_center_on_screen, max_radius)
        screen.blit(fog_hard, (0, 0))

        for ring in assets.fog_rings:
            radius = int(assets.fov_radius * ring.radius_factor * fog_scale)
            thickness = ring.thickness
            pattern = get_hatch_pattern(
                fog_surfaces, thickness, assets.fog_hatch_pixel_scale
            )
            _blit_hatch_ring(screen, fog_soft, pattern, fov_center_on_screen, radius)

    if not has_fuel and fuel_message_until > elapsed_play_ms:
        show_message(
            screen,
            "Need fuel to drive!",
            18,
            ORANGE,
            (assets.screen_width // 2, assets.screen_height // 2),
        )

    def _render_objective(lines: list[str]):
        try:
            font = load_font(18)
            y = 16
            for line in lines:
                text_surface = font.render(line, False, YELLOW)
                text_rect = text_surface.get_rect(topleft=(16, y))
                screen.blit(text_surface, text_rect)
                y += text_rect.height + 6
        except pygame.error as e:
            print(f"Error rendering objective: {e}")

    objective_lines: list[str] = []
    if stage and stage.requires_fuel and not has_fuel:
        objective_lines.append("Find the fuel can")
    elif not player.in_car:
        objective_lines.append("Find the car")
    else:
        objective_lines.append("Escape the building")

    if stage and getattr(stage, "requires_companion", False):
        if not companion_rescued:
            buddy_following = companion and getattr(companion, "following", False)
            if player.in_car:
                # Cannot escape until the buddy is picked up; suppress the redundant find prompt.
                objective_lines[-1] = "Pick up your buddy"
            elif not buddy_following:
                objective_lines.append("Find your buddy")

    if objective_lines:
        _render_objective(objective_lines)

    _draw_status_bar(screen, assets, config, stage=stage)
    if do_flip:
        if present_fn:
            present_fn(screen)
        else:
            pygame.display.flip()
