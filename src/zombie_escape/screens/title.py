from __future__ import annotations

import webbrowser
from typing import Any, Sequence

import pygame
from pygame import surface, time

from ..colors import BLACK, GRAY, LIGHT_GRAY, WHITE
from ..font_utils import load_font
from ..localization import get_font_settings, get_language
from ..localization import translate as tr
from ..models import Stage
from ..progress import load_progress
from ..render import show_message
from ..rng import generate_seed
from ..input_utils import (
    CONTROLLER_BUTTON_DOWN,
    CONTROLLER_BUTTON_DPAD_DOWN,
    CONTROLLER_BUTTON_DPAD_LEFT,
    CONTROLLER_BUTTON_DPAD_RIGHT,
    CONTROLLER_BUTTON_DPAD_UP,
    CONTROLLER_DEVICE_ADDED,
    CONTROLLER_DEVICE_REMOVED,
    init_first_controller,
    init_first_joystick,
    is_confirm_event,
)
from ..screens import (
    ScreenID,
    ScreenTransition,
    nudge_window_scale,
    present,
    sync_window_size,
    toggle_fullscreen,
)
try:  # pragma: no cover - version fallback not critical for tests
    from ..__about__ import __version__
except Exception:  # pragma: no cover - fallback version
    __version__ = "0.0.0-unknown"

MAX_SEED_DIGITS = 19
README_URLS: dict[str, str] = {
    "en": "https://github.com/tos-kamiya/zombie-escape/blob/main/README.md",
    "ja": "https://github.com/tos-kamiya/zombie-escape/blob/main/README-ja_JP.md",
}
UNCLEARED_STAGE_COLOR: tuple[int, int, int] = (220, 80, 80)


def _open_readme_link() -> None:
    """Open the GitHub README for the active UI language."""

    language = get_language()
    url = README_URLS.get(language, README_URLS["en"])
    try:
        webbrowser.open(url, new=0, autoraise=True)
    except Exception as exc:  # pragma: no cover - best effort only
        print(f"Unable to open README URL {url}: {exc}")


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


def _wrap_text(text: str, font: pygame.font.Font, max_width: int) -> list[str]:
    """Break text into multiple lines within a max width (supports CJK text)."""

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


