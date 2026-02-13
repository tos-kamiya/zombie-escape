from __future__ import annotations

import math
from typing import Any

import pygame
from pygame import sprite, surface

from ..colors import LIGHT_GRAY, ORANGE, YELLOW
from ..entities import Camera, Car, Player
from ..entities_constants import (
    CAR_HEIGHT,
    CAR_WIDTH,
    FLASHLIGHT_HEIGHT,
    FLASHLIGHT_WIDTH,
    FUEL_CAN_HEIGHT,
    FUEL_CAN_WIDTH,
    SHOES_HEIGHT,
    SHOES_WIDTH,
)
from ..font_utils import load_font, render_text_surface
from ..gameplay_constants import SURVIVAL_FAKE_CLOCK_RATIO
from ..localization import get_font_settings
from ..localization import translate as tr
from ..entities_constants import ZombieKind
from ..models import Stage, TimedMessage
from ..render_assets import (
    RenderAssets,
    build_car_surface,
    build_empty_fuel_can_surface,
    build_flashlight_surface,
    build_fuel_can_surface,
    build_shoes_surface,
    paint_car_surface,
    resolve_car_color,
)
from ..render_constants import (
    FLASHLIGHT_FOG_SCALE_ONE,
    FLASHLIGHT_FOG_SCALE_TWO,
    GAMEPLAY_FONT_SIZE,
    HUD_ICON_SIZE,
    TIMED_MESSAGE_BAND_ALPHA,
    TIMED_MESSAGE_LEFT_X,
    TIMED_MESSAGE_TOP_Y,
)

_HUD_ICON_CACHE: dict[str, surface.Surface] = {}


def _scale_icon_to_box(icon: surface.Surface, size: int) -> surface.Surface:
    target_size = max(1, size)
    width = max(1, icon.get_width())
    height = max(1, icon.get_height())
    scale = min(target_size / width, target_size / height)
    target_width = max(1, int(width * scale))
    target_height = max(1, int(height * scale))
    scaled = pygame.transform.smoothscale(icon, (target_width, target_height))
    boxed = pygame.Surface((target_size, target_size), pygame.SRCALPHA)
    boxed.blit(
        scaled,
        (
            (target_size - target_width) // 2,
            (target_size - target_height) // 2,
        ),
    )
    return boxed


def _get_hud_icon(kind: str) -> surface.Surface:
    cached = _HUD_ICON_CACHE.get(kind)
    if cached is not None:
        return cached
    if kind == "fuel":
        icon = build_fuel_can_surface(FUEL_CAN_WIDTH, FUEL_CAN_HEIGHT)
    elif kind == "empty_fuel":
        icon = build_empty_fuel_can_surface(FUEL_CAN_WIDTH, FUEL_CAN_HEIGHT)
    elif kind == "car":
        icon = build_car_surface(CAR_WIDTH, CAR_HEIGHT)
        paint_car_surface(
            icon,
            width=CAR_WIDTH,
            height=CAR_HEIGHT,
            color=resolve_car_color(health_ratio=1.0, appearance="default"),
        )
    elif kind == "flashlight":
        icon = build_flashlight_surface(FLASHLIGHT_WIDTH, FLASHLIGHT_HEIGHT)
    elif kind == "shoes":
        icon = build_shoes_surface(SHOES_WIDTH, SHOES_HEIGHT)
    else:
        icon = pygame.Surface((1, 1), pygame.SRCALPHA)
    icon = _scale_icon_to_box(icon, HUD_ICON_SIZE)
    _HUD_ICON_CACHE[kind] = icon
    return icon


