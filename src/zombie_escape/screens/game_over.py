from __future__ import annotations

from typing import Any

import pygame
from pygame import surface, time

from ..colors import BLACK, GREEN, LIGHT_GRAY, RED, WHITE
from ..gameplay_constants import SURVIVAL_FAKE_CLOCK_RATIO
from ..input_utils import (
    CommonAction,
    InputHelper,
)
from ..localization import translate as tr
from ..models import GameData, Stage
from ..render import (
    RenderAssets,
    _draw_status_bar,
    compute_floor_cells,
    draw_level_overview,
    blit_message,
)
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

    screen_width = screen.get_width()
    screen_height = screen.get_height()
    state = game_data.state
    wall_group = game_data.groups.wall_group
    footprints_enabled = config.get("footprints", {}).get("enabled", True)
    input_helper = InputHelper()

    while True:
        if not state.overview_created:
            level_rect = game_data.layout.field_rect
            level_width = level_rect.width
            level_height = level_rect.height
            overview_surface = pygame.Surface((level_width, level_height))
            cell_size = render_assets.internal_wall_grid_snap
            floor_cells: set[tuple[int, int]] = set()
            if cell_size > 0:
                floor_cells = compute_floor_cells(
                    cols=max(0, level_width // cell_size),
                    rows=max(0, level_height // cell_size),
                    wall_cells=game_data.layout.wall_cells,
                    outer_wall_cells=game_data.layout.outer_wall_cells,
                    pitfall_cells=game_data.layout.pitfall_cells,
                )
            footprints_to_draw = state.footprints if footprints_enabled else []
            draw_level_overview(
                render_assets,
                overview_surface,
                wall_group,
                floor_cells,
                game_data.player,
                game_data.car,
                game_data.waiting_cars,
                footprints_to_draw,
                now_ms=state.clock.elapsed_ms,
                fuel=game_data.fuel,
                empty_fuel_can=game_data.empty_fuel_can,
                fuel_station=game_data.fuel_station,
                flashlights=game_data.flashlights or [],
                shoes=game_data.shoes or [],
                buddies=[
                    survivor
                    for survivor in game_data.groups.survivor_group
                    if survivor.alive() and survivor.is_buddy and not survivor.rescued
                ],
                survivors=list(game_data.groups.survivor_group),
                patrol_bots=list(game_data.groups.patrol_bot_group),
                houseplants=list(game_data.houseplants.values()),
                zombies=list(game_data.groups.zombie_group),
                lineformer_trains=game_data.lineformer_trains,
                fall_spawn_cells=game_data.layout.fall_spawn_cells,
                moving_floor_cells=game_data.layout.moving_floor_cells,
                puddle_cells=game_data.layout.puddle_cells,
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
                blit_message(
                    screen,
                    tr("game_over.win"),
                    11,
                    GREEN,
                    (screen_width // 2, screen_height // 2 - 26),
                )
            else:
                blit_message(
                    screen,
                    tr("game_over.lose"),
                    11,
                    RED,
                    (screen_width // 2, screen_height // 2 - 26),
                )
            summary_y = screen_height // 2 + 70
            if stage and (
                stage.survivor_rescue_stage
                or stage.survivor_spawn_rate > 0.0
                or stage.buddy_required_count > 0
            ):
                total_rescued = state.survivors_rescued + state.buddy_rescued
                msg = tr("game_over.survivors_summary", count=total_rescued)
                blit_message(
                    screen,
                    msg,
                    11,
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
                blit_message(
                    screen,
                    msg,
                    11,
                    LIGHT_GRAY,
                    (screen_width // 2, summary_y),
                )

        blit_message(
            screen,
            tr("game_over.prompt"),
            11,
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

        events = pygame.event.get()
        for event in events:
            if event.type == pygame.QUIT:
                return ScreenTransition(ScreenID.EXIT)
            if event.type in (pygame.WINDOWSIZECHANGED, pygame.VIDEORESIZE):
                sync_window_size(event, game_data=game_data)
                continue
            input_helper.handle_device_event(event)
            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_LEFTBRACKET:
                    nudge_window_scale(0.5, game_data=game_data)
                    continue
                if event.key == pygame.K_RIGHTBRACKET:
                    nudge_window_scale(2.0, game_data=game_data)
                    continue
                if event.key == pygame.K_f:
                    toggle_fullscreen(game_data=game_data)
                    continue
                if event.key in (pygame.K_ESCAPE, pygame.K_SPACE):
                    return ScreenTransition(ScreenID.TITLE)
                if event.key == pygame.K_r and stage is not None:
                    return ScreenTransition(
                        ScreenID.GAMEPLAY,
                        stage=stage,
                        seed=state.seed,
                    )

        snapshot = input_helper.snapshot(events, pygame.key.get_pressed())
        if snapshot.pressed(CommonAction.START) and stage is not None:
            return ScreenTransition(
                ScreenID.GAMEPLAY,
                stage=stage,
                seed=state.seed,
            )
        if snapshot.pressed(CommonAction.BACK) or snapshot.pressed(CommonAction.CONFIRM):
            return ScreenTransition(ScreenID.TITLE)