def _blit_wrapped_text(
    target: surface.Surface,
    text: str,
    font: pygame.font.Font,
    color: tuple[int, int, int],
    topleft: tuple[int, int],
    max_width: int,
) -> None:
    """Render text with simple wrapping constrained to max_width."""

    x, y = topleft
    line_height = font.get_linesize()
    for line in _wrap_text(text, font, max_width):
        if not line:
            y += line_height
            continue
        rendered = font.render(line, False, color)
        target.blit(rendered, (x, y))
        y += line_height


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
    stage_options_all: list[dict] = [
        {"type": "stage", "stage": stage, "available": stage.available}
        for stage in stages
        if stage.available
    ]
    page_size = 5
    stage_pages = [
        stage_options_all[i : i + page_size]
        for i in range(0, len(stage_options_all), page_size)
    ]
    action_options: list[dict[str, Any]] = [
        {"type": "settings"},
        {"type": "readme"},
        {"type": "quit"},
    ]
    generated = seed_text is None
    current_seed_text = (
        seed_text if seed_text is not None else _generate_auto_seed_text()
    )
    current_seed_auto = seed_is_auto or generated
    stage_progress, _ = load_progress()

    def _page_available(page_index: int) -> bool:
        if page_index <= 0:
            return True
        required = stage_options_all[:page_size]
        return all(
            stage_progress.get(option["stage"].id, 0) > 0 for option in required
        )

    current_page = 0
    if stage_options_all:
        for idx, opt in enumerate(stage_options_all):
            if opt["stage"].id == default_stage_id:
                target_page = idx // page_size
                if _page_available(target_page):
                    current_page = target_page
                break

    def _build_options(page_index: int) -> tuple[list[dict], list[dict]]:
        page_index = max(0, min(page_index, len(stage_pages) - 1))
        stage_options = stage_pages[page_index] if stage_pages else []
        options = list(stage_options) + action_options
        return options, stage_options

    options, stage_options = _build_options(current_page)
    selected_stage_index = next(
        (
            i
            for i, opt in enumerate(options)
            if opt["type"] == "stage" and opt["stage"].id == default_stage_id
        ),
        0,
    )
    selected = min(selected_stage_index, len(options) - 1)
    controller = init_first_controller()
    joystick = init_first_joystick() if controller is None else None

    while True:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                return ScreenTransition(
                    ScreenID.EXIT,
                    seed_text=current_seed_text,
                    seed_is_auto=current_seed_auto,
                )
            if event.type in (pygame.WINDOWSIZECHANGED, pygame.VIDEORESIZE):
                sync_window_size(event)
                continue
            if event.type == pygame.JOYDEVICEADDED or (
                CONTROLLER_DEVICE_ADDED is not None
                and event.type == CONTROLLER_DEVICE_ADDED
            ):
                if controller is None:
                    controller = init_first_controller()
                if controller is None:
                    joystick = init_first_joystick()
            if event.type == pygame.JOYDEVICEREMOVED or (
                CONTROLLER_DEVICE_REMOVED is not None
                and event.type == CONTROLLER_DEVICE_REMOVED
            ):
                if controller and not controller.get_init():
                    controller = None
                if joystick and not joystick.get_init():
                    joystick = None
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
                if event.key == pygame.K_f:
                    toggle_fullscreen()
                    continue
                if event.key == pygame.K_LEFT:
                    if current_page > 0:
                        current_page -= 1
                        options, stage_options = _build_options(current_page)
                        selected = 0
                    continue
                if event.key == pygame.K_RIGHT:
                    if (
                        current_page < len(stage_pages) - 1
                        and _page_available(current_page + 1)
                    ):
                        current_page += 1
                        options, stage_options = _build_options(current_page)
                        selected = 0
                    continue
                if event.key in (pygame.K_UP, pygame.K_w):
                    selected = (selected - 1) % len(options)
                elif event.key in (pygame.K_DOWN, pygame.K_s):
                    selected = (selected + 1) % len(options)
                elif event.key in (pygame.K_RETURN, pygame.K_SPACE):
                    current = options[selected]
                    if current["type"] == "stage" and current.get("available"):
                        seed_value = (
                            int(current_seed_text) if current_seed_text else None
                        )
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
                    if current["type"] == "readme":
                        _open_readme_link()
                        continue
                    if current["type"] == "quit":
                        return ScreenTransition(
                            ScreenID.EXIT,
                            seed_text=current_seed_text,
                            seed_is_auto=current_seed_auto,
                        )
            if event.type == pygame.JOYBUTTONDOWN or (
                CONTROLLER_BUTTON_DOWN is not None
                and event.type == CONTROLLER_BUTTON_DOWN
            ):
                if is_confirm_event(event):
                    current = options[selected]
                    if current["type"] == "stage" and current.get("available"):
                        seed_value = (
                            int(current_seed_text) if current_seed_text else None
                        )
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
                    if current["type"] == "readme":
                        _open_readme_link()
                        continue
                    if current["type"] == "quit":
                        return ScreenTransition(
                            ScreenID.EXIT,
                            seed_text=current_seed_text,
                            seed_is_auto=current_seed_auto,
                        )
                if CONTROLLER_BUTTON_DOWN is not None and event.type == CONTROLLER_BUTTON_DOWN:
                    if (
                        CONTROLLER_BUTTON_DPAD_UP is not None
                        and event.button == CONTROLLER_BUTTON_DPAD_UP
                    ):
                        selected = (selected - 1) % len(options)
                    if (
                        CONTROLLER_BUTTON_DPAD_DOWN is not None
                        and event.button == CONTROLLER_BUTTON_DPAD_DOWN
                    ):
                        selected = (selected + 1) % len(options)
                    if (
                        CONTROLLER_BUTTON_DPAD_LEFT is not None
                        and event.button == CONTROLLER_BUTTON_DPAD_LEFT
                    ):
                        if current_page > 0:
                            current_page -= 1
                            options, stage_options = _build_options(current_page)
                            selected = 0
                    if (
                        CONTROLLER_BUTTON_DPAD_RIGHT is not None
                        and event.button == CONTROLLER_BUTTON_DPAD_RIGHT
                    ):
                        if (
                            current_page < len(stage_pages) - 1
                            and _page_available(current_page + 1)
                        ):
                            current_page += 1
                            options, stage_options = _build_options(current_page)
                            selected = 0
            if event.type == pygame.JOYHATMOTION:
                hat_x, hat_y = event.value
                if hat_y == 1:
                    selected = (selected - 1) % len(options)
                elif hat_y == -1:
                    selected = (selected + 1) % len(options)
                if hat_x == -1:
                    if current_page > 0:
                        current_page -= 1
                        options, stage_options = _build_options(current_page)
                        selected = 0
                elif hat_x == 1:
                    if (
                        current_page < len(stage_pages) - 1
                        and _page_available(current_page + 1)
                    ):
                        current_page += 1
                        options, stage_options = _build_options(current_page)
                        selected = 0

        screen.fill(BLACK)
        title_text = tr("game.title")
        show_message(screen, title_text, 32, LIGHT_GRAY, (width // 2, 40))

        try:
            font_settings = get_font_settings()
            title_font = load_font(
                font_settings.resource, font_settings.scaled_size(32)
            )
            option_font = load_font(
                font_settings.resource, font_settings.scaled_size(14)
            )
            desc_font = load_font(font_settings.resource, font_settings.scaled_size(11))
            section_font = load_font(
                font_settings.resource, font_settings.scaled_size(13)
            )
            hint_font = load_font(font_settings.resource, font_settings.scaled_size(11))

            row_height = 20
            list_column_x = 24
            list_column_width = width // 2 - 36
            info_column_x = width // 2 + 12
            info_column_width = width - info_column_x - 24
            section_top = 70
            highlight_color = (70, 70, 70)

            stage_count = len(stage_options)
            # resource_count = len(options) - stage_count

            stage_header_text = tr("menu.sections.stage_select")
            show_page_arrows = len(stage_pages) > 1 and _page_available(1)
            if show_page_arrows:
                left_arrow = "<- " if current_page > 0 else ""
                right_arrow = (
                    " ->"
                    if current_page < len(stage_pages) - 1
                    and _page_available(current_page + 1)
                    else ""
                )
                stage_header_text = f"{left_arrow}{stage_header_text}{right_arrow}"
            stage_header = section_font.render(stage_header_text, False, LIGHT_GRAY)
            stage_header_pos = (list_column_x, section_top)
            screen.blit(stage_header, stage_header_pos)
            stage_rows_start = stage_header_pos[1] + stage_header.get_height() + 6
            action_header = section_font.render(
                tr("menu.sections.resources"), False, LIGHT_GRAY
            )
            action_header_pos = (
                list_column_x,
                stage_rows_start + stage_count * row_height + 14,
            )
            screen.blit(action_header, action_header_pos)
            action_rows_start = action_header_pos[1] + action_header.get_height() + 6

            for idx, option in enumerate(stage_options):
                row_top = stage_rows_start + idx * row_height
                highlight_rect = pygame.Rect(
                    list_column_x, row_top - 2, list_column_width, row_height
                )
                cleared = stage_progress.get(option["stage"].id, 0) > 0
                base_color = WHITE if cleared else UNCLEARED_STAGE_COLOR
                color = base_color
                if idx == selected:
                    pygame.draw.rect(screen, highlight_color, highlight_rect)
                label = option["stage"].name
                if not option.get("available"):
                    locked_suffix = tr("menu.locked_suffix")
                    label = f"{label} {locked_suffix}"
                    color = GRAY
                text_surface = option_font.render(label, False, color)
                text_rect = text_surface.get_rect(
                    topleft=(
                        list_column_x + 8,
                        row_top + (row_height - text_surface.get_height()) // 2,
                    )
                )
                screen.blit(text_surface, text_rect)

            for idx, option in enumerate(action_options):
                option_idx = stage_count + idx
                row_top = action_rows_start + idx * row_height
                highlight_rect = pygame.Rect(
                    list_column_x, row_top - 2, list_column_width, row_height
                )
                is_selected = option_idx == selected
                if is_selected:
                    pygame.draw.rect(screen, highlight_color, highlight_rect)
                if option["type"] == "settings":
                    label = tr("menu.settings")
                elif option["type"] == "readme":
                    label = f"> {tr('menu.readme')}"
                else:
                    label = tr("menu.quit")
                color = WHITE
                text_surface = option_font.render(label, False, color)
                text_rect = text_surface.get_rect(
                    topleft=(
                        list_column_x + 8,
                        row_top + (row_height - text_surface.get_height()) // 2,
                    )
                )
                screen.blit(text_surface, text_rect)

            current = options[selected]
            desc_area_top = section_top
            if current["type"] == "stage":
                desc_color = WHITE if current.get("available") else GRAY
                _blit_wrapped_text(
                    screen,
                    current["stage"].description,
                    desc_font,
                    desc_color,
                    (info_column_x, desc_area_top),
                    info_column_width,
                )

            option_help_top = desc_area_top
            help_text = ""
            if current["type"] == "settings":
                help_text = tr("menu.option_help.settings")
            elif current["type"] == "quit":
                help_text = tr("menu.option_help.quit")
            elif current["type"] == "readme":
                help_text = tr("menu.option_help.readme")

            if help_text:
                _blit_wrapped_text(
                    screen,
                    help_text,
                    desc_font,
                    WHITE,
                    (info_column_x, option_help_top),
                    info_column_width,
                )

            hint_lines = [tr("menu.hints.navigate")]
            if len(stage_pages) > 1 and _page_available(1):
                hint_lines.append(tr("menu.hints.page_switch"))
            hint_lines.append(tr("menu.hints.confirm"))
            hint_line_height = hint_font.get_linesize()
            # hint_block_height = len(hint_lines) * hint_line_height
            hint_start_y = action_header_pos[1]
            for offset, line in enumerate(hint_lines):
                hint_surface = hint_font.render(line, False, WHITE)
                hint_rect = hint_surface.get_rect(
                    topleft=(info_column_x, hint_start_y + offset * hint_line_height)
                )
                screen.blit(hint_surface, hint_rect)

            seed_value_display = (
                current_seed_text if current_seed_text else tr("menu.seed_empty")
            )
            seed_label = tr("menu.seed_label", value=seed_value_display)
            seed_surface = hint_font.render(seed_label, False, LIGHT_GRAY)
            seed_offset_y = hint_line_height
            seed_rect = seed_surface.get_rect(
                bottomleft=(info_column_x, height - 30 + seed_offset_y)
            )
            screen.blit(seed_surface, seed_rect)

            seed_hint = tr("menu.seed_hint")
            seed_hint_lines = _wrap_text(seed_hint, hint_font, info_column_width)
            seed_hint_height = len(seed_hint_lines) * hint_line_height
            seed_hint_top = seed_rect.top - 4 - seed_hint_height
            _blit_wrapped_text(
                screen,
                seed_hint,
                hint_font,
                LIGHT_GRAY,
                (info_column_x, seed_hint_top),
                info_column_width,
            )

            title_surface = title_font.render(title_text, False, LIGHT_GRAY)
            title_rect = title_surface.get_rect(center=(width // 2, 40))
            version_font = load_font(
                font_settings.resource, font_settings.scaled_size(15)
            )
            version_surface = version_font.render(f"v{__version__}", False, LIGHT_GRAY)
            version_rect = version_surface.get_rect(
                topleft=(title_rect.right + 4, title_rect.bottom - 4)
            )
            screen.blit(version_surface, version_rect)

        except pygame.error as e:
            print(f"Error rendering title screen: {e}")

        present(screen)
        clock.tick(fps)
