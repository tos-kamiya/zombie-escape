from __future__ import annotations

from typing import Any

import pygame
from pygame import surface, time

from ..colors import BLACK, GREEN, LIGHT_GRAY, RED, WHITE
from ..localization import translate as tr
from ..models import GameData, Stage
from ..render import (
    RenderAssets,
    draw_level_overview,
    _draw_status_bar,
    show_message,
)
from ..input_utils import is_confirm_event, is_select_event
from ..screens import (
    ScreenID,
    ScreenTransition,
    present,
    sync_window_size,
)
from ..gameplay_constants import SURVIVAL_FAKE_CLOCK_RATIO


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

    screen_width = screen.get_width()
    screen_height = screen.get_height()
    state = game_data.state
    wall_group = game_data.groups.wall_group
    footprints_enabled = config.get("footprints", {}).get("enabled", True)

    while True:
        if not state.overview_created:
            level_rect = game_data.layout.outer_rect
            level_width = level_rect[2]
            level_height = level_rect[3]
            overview_surface = pygame.Surface((level_width, level_height))
            footprints_to_draw = state.footprints if footprints_enabled else []
            draw_level_overview(
                render_assets,
                overview_surface,
                wall_group,
                game_data.player,
                game_data.car,
                game_data.waiting_cars,
                footprints_to_draw,
                fuel=game_data.fuel,
                flashlights=game_data.flashlights or [],
                stage=stage,
                buddies=[
                    survivor
                    for survivor in game_data.groups.survivor_group
                    if survivor.alive() and survivor.is_buddy and not survivor.rescued
                ],
                survivors=list(game_data.groups.survivor_group),
                palette_key=state.ambient_palette_key,
            )

            level_aspect = level_width / max(1, level_height)
            screen_aspect = screen_width / max(1, screen_height)
            if level_aspect > screen_aspect:
                scaled_w = screen_width - 40
                scaled_h = int(scaled_w / level_aspect)
            else:
                scaled_h = screen_height - 40
                scaled_w = int(scaled_h * level_aspect)
            scaled_w = max(1, scaled_w)
            scaled_h = max(1, scaled_h)
            state.scaled_overview = pygame.transform.smoothscale(
                overview_surface, (scaled_w, scaled_h)
            )
            state.overview_created = True

        screen.fill(BLACK)
        if state.scaled_overview:
            screen.blit(
                state.scaled_overview,
                state.scaled_overview.get_rect(
                    center=(screen_width // 2, screen_height // 2)
                ),
            )
            if state.game_won:
                show_message(
                    screen,
                    tr("game_over.win"),
                    22,
                    GREEN,
                    (screen_width // 2, screen_height // 2 - 26),
                )
            else:
                show_message(
                    screen,
                    tr("game_over.lose"),
                    22,
                    RED,
                    (screen_width // 2, screen_height // 2 - 26),
                )
                if state.game_over_message:
                    show_message(
                        screen,
                        state.game_over_message,
                        18,
                        LIGHT_GRAY,
                        (screen_width // 2, screen_height // 2 + 6),
                    )
            summary_y = screen_height // 2 + 70
            if stage and (stage.rescue_stage or stage.buddy_required_count > 0):
                total_rescued = state.survivors_rescued + state.buddy_rescued
                msg = tr("game_over.survivors_summary", count=total_rescued)
                show_message(
                    screen,
                    msg,
                    18,
                    LIGHT_GRAY,
                    (screen_width // 2, summary_y),
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
                msg = tr("game_over.endurance_duration", time=time_label)
                show_message(
                    screen,
                    msg,
                    18,
                    LIGHT_GRAY,
                    (screen_width // 2, summary_y),
                )

        show_message(
            screen,
            tr("game_over.prompt"),
            18,
            WHITE,
            (screen_width // 2, screen_height // 2 + 24),
        )
        _draw_status_bar(
            screen,
            render_assets,
            config,
            stage=stage,
            seed=state.seed,
            debug_mode=state.debug_mode,
        )

        present(screen)
        clock.tick(fps)

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                return ScreenTransition(ScreenID.EXIT)
            if event.type in (pygame.WINDOWSIZECHANGED, pygame.VIDEORESIZE):
                sync_window_size(event, game_data=game_data)
                continue
            if event.type == pygame.KEYDOWN:
                if event.key in (pygame.K_ESCAPE, pygame.K_SPACE):
                    return ScreenTransition(ScreenID.TITLE)
                if event.key == pygame.K_r and stage is not None:
                    return ScreenTransition(
                        ScreenID.GAMEPLAY,
                        stage=stage,
                        seed=state.seed,
                    )
            if event.type in (pygame.CONTROLLERBUTTONDOWN, pygame.JOYBUTTONDOWN):
                if is_select_event(event) or is_confirm_event(event):
                    return ScreenTransition(ScreenID.TITLE)
