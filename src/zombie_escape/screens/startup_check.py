from __future__ import annotations

from typing import Any, Sequence

import pygame
from pygame import surface, time

from ..colors import BLACK, LIGHT_GRAY, WHITE
from ..font_utils import load_font
from ..localization import get_font_settings
from ..localization import translate as tr
from ..level_constants import DEFAULT_CELL_SIZE
from ..models import Stage
from ..render_constants import build_render_assets
from ..render.fog import load_shared_fog_cache_from_files
from ..input_utils import (
    InputHelper,
)
from ..render import blit_text_wrapped, wrap_text
from ..windowing import adjust_menu_logical_size, present, sync_window_size
from ..screens import ScreenID, ScreenTransition


def _measure_text_block(
    text: str,
    font: pygame.font.Font,
    max_width: int,
    *,
    line_height_scale: float,
) -> tuple[int, int, int]:
    lines = wrap_text(text, font, max_width)
    line_height = int(round(font.get_linesize() * line_height_scale))
    height = max(1, len(lines)) * line_height
    width = max((font.size(line)[0] for line in lines if line), default=0)
    return width, height, line_height


def startup_check_screen(
    screen: surface.Surface,
    clock: time.Clock,
    _config: dict[str, Any],
    fps: int,
    *,
    screen_size: tuple[int, int],
    stages: Sequence[Stage],
) -> ScreenTransition:
    """Gate entry to title screen if confirm is held on startup."""
    width, height = screen.get_size()
    if width <= 0 or height <= 0:
        width, height = screen_size

    input_helper = InputHelper()
    pygame.event.pump()

    unique_cell_sizes = sorted({int(stage.cell_size) for stage in stages if stage.available})
    if not unique_cell_sizes:
        unique_cell_sizes = [DEFAULT_CELL_SIZE]
    fog_cache_error: str | None = None
    for cell_size in unique_cell_sizes:
        assets = build_render_assets(cell_size)
        if load_shared_fog_cache_from_files(assets) is None:
            fog_cache_error = (
                "Fog cache load failed. "
                "Run --build-fog-cache-dark0 and restart."
            )
            break

    if fog_cache_error is not None:
        while True:
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    return ScreenTransition(ScreenID.EXIT)
                if event.type in (pygame.WINDOWSIZECHANGED, pygame.VIDEORESIZE):
                    sync_window_size(event)
                    adjust_menu_logical_size()
                    width, height = screen.get_size()

            screen.fill(BLACK)
            try:
                font_settings = get_font_settings()
                message_font = load_font(
                    font_settings.resource, font_settings.scaled_size(20)
                )
                sub_font = load_font(
                    font_settings.resource, font_settings.scaled_size(11)
                )
                max_width = max(1, width - 48)
                message = "Startup error"
                sub_message = fog_cache_error
                msg_width, msg_height, _ = _measure_text_block(
                    message,
                    message_font,
                    max_width,
                    line_height_scale=font_settings.line_height_scale,
                )
                _, sub_height, _ = _measure_text_block(
                    sub_message,
                    sub_font,
                    max_width,
                    line_height_scale=font_settings.line_height_scale,
                )
                total_height = msg_height + 8 + sub_height
                top = max(24, height // 2 - total_height // 2)
                left = max(24, width // 2 - msg_width // 2)
                blit_text_wrapped(
                    screen,
                    message,
                    message_font,
                    WHITE,
                    (left, top),
                    max_width,
                    line_height_scale=font_settings.line_height_scale,
                )
                blit_text_wrapped(
                    screen,
                    sub_message,
                    sub_font,
                    LIGHT_GRAY,
                    (24, top + msg_height + 8),
                    max_width,
                    line_height_scale=font_settings.line_height_scale,
                )
            except pygame.error as exc:
                print(f"Error rendering startup check screen: {exc}")
            present(screen)
            clock.tick(fps)

    if not input_helper.is_confirm_held():
        return ScreenTransition(ScreenID.TITLE)

    release_at: int | None = None
    release_delay_ms = 800

    while True:
        now = pygame.time.get_ticks()
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                return ScreenTransition(ScreenID.EXIT)
            if event.type in (pygame.WINDOWSIZECHANGED, pygame.VIDEORESIZE):
                sync_window_size(event)
                adjust_menu_logical_size()
                width, height = screen.get_size()
                continue
            input_helper.handle_device_event(event)

        pygame.event.pump()
        if not input_helper.is_confirm_held():
            if release_at is None:
                release_at = now
            elif now - release_at >= release_delay_ms:
                return ScreenTransition(ScreenID.TITLE)
        else:
            release_at = None

        screen.fill(BLACK)
        try:
            font_settings = get_font_settings()

            message = tr("menu.startup.release_confirm")
            sub_message = tr("menu.startup.waiting")
            message_font = load_font(
                font_settings.resource, font_settings.scaled_size(20)
            )
            sub_font = load_font(font_settings.resource, font_settings.scaled_size(11))
            max_width = max(1, width - 48)
            msg_width, msg_height, _ = _measure_text_block(
                message,
                message_font,
                max_width,
                line_height_scale=font_settings.line_height_scale,
            )
            sub_width, sub_height, _ = _measure_text_block(
                sub_message,
                sub_font,
                max_width,
                line_height_scale=font_settings.line_height_scale,
            )
            total_height = msg_height + 8 + sub_height
            top = max(24, height // 2 - total_height // 2)
            left = max(24, width // 2 - msg_width // 2)
            blit_text_wrapped(
                screen,
                message,
                message_font,
                WHITE,
                (left, top),
                max_width,
                line_height_scale=font_settings.line_height_scale,
            )
            sub_left = max(24, width // 2 - sub_width // 2)
            blit_text_wrapped(
                screen,
                sub_message,
                sub_font,
                LIGHT_GRAY,
                (sub_left, top + msg_height + 8),
                max_width,
                line_height_scale=font_settings.line_height_scale,
            )
        except pygame.error as exc:
            print(f"Error rendering startup check screen: {exc}")

        present(screen)
        clock.tick(fps)
