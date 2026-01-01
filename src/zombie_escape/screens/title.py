from __future__ import annotations

from typing import Any, Sequence

import pygame
from pygame import surface, time

from ..colors import BLACK, GRAY, LIGHT_GRAY, WHITE, YELLOW
from ..font_utils import load_font
from ..localization import get_font_settings, translate as tr
from ..models import Stage
from ..render import show_message
from ..screens import ScreenID, ScreenTransition, nudge_window_scale, present
from ..rng import generate_seed

MAX_SEED_DIGITS = 19


def _generate_auto_seed_text() -> str:
    raw = generate_seed()
    trimmed = raw // 100  # drop lower 2 digits for stability
    return str(trimmed % 100000).zfill(5)


def title_screen(
    screen: surface.Surface,
    clock: time.Clock,
    config: dict[str, Any],
    fps: int,
    *,
    stages: Sequence[Stage],
    default_stage_id: str,
    screen_size: tuple[int, int],
    seed_text: str | None = None,
    seed_is_auto: bool = False,
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
    generated = seed_text is None
    current_seed_text = seed_text if seed_text is not None else _generate_auto_seed_text()
    current_seed_auto = seed_is_auto or generated

    while True:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                return ScreenTransition(
                    ScreenID.EXIT,
                    seed_text=current_seed_text,
                    seed_is_auto=current_seed_auto,
                )
            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_BACKSPACE:
                    current_seed_text = _generate_auto_seed_text()
                    current_seed_auto = True
                    continue
                if event.unicode and event.unicode.isdigit():
                    if current_seed_auto:
                        current_seed_text = ""
                        current_seed_auto = False
                    if len(current_seed_text) < MAX_SEED_DIGITS:
                        current_seed_text += event.unicode
                    continue
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
                        seed_value = int(current_seed_text) if current_seed_text else None
                        return ScreenTransition(
                            ScreenID.GAMEPLAY,
                            stage=current["stage"],
                            seed=seed_value,
                            seed_text=current_seed_text,
                            seed_is_auto=current_seed_auto,
                        )
                    if current["type"] == "settings":
                        return ScreenTransition(
                            ScreenID.SETTINGS,
                            seed_text=current_seed_text,
                            seed_is_auto=current_seed_auto,
                        )
                    if current["type"] == "quit":
                        return ScreenTransition(
                            ScreenID.EXIT,
                            seed_text=current_seed_text,
                            seed_is_auto=current_seed_auto,
                        )

        screen.fill(BLACK)
        show_message(
            screen,
            tr("game.title"),
            32,
            LIGHT_GRAY,
            (width // 2, 40),
        )

        try:
            font_settings = get_font_settings()
            font = load_font(font_settings.resource, font_settings.scaled_size(18))
            line_height = 18
            start_y = 84
            for idx, option in enumerate(options):
                if option["type"] == "stage":
                    label = option["stage"].name
                    if not option.get("available"):
                        locked_suffix = tr("menu.locked_suffix")
                        label += f" {locked_suffix}"
                    color = (
                        YELLOW
                        if idx == selected
                        else (WHITE if option.get("available") else GRAY)
                    )
                elif option["type"] == "settings":
                    label = tr("menu.settings")
                    color = YELLOW if idx == selected else WHITE
                else:
                    label = tr("menu.quit")
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

            seed_font = load_font(font_settings.resource, font_settings.scaled_size(12))
            seed_value_display = (
                current_seed_text if current_seed_text else tr("menu.seed_empty")
            )
            seed_label = tr("status.seed", value=seed_value_display)
            seed_surface = seed_font.render(seed_label, False, LIGHT_GRAY)
            seed_rect = seed_surface.get_rect(right=width - 14, bottom=height - 12)
            screen.blit(seed_surface, seed_rect)

            hint_font = load_font(font_settings.resource, font_settings.scaled_size(11))
            hint_text = tr("menu.window_hint")
            hint_surface = hint_font.render(hint_text, False, LIGHT_GRAY)
            hint_rect = hint_surface.get_rect(center=(width // 2, height - 60))
            screen.blit(hint_surface, hint_rect)

            seed_hint = tr("menu.seed_hint")
            seed_hint_surface = hint_font.render(seed_hint, False, GRAY)
            seed_hint_rect = seed_hint_surface.get_rect(left=14, bottom=height - 12)
            screen.blit(seed_hint_surface, seed_hint_rect)
        except pygame.error as e:
            print(f"Error rendering title screen: {e}")

        present(screen)
        clock.tick(fps)