def build_zombie_debug_counts_text(
    *,
    zombie_group: sprite.Group | None,
    lineformer_marker_count: int | None = None,
    falling_spawn_carry: int | None = None,
) -> str | None:
    """Build the shared zombie debug summary text used in HUD/overview."""
    if zombie_group is None:
        return None
    zombies = [z for z in zombie_group if z.alive()]
    total = len(zombies)
    kinds = [getattr(z, "kind", None) for z in zombies]
    tracker = sum(1 for kind in kinds if kind == ZombieKind.TRACKER)
    wall = sum(1 for kind in kinds if kind == ZombieKind.WALL_HUGGER)
    lineformer = sum(1 for kind in kinds if kind == ZombieKind.LINEFORMER)
    marker_count = max(0, int(lineformer_marker_count or 0))
    lineformer_total = lineformer + marker_count
    dog_count = sum(1 for kind in kinds if kind == ZombieKind.DOG)
    normal = max(0, total - tracker - wall - lineformer - dog_count)
    debug_counts = (
        f"Z:{total} N:{normal} T:{tracker} W:{wall} "
        f"L:{lineformer}({lineformer_total}) D:{dog_count}"
    )
    if falling_spawn_carry is not None:
        debug_counts = f"{debug_counts} C:{max(0, falling_spawn_carry)}"
    return debug_counts


