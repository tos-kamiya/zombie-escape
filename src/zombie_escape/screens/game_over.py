from __future__ import annotations

from typing import Callable

import pygame
from pygame import surface, time

from ..colors import BLACK, GREEN, LIGHT_GRAY, RED, WHITE
from ..i18n import translate as _
from ..models import GameData, Stage
from ..render import RenderAssets, draw_level_overview, show_message
from ..screens import ScreenID, ScreenTransition



def game_over_screen(
    screen: surface.Surface,
    clock: time.Clock,
    payload: dict,
    *,
    render_assets: RenderAssets,
    fps: int,
    present_fn: Callable[[surface.Surface], None],
) -> ScreenTransition:
    """Display the game-over overview until the player chooses the next step."""

    game_data: GameData | None = payload.get("game_data") if payload else None
    stage: Stage | None = payload.get("stage") if payload else None
    config = payload.get("config") if payload else None

    if not game_data or config is None:
        return ScreenTransition(ScreenID.TITLE)

    screen_width = screen.get_width()
    screen_height = screen.get_height()
    state = game_data.state
    wall_group = game_data.groups.wall_group
    footprints_enabled = config.get("footprints", {}).get("enabled", True)

    while True:
        if not state.overview_created:
            level_rect = game_data.areas.outer_rect
            level_width = level_rect[2]
            level_height = level_rect[3]
            state.overview_surface = pygame.Surface((level_width, level_height))
            footprints_to_draw = state.footprints if footprints_enabled else []
            draw_level_overview(
                render_assets,
                state.overview_surface,
                wall_group,
                game_data.player,
                game_data.car,
                footprints_to_draw,
                fuel=game_data.fuel,
                flashlights=game_data.flashlights or [],
                stage=stage,
                companion=game_data.companion,
                survivors=list(game_data.groups.survivor_group),
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
                state.overview_surface, (scaled_w, scaled_h)
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
                    _("game_over.win"),
                    22,
                    GREEN,
                    (screen_width // 2, screen_height // 2 - 26),
                )
            else:
                show_message(
                    screen,
                    _("game_over.lose"),
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
            if stage and stage.survivor_stage:
                msg = _("game_over.survivors_summary", count=state.survivors_rescued)
                show_message(
                    screen,
                    msg,
                    18,
                    LIGHT_GRAY,
                    (screen_width // 2, screen_height // 2 + 70),
                )

        show_message(
            screen,
            _("game_over.prompt"),
            18,
            WHITE,
            (screen_width // 2, screen_height // 2 + 24),
        )

        present_fn(screen)
        clock.tick(fps)

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                return ScreenTransition(ScreenID.EXIT)
            if event.type == pygame.KEYDOWN:
                if event.key in (pygame.K_ESCAPE, pygame.K_SPACE):
                    return ScreenTransition(ScreenID.TITLE)
