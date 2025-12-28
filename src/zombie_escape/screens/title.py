from __future__ import annotations

from typing import Any, Sequence

import pygame
from pygame import surface, time

from ..colors import BLACK, GRAY, LIGHT_GRAY, WHITE, YELLOW
from ..font_utils import load_font
from ..localization import get_font_settings, translate as _
from ..models import Stage
from ..render import show_message
from ..screens import ScreenID, ScreenTransition, nudge_window_scale, present


def title_screen(
    screen: surface.Surface,
    clock: time.Clock,
    config: dict[str, Any],
    fps: int,
    *,
    stages: Sequence[Stage],
    default_stage_id: str,
    screen_size: tuple[int, int],
) -> ScreenTransition:
    """Display the title menu and return the selected transition."""

    width, height = screen_size
    options: list[dict] = [
        {"type": "stage", "stage": stage, "available": stage.available}
        for stage in stages
    ]
    options += [{"type": "settings"}, {"type": "quit"}]

    selected = next(
        (
            i
            for i, opt in enumerate(options)
            if opt["type"] == "stage" and opt["stage"].id == default_stage_id
        ),
        0,
    )

    while True:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                return ScreenTransition(ScreenID.EXIT)
            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_LEFTBRACKET:
                    nudge_window_scale(0.5)
                    continue
                if event.key == pygame.K_RIGHTBRACKET:
                    nudge_window_scale(2.0)
                    continue
                if event.key in (pygame.K_UP, pygame.K_w):
                    selected = (selected - 1) % len(options)
                elif event.key in (pygame.K_DOWN, pygame.K_s):
                    selected = (selected + 1) % len(options)
                elif event.key in (pygame.K_RETURN, pygame.K_SPACE):
                    current = options[selected]
                    if current["type"] == "stage" and current.get("available"):
                        return ScreenTransition(
                            ScreenID.GAMEPLAY, stage=current["stage"]
                        )
                    if current["type"] == "settings":
                        return ScreenTransition(ScreenID.SETTINGS)
                    if current["type"] == "quit":
                        return ScreenTransition(ScreenID.EXIT)

        screen.fill(BLACK)
        show_message(
            screen,
            _("game.title"),
            32,
            LIGHT_GRAY,
            (width // 2, 40),
        )

        try:
            font_settings = get_font_settings()
            font = load_font(font_settings.resource, font_settings.scaled_size(18))
            line_height = 22
            start_y = 80
            for idx, option in enumerate(options):
                if option["type"] == "stage":
                    label = option["stage"].name
                    if not option.get("available"):
                        locked_suffix = _("menu.locked_suffix")
                        label += f" {locked_suffix}"
                    color = (
                        YELLOW
                        if idx == selected
                        else (WHITE if option.get("available") else GRAY)
                    )
                elif option["type"] == "settings":
                    label = _("menu.settings")
                    color = YELLOW if idx == selected else WHITE
                else:
                    label = _("menu.quit")
                    color = YELLOW if idx == selected else WHITE

                text_surface = font.render(label, False, color)
                text_rect = text_surface.get_rect(
                    center=(width // 2, start_y + idx * line_height)
                )
                screen.blit(text_surface, text_rect)

            current = options[selected]
            if current["type"] == "stage":
                desc_font = load_font(
                    font_settings.resource, font_settings.scaled_size(11)
                )
                desc_color = LIGHT_GRAY if current.get("available") else GRAY
                desc_surface = desc_font.render(
                    current["stage"].description, False, desc_color
                )
                desc_rect = desc_surface.get_rect(center=(width // 2, height // 2 + 74))
                screen.blit(desc_surface, desc_rect)

            hint_font = load_font(font_settings.resource, font_settings.scaled_size(11))
            hint_text = _("menu.window_hint")
            hint_surface = hint_font.render(hint_text, False, LIGHT_GRAY)
            hint_rect = hint_surface.get_rect(center=(width // 2, height - 50))
            screen.blit(hint_surface, hint_rect)
        except pygame.error as e:
            print(f"Error rendering title screen: {e}")

        present(screen)
        clock.tick(fps)
