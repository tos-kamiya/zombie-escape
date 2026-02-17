from __future__ import annotations

import pygame
from pygame import surface

from ..colors import LIGHT_GRAY, WHITE
from ..font_utils import load_font, render_text_surface
from ..localization import get_font_settings
from ..localization import translate as tr
from ..render_constants import GAMEPLAY_FONT_SIZE


def _wrap_long_segment(
    segment: str, font: pygame.font.Font, max_width: int
) -> list[str]:
    lines: list[str] = []
    current = ""
    for char in segment:
        candidate = current + char
        if font.size(candidate)[0] <= max_width or not current:
            current = candidate
        else:
            lines.append(current)
            current = char
    if current:
        lines.append(current)
    return lines


def wrap_text(text: str, font: pygame.font.Font, max_width: int) -> list[str]:
    if max_width <= 0:
        return [text]
    paragraphs = text.splitlines() or [text]
    lines: list[str] = []
    for paragraph in paragraphs:
        if not paragraph:
            lines.append("")
            continue
        words = paragraph.split(" ")
        if len(words) == 1:
            lines.extend(_wrap_long_segment(paragraph, font, max_width))
            continue
        current = ""
        for word in words:
            candidate = f"{current} {word}".strip() if current else word
            if font.size(candidate)[0] <= max_width:
                current = candidate
                continue
            if current:
                lines.append(current)
            if font.size(word)[0] <= max_width:
                current = word
            else:
                lines.extend(_wrap_long_segment(word, font, max_width))
                current = ""
        if current:
            lines.append(current)
    return lines


def blit_text_wrapped(
    target: surface.Surface,
    text: str,
    font: pygame.font.Font,
    color: tuple[int, int, int],
    topleft: tuple[int, int],
    max_width: int,
    *,
    line_height_scale: float = 1.0,
) -> None:
    """Render text with simple wrapping constrained to max_width."""

    x, y = topleft
    line_height = int(round(font.get_linesize() * line_height_scale))
    for line in wrap_text(text, font, max_width):
        if not line:
            y += line_height
            continue
        rendered = render_text_surface(
            font, line, color, line_height_scale=line_height_scale
        )
        target.blit(rendered, (x, y))
        y += line_height


def blit_message(
    screen: surface.Surface,
    text: str,
    size: int,
    color: tuple[int, int, int],
    position: tuple[int, int],
) -> None:
    try:
        font_settings = get_font_settings()
        scaled_size = font_settings.scaled_size(size)
        font = load_font(font_settings.resource, scaled_size)
        text_surface = render_text_surface(
            font, text, color, line_height_scale=font_settings.line_height_scale
        )
        text_rect = text_surface.get_rect(center=position)

        # Add a semi-transparent background rectangle for better visibility
        bg_padding = 15
        bg_rect = text_rect.inflate(bg_padding * 2, bg_padding * 2)
        bg_surface = pygame.Surface((bg_rect.width, bg_rect.height), pygame.SRCALPHA)
        bg_surface.fill((0, 0, 0, 180))
        screen.blit(bg_surface, bg_rect.topleft)

        screen.blit(text_surface, text_rect)
    except pygame.error as e:
        print(f"Error rendering font or surface: {e}")


def blit_message_wrapped(
    screen: surface.Surface,
    text: str,
    size: int,
    color: tuple[int, int, int],
    position: tuple[int, int],
    *,
    max_width: int,
    line_spacing: int = 2,
) -> None:
    try:
        font_settings = get_font_settings()
        font = load_font(font_settings.resource, font_settings.scaled_size(size))
        line_height_scale = font_settings.line_height_scale
        lines = wrap_text(text, font, max_width)
        if not lines:
            return
        rendered = [
            render_text_surface(
                font, line, color, line_height_scale=line_height_scale
            )
            for line in lines
        ]
        max_line_width = max(text_surface.get_width() for text_surface in rendered)
        line_height = int(round(font.get_linesize() * line_height_scale))
        total_height = line_height * len(rendered) + line_spacing * (len(rendered) - 1)

        center_x, center_y = position
        top = center_y - total_height // 2

        bg_padding = 15
        bg_width = max_line_width + bg_padding * 2
        bg_height = total_height + bg_padding * 2
        bg_rect = pygame.Rect(0, 0, bg_width, bg_height)
        bg_rect.center = (center_x, center_y)
        bg_surface = pygame.Surface((bg_rect.width, bg_rect.height), pygame.SRCALPHA)
        bg_surface.fill((0, 0, 0, 180))
        screen.blit(bg_surface, bg_rect.topleft)

        y = top
        for text_surface in rendered:
            text_rect = text_surface.get_rect(centerx=center_x, y=y)
            screen.blit(text_surface, text_rect)
            y += line_height + line_spacing
    except pygame.error as e:
        print(f"Error rendering font or surface: {e}")


def draw_pause_overlay(
    screen: pygame.Surface,
    *,
    menu_labels: list[str] | None = None,
    selected_index: int = 0,
) -> list[pygame.Rect]:
    screen_width, screen_height = screen.get_size()
    overlay = pygame.Surface((screen_width, screen_height), pygame.SRCALPHA)
    overlay.fill((0, 0, 0, 150))
    pause_radius = 34
    cx = screen_width // 2
    cy = screen_height // 2 - 20
    pygame.draw.circle(
        overlay,
        LIGHT_GRAY,
        (cx, cy),
        pause_radius,
        width=3,
    )
    bar_width = 6
    bar_height = 22
    gap = 8
    pygame.draw.rect(
        overlay,
        LIGHT_GRAY,
        (cx - gap - bar_width, cy - bar_height // 2, bar_width, bar_height),
    )
    pygame.draw.rect(
        overlay,
        LIGHT_GRAY,
        (cx + gap, cy - bar_height // 2, bar_width, bar_height),
    )
    screen.blit(overlay, (0, 0))
    blit_message(
        screen,
        tr("hud.paused"),
        GAMEPLAY_FONT_SIZE,
        WHITE,
        (screen_width // 2, cy - pause_radius - 14),
    )
    option_rects: list[pygame.Rect] = []
    if menu_labels:
        font_settings = get_font_settings()
        menu_font = load_font(font_settings.resource, font_settings.scaled_size(11))
        line_height = int(
            round(menu_font.get_linesize() * font_settings.line_height_scale)
        )
        row_height = line_height + 6
        menu_width = max(140, int(screen_width * 0.34))
        menu_top = cy + pause_radius + 10
        highlight_color = (70, 70, 70)
        for idx, label in enumerate(menu_labels):
            rect = pygame.Rect(
                screen_width // 2 - menu_width // 2,
                menu_top + idx * row_height,
                menu_width,
                row_height,
            )
            if idx == selected_index:
                pygame.draw.rect(screen, highlight_color, rect)
            text_surface = render_text_surface(
                menu_font,
                label,
                WHITE,
                line_height_scale=font_settings.line_height_scale,
            )
            text_rect = text_surface.get_rect(center=rect.center)
            screen.blit(text_surface, text_rect)
            option_rects.append(rect)
    return option_rects
