from __future__ import annotations

from typing import Any

import pygame
from pygame import surface, time

from ..colors import GREEN, LIGHT_GRAY, RED, WHITE
from ..font_utils import load_font, render_text_surface
from ..gameplay_constants import SURVIVAL_FAKE_CLOCK_RATIO
from ..input_utils import (
    ClickTarget,
    ClickableMap,
    CommonAction,
    InputHelper,
    KeyboardShortcut,
    MouseUiGuard,
)
from ..localization import get_font_settings
from ..localization import translate as tr
from ..models import GameData, Stage
from ..overview import draw_debug_overview
from ..render import RenderAssets
from ..screens import ScreenID, ScreenTransition
from ..windowing import nudge_window_scale, present, sync_window_size, toggle_fullscreen


def game_over_screen(
    screen: surface.Surface,
    clock: time.Clock,
    config: dict[str, Any],
    fps: int,
    *,
    game_data: GameData | None,
    stage: Stage | None,
    render_assets: RenderAssets,
) -> ScreenTransition:
    """Display the game-over overview until the player chooses the next step."""

    if not game_data:
        return ScreenTransition(ScreenID.TITLE)

    state = game_data.state
    input_helper = InputHelper()
    pygame.mouse.set_visible(True)
    options: list[dict[str, str]] = [
        {"id": "title", "label": tr("game_over.menu_title")}
    ]
    if stage is not None:
        options.append({"id": "retry", "label": tr("game_over.menu_retry")})
    selected = 0
    option_click_map = ClickableMap()
    mouse_ui_guard = MouseUiGuard()
    overview_surface: surface.Surface | None = None

    def _activate_option(option_id: str) -> ScreenTransition:
        if option_id == "retry" and stage is not None:
            return ScreenTransition(
                ScreenID.GAMEPLAY,
                stage=stage,
                seed=state.seed,
            )
        return ScreenTransition(ScreenID.TITLE)

    def _draw_message_box(
        lines: list[tuple[str, tuple[int, int, int]]],
        *,
        center: tuple[int, int],
        size: int = 11,
    ) -> None:
        if not lines:
            return
        font_settings = get_font_settings()
        font = load_font(font_settings.resource, font_settings.scaled_size(size))
        line_height = int(round(font.get_linesize() * font_settings.line_height_scale))
        line_spacing = 2
        rendered = [
            render_text_surface(
                font, text, color, line_height_scale=font_settings.line_height_scale
            )
            for text, color in lines
        ]
        max_width = max(s.get_width() for s in rendered)
        total_height = line_height * len(rendered) + line_spacing * (len(rendered) - 1)
        bg_padding = 15
        bg_rect = pygame.Rect(
            0, 0, max_width + bg_padding * 2, total_height + bg_padding * 2
        )
        bg_rect.center = center
        bg_surface = pygame.Surface((bg_rect.width, bg_rect.height), pygame.SRCALPHA)
        bg_surface.fill((0, 0, 0, 180))
        screen.blit(bg_surface, bg_rect.topleft)
        y = center[1] - total_height // 2
        for line_surface in rendered:
            text_rect = line_surface.get_rect(centerx=center[0], y=y)
            screen.blit(line_surface, text_rect)
            y += line_height + line_spacing

    while True:
        screen_width = screen.get_width()
        screen_height = screen.get_height()
        level_rect = game_data.layout.field_rect
        level_size = (level_rect.width, level_rect.height)
        if overview_surface is None or overview_surface.get_size() != level_size:
            overview_surface = pygame.Surface(level_size)
        overview_height = max(1, screen_height - render_assets.status_bar_height)
        draw_debug_overview(
            render_assets,
            screen,
            overview_surface,
            game_data,
            config,
            screen_width=screen_width,
            screen_height=overview_height,
            show_debug_counts=True,
        )
        headline_lines: list[tuple[str, tuple[int, int, int]]] = []
        if state.game_won:
            headline_lines.append((tr("game_over.win"), GREEN))
        else:
            headline_lines.append((tr("game_over.lose"), RED))
        if stage and (
            stage.survivor_rescue_stage
            or stage.survivor_spawn_rate > 0.0
            or stage.buddy_required_count > 0
        ):
            total_rescued = state.survivors_rescued + state.buddy_rescued
            headline_lines.append(
                (tr("game_over.survivors_summary", count=total_rescued), LIGHT_GRAY)
            )
        elif stage and stage.endurance_stage:
            elapsed_ms = max(0, state.endurance_elapsed_ms)
            goal_ms = max(0, state.endurance_goal_ms)
            if goal_ms:
                elapsed_ms = min(elapsed_ms, goal_ms)
            display_ms = int(elapsed_ms * SURVIVAL_FAKE_CLOCK_RATIO)
            hours = display_ms // 3_600_000
            minutes = (display_ms % 3_600_000) // 60_000
            time_label = f"{int(hours):02d}:{int(minutes):02d}"
            headline_lines.append(
                (tr("game_over.endurance_duration", time=time_label), LIGHT_GRAY)
            )
        _draw_message_box(
            headline_lines,
            center=(screen_width // 2, screen_height // 2 - 18),
            size=11,
        )

        font_settings = get_font_settings()
        menu_font = load_font(font_settings.resource, font_settings.scaled_size(11))
        line_height = int(
            round(menu_font.get_linesize() * font_settings.line_height_scale)
        )
        row_height = line_height + 6
        menu_center_x = screen_width // 2
        menu_top = screen_height // 2 + 18
        menu_width = max(140, int(screen_width * 0.32))
        option_targets: list[ClickTarget] = []
        highlight_color = (70, 70, 70)
        for idx, option in enumerate(options):
            row_rect = pygame.Rect(
                menu_center_x - menu_width // 2,
                menu_top + idx * row_height,
                menu_width,
                row_height,
            )
            option_targets.append(ClickTarget(idx, row_rect))
            if idx == selected:
                pygame.draw.rect(screen, highlight_color, row_rect)
            label_surface = menu_font.render(option["label"], False, WHITE)
            label_rect = label_surface.get_rect(center=row_rect.center)
            screen.blit(label_surface, label_rect)
        option_click_map.set_targets(option_targets)

        present(screen)
        clock.tick(fps)

        events = pygame.event.get()
        for event in events:
            if event.type == pygame.QUIT:
                return ScreenTransition(ScreenID.EXIT)
            if event.type in (pygame.WINDOWSIZECHANGED, pygame.VIDEORESIZE):
                sync_window_size(event, game_data=game_data)
                continue
            if event.type == pygame.WINDOWFOCUSLOST:
                mouse_ui_guard.handle_focus_event(event)
                continue
            if event.type == pygame.WINDOWFOCUSGAINED:
                mouse_ui_guard.handle_focus_event(event)
                continue
            if event.type == pygame.MOUSEMOTION and mouse_ui_guard.can_process_mouse():
                hover_target = option_click_map.pick_hover(event.pos)
                if isinstance(hover_target, int):
                    selected = hover_target
                continue
            if (
                event.type == pygame.MOUSEBUTTONUP
                and event.button == 1
                and mouse_ui_guard.can_process_mouse()
            ):
                clicked_target = option_click_map.pick_click(event.pos)
                if isinstance(clicked_target, int):
                    selected = clicked_target
                    return _activate_option(options[clicked_target]["id"])
                continue
            input_helper.handle_device_event(event)

        snapshot = input_helper.snapshot(events, pygame.key.get_pressed())
        if snapshot.shortcut_pressed(KeyboardShortcut.WINDOW_SCALE_DOWN):
            nudge_window_scale(0.5, game_data=game_data)
        if snapshot.shortcut_pressed(KeyboardShortcut.WINDOW_SCALE_UP):
            nudge_window_scale(2.0, game_data=game_data)
        if snapshot.shortcut_pressed(KeyboardShortcut.TOGGLE_FULLSCREEN):
            toggle_fullscreen(game_data=game_data)
        if snapshot.shortcut_pressed(KeyboardShortcut.RETRY) and stage is not None:
            return _activate_option("retry")
        if snapshot.pressed(CommonAction.UP):
            selected = (selected - 1) % len(options)
        if snapshot.pressed(CommonAction.DOWN):
            selected = (selected + 1) % len(options)
        if snapshot.pressed(CommonAction.START) and stage is not None:
            return _activate_option("retry")
        if snapshot.pressed(CommonAction.BACK):
            return ScreenTransition(ScreenID.TITLE)
        if snapshot.pressed(CommonAction.CONFIRM):
            return _activate_option(options[selected]["id"])
        mouse_ui_guard.end_frame()