def _draw_status_bar(
    screen: surface.Surface,
    assets: RenderAssets,
    config: dict[str, Any],
    *,
    stage: Stage | None = None,
    seed: int | None = None,
    debug_mode: bool = False,
    zombie_group: sprite.Group | None = None,
    lineformer_marker_count: int | None = None,
    falling_spawn_carry: int | None = None,
    show_fps: bool = False,
    fps: float | None = None,
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
        if stage.id.startswith("stage"):
            stage_suffix = stage.id.removeprefix("stage")
            stage_label = f"#{stage_suffix}" if stage_suffix else stage.id
        else:
            stage_label = stage.id
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
    debug_counts: str | None = None
    if debug_mode:
        debug_counts = build_zombie_debug_counts_text(
            zombie_group=zombie_group,
            lineformer_marker_count=lineformer_marker_count,
            falling_spawn_carry=falling_spawn_carry,
        )
    status_text = " | ".join(parts)
    color = LIGHT_GRAY

    try:
        font_settings = get_font_settings()
        font = load_font(
            font_settings.resource, font_settings.scaled_size(GAMEPLAY_FONT_SIZE)
        )
        text_surface = render_text_surface(
            font, status_text, color, line_height_scale=font_settings.line_height_scale
        )
        text_rect = text_surface.get_rect(left=12, centery=bar_rect.centery)
        screen.blit(text_surface, text_rect)
        if seed is not None:
            seed_text = tr("status.seed", value=str(seed))
            seed_surface = render_text_surface(
                font,
                seed_text,
                LIGHT_GRAY,
                line_height_scale=font_settings.line_height_scale,
            )
            seed_rect = seed_surface.get_rect(
                right=bar_rect.right - 12, centery=bar_rect.centery
            )
            screen.blit(seed_surface, seed_rect)
        overlay_bottom = max(2, bar_rect.top)
        overlay_left = 12
        if show_fps:
            fps_text = f"FPS:{fps:.1f}" if fps is not None else "FPS:-.-"
            fps_surface = render_text_surface(
                font,
                fps_text,
                LIGHT_GRAY,
                line_height_scale=font_settings.line_height_scale,
            )
            fps_rect = fps_surface.get_rect(left=overlay_left, bottom=overlay_bottom)
            screen.blit(fps_surface, fps_rect)
            fps_max_width = font.size("FPS:999.9")[0]
            overlay_left += fps_max_width + 8
        if debug_counts:
            debug_surface = render_text_surface(
                font,
                debug_counts,
                LIGHT_GRAY,
                line_height_scale=font_settings.line_height_scale,
            )
            debug_rect = debug_surface.get_rect(left=overlay_left, bottom=overlay_bottom)
            screen.blit(debug_surface, debug_rect)
    except pygame.error as e:
        print(f"Error rendering status bar: {e}")


def _draw_objective(lines: list[str], *, screen: surface.Surface) -> None:
    try:
        font_settings = get_font_settings()
        font = load_font(
            font_settings.resource, font_settings.scaled_size(GAMEPLAY_FONT_SIZE)
        )
        y = 8
        for line in lines:
            text_surface = render_text_surface(
                font, line, YELLOW, line_height_scale=font_settings.line_height_scale
            )
            text_rect = text_surface.get_rect(topleft=(12, y))
            screen.blit(text_surface, text_rect)
            y += text_rect.height + 4
    except pygame.error as e:
        print(f"Error rendering objective: {e}")


def _draw_inventory_icons(
    screen: surface.Surface,
    assets: RenderAssets,
    *,
    has_fuel: bool,
    has_empty_fuel_can: bool,
    flashlight_count: int,
    shoes_count: int,
    player_in_car: bool = False,
    buddy_onboard: int = 0,
    survivors_onboard: int = 0,
    passenger_capacity: int = 0,
) -> None:
    spacing = 3
    padding = 8
    y = 8
    right_edge = assets.screen_width - padding

    passenger_icon: surface.Surface | None = None
    passenger_surface: surface.Surface | None = None
    passenger_bottom_pad = 0
    if player_in_car:
        try:
            font_settings = get_font_settings()
            font = load_font(
                font_settings.resource, font_settings.scaled_size(GAMEPLAY_FONT_SIZE)
            )
            passenger_text = tr(
                "hud.passengers_compact",
                crew=max(0, int(buddy_onboard)),
                survivors=max(0, int(survivors_onboard)),
                limit=max(0, int(passenger_capacity)),
            )
            passenger_surface = render_text_surface(
                font,
                passenger_text,
                LIGHT_GRAY,
                line_height_scale=font_settings.line_height_scale,
            )
            raw_text_surface = font.render(passenger_text, False, LIGHT_GRAY)
            line_height = int(
                round(font.get_linesize() * max(0.0, font_settings.line_height_scale))
            )
            extra_height = max(0, line_height - raw_text_surface.get_height())
            passenger_bottom_pad = extra_height - (extra_height // 2)
            passenger_icon = _get_hud_icon("car")
        except pygame.error as e:
            print(f"Error rendering passenger info: {e}")

    reserved_right = right_edge
    if passenger_icon is not None and passenger_surface is not None:
        passenger_width = (
            passenger_icon.get_width() + spacing + passenger_surface.get_width()
        )
        reserved_right -= passenger_width + (spacing * 2)

    icons: list[surface.Surface] = []
    if has_fuel:
        icons.append(_get_hud_icon("fuel"))
    elif has_empty_fuel_can:
        icons.append(_get_hud_icon("empty_fuel"))
    for _ in range(max(0, int(flashlight_count))):
        icons.append(_get_hud_icon("flashlight"))
    for _ in range(max(0, int(shoes_count))):
        icons.append(_get_hud_icon("shoes"))
    if icons:
        total_width = sum(icon.get_width() for icon in icons)
        total_width += spacing * max(0, len(icons) - 1)
        start_x = reserved_right - total_width
        x = max(padding, start_x)
        for icon in icons:
            screen.blit(icon, (x, y))
            x += icon.get_width() + spacing

    if passenger_icon is not None and passenger_surface is not None:
        text_rect = passenger_surface.get_rect(right=right_edge)
        icon_rect = passenger_icon.get_rect(
            right=text_rect.left - spacing,
            top=y,
        )
        text_rect.bottom = icon_rect.bottom + passenger_bottom_pad
        screen.blit(passenger_icon, icon_rect)
        screen.blit(passenger_surface, text_rect)


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
    bar_height = 6
    text_bottom = assets.screen_height - assets.status_bar_height - bar_height - 8
    bar_overlap = 6
    y_pos = text_bottom + 2 - bar_overlap
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
        fill_color = (120, 20, 20, 160)
        if state.dawn_ready:
            fill_color = (25, 40, 120, 160)
        fill_rect = pygame.Rect(
            bar_rect.left,
            bar_rect.top,
            progress_width,
            bar_rect.height,
        )
        fill_surface = pygame.Surface(
            (progress_width, bar_rect.height), pygame.SRCALPHA
        )
        fill_surface.fill(fill_color)
        screen.blit(fill_surface, fill_rect.topleft)
    display_ms = int(remaining_ms * SURVIVAL_FAKE_CLOCK_RATIO)
    display_ms = max(0, display_ms)
    display_hours = display_ms // 3_600_000
    display_minutes = (display_ms % 3_600_000) // 60_000
    display_label = f"{int(display_hours):02d}:{int(display_minutes):02d}"
    timer_text = tr("hud.endurance_timer_label", time=display_label)
    try:
        font_settings = get_font_settings()
        font = load_font(
            font_settings.resource, font_settings.scaled_size(GAMEPLAY_FONT_SIZE)
        )
        text_surface = render_text_surface(
            font,
            timer_text,
            LIGHT_GRAY,
            line_height_scale=font_settings.line_height_scale,
        )
        text_rect = text_surface.get_rect(left=bar_rect.left, bottom=text_bottom)
        screen.blit(text_surface, text_rect)
        if state.time_accel_active:
            accel_text = tr("hud.time_accel")
            accel_surface = render_text_surface(
                font, accel_text, YELLOW, line_height_scale=font_settings.line_height_scale
            )
            accel_rect = accel_surface.get_rect(
                right=bar_rect.right, bottom=text_bottom
            )
            screen.blit(accel_surface, accel_rect)
        else:
            hint_text = tr("hud.time_accel_hint")
            hint_surface = render_text_surface(
                font,
                hint_text,
                LIGHT_GRAY,
                line_height_scale=font_settings.line_height_scale,
            )
            hint_rect = hint_surface.get_rect(right=bar_rect.right, bottom=text_bottom)
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
        font = load_font(
            font_settings.resource, font_settings.scaled_size(GAMEPLAY_FONT_SIZE)
        )
        if state.time_accel_active:
            text = tr("hud.time_accel")
            color = YELLOW
        else:
            text = tr("hud.time_accel_hint")
            color = LIGHT_GRAY
        text_surface = render_text_surface(
            font, text, color, line_height_scale=font_settings.line_height_scale
        )
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
        font_size = font_settings.scaled_size(GAMEPLAY_FONT_SIZE * 2)
        font = load_font(font_settings.resource, font_size)
        line_height = int(round(font.get_linesize() * 2))
        base_y = assets.screen_height // 2 - (line_height * 2)
        for idx, message in enumerate(survivor_messages[:5]):
            text = message.get("text", "")
            if not text:
                continue
            msg_surface = render_text_surface(
                font, text, ORANGE, line_height_scale=font_settings.line_height_scale
            )
            msg_rect = msg_surface.get_rect(
                center=(assets.screen_width // 2, base_y + idx * line_height)
            )
            screen.blit(msg_surface, msg_rect)
    except pygame.error as e:
        print(f"Error rendering survivor message: {e}")


def _draw_timed_message(
    screen: surface.Surface,
    assets: RenderAssets,
    *,
    message: TimedMessage | None,
    elapsed_play_ms: int,
) -> None:
    if not message:
        return
    if message.expires_at_ms <= 0:
        return
    if elapsed_play_ms > message.expires_at_ms:
        return
    try:
        font_settings = get_font_settings()
        font_size = font_settings.scaled_size(GAMEPLAY_FONT_SIZE * 2)
        font = load_font(font_settings.resource, font_size)
        text_color = message.color or LIGHT_GRAY
        line_height = int(round(font.get_linesize() * font_settings.line_height_scale))
        lines = message.text.splitlines() or [message.text]
        rendered_lines = [
            render_text_surface(
                font, line, text_color, line_height_scale=font_settings.line_height_scale
            )
            for line in lines
        ]
        max_width = max(surface.get_width() for surface in rendered_lines)
        total_height = line_height * len(rendered_lines)
        if message.align == "left":
            text_rect = pygame.Rect(
                TIMED_MESSAGE_LEFT_X, TIMED_MESSAGE_TOP_Y, max_width, total_height
            )
        else:
            center_x = assets.screen_width // 2
            center_y = assets.screen_height // 2
            text_rect = pygame.Rect(0, 0, max_width, total_height)
            text_rect.center = (center_x, center_y)
        padding_x = 16
        padding_y = max(8, int(round(line_height * 0.35)))
        band_rect = text_rect.inflate(padding_x * 2, padding_y * 2)
        band_surface = pygame.Surface(band_rect.size, pygame.SRCALPHA)
        band_surface.fill((0, 0, 0, TIMED_MESSAGE_BAND_ALPHA))
        screen.blit(band_surface, band_rect.topleft)
        y = text_rect.top
        for surface in rendered_lines:
            if message.align == "left":
                line_rect = surface.get_rect(topleft=(text_rect.left, y))
            else:
                line_rect = surface.get_rect(centerx=text_rect.centerx, y=y)
            screen.blit(surface, line_rect)
            y += line_height
    except pygame.error as e:
        print(f"Error rendering timed message: {e}")


def _build_objective_lines(
    *,
    stage: Stage | None,
    state: Any,
    player: Player,
    active_car: Car | None,
    has_fuel: bool,
    has_empty_fuel_can: bool,
    buddy_merged_count: int,
    buddy_required: int,
) -> list[str]:
    objective_lines: list[str] = []
    if stage and stage.endurance_stage:
        if state.dawn_ready:
            objective_lines.append(tr("objectives.get_outside"))
        else:
            objective_lines.append(tr("objectives.survive_until_dawn"))
        if stage.buddy_required_count > 0:
            buddy_ready = buddy_merged_count >= buddy_required
            if not buddy_ready:
                if buddy_required == 1:
                    objective_lines.append(tr("objectives.merge_buddy_single"))
                else:
                    objective_lines.append(
                        tr(
                            "objectives.merge_buddy_multi",
                            count=buddy_merged_count,
                            limit=buddy_required,
                        )
                    )
        return objective_lines

    if stage and stage.buddy_required_count > 0:
        buddy_ready = buddy_merged_count >= buddy_required
        if not buddy_ready:
            if buddy_required == 1:
                objective_lines.append(tr("objectives.merge_buddy_single"))
            else:
                objective_lines.append(
                    tr(
                        "objectives.merge_buddy_multi",
                        count=buddy_merged_count,
                        limit=buddy_required,
                    )
                )
        if not stage.endurance_stage:
            if not active_car:
                if stage.requires_refuel and not has_fuel:
                    if not has_empty_fuel_can:
                        objective_lines.append(tr("objectives.find_empty_fuel_can"))
                    else:
                        objective_lines.append(tr("objectives.refuel_at_station"))
                elif stage.requires_fuel and not has_fuel:
                    objective_lines.append(tr("objectives.find_fuel"))
                else:
                    objective_lines.append(tr("objectives.find_car"))
            else:
                if stage.requires_refuel and not has_fuel:
                    if not has_empty_fuel_can:
                        objective_lines.append(tr("objectives.find_empty_fuel_can"))
                    else:
                        objective_lines.append(tr("objectives.refuel_at_station"))
                elif stage.requires_fuel and not has_fuel:
                    objective_lines.append(tr("objectives.find_fuel"))
                else:
                    objective_lines.append(tr("objectives.escape"))
    elif stage and stage.requires_refuel and not has_fuel:
        if not has_empty_fuel_can:
            objective_lines.append(tr("objectives.find_empty_fuel_can"))
        else:
            objective_lines.append(tr("objectives.refuel_at_station"))
    elif stage and stage.requires_fuel and not has_fuel:
        objective_lines.append(tr("objectives.find_fuel"))
    elif stage and stage.survivor_rescue_stage:
        if not player.in_car:
            objective_lines.append(tr("objectives.find_car"))
        else:
            objective_lines.append(tr("objectives.escape_with_survivors"))
    elif not player.in_car:
        objective_lines.append(tr("objectives.find_car"))
    else:
        objective_lines.append(tr("objectives.escape"))

    return objective_lines


def _get_fog_scale(
    assets: RenderAssets,
    flashlight_count: int,
) -> float:
    """Return current fog scale factoring in flashlight bonus."""
    scale = assets.fog_radius_scale
    flashlight_count = max(0, int(flashlight_count))
    if flashlight_count <= 0:
        return scale
    if flashlight_count == 1:
        return max(scale, FLASHLIGHT_FOG_SCALE_ONE)
    return max(scale, FLASHLIGHT_FOG_SCALE_TWO)


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
    if dist < assets.fov_radius * 0.7:
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
    current_fov_scale = _get_fog_scale(assets, flashlight_count)
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
