from __future__ import annotations

import copy
from pathlib import Path
from typing import Any

import pygame
from pygame import surface, time

from ..colors import BLACK, GREEN, LIGHT_GRAY, WHITE
from ..config import DEFAULT_CONFIG, save_config
from ..font_utils import load_font
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
    is_select_event,
)
from ..localization import (
    get_font_settings,
    get_language,
    get_language_name,
    language_options,
    set_language,
)
from ..localization import (
    translate as tr,
)
from ..render import show_message
from ..progress import user_progress_path
from ..screens import (
    nudge_window_scale,
    present,
    sync_window_size,
    toggle_fullscreen,
)


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


def settings_screen(
    screen: surface.Surface,
    clock: time.Clock,
    config: dict[str, Any],
    fps: int,
    *,
    config_path: Path,
    screen_size: tuple[int, int],
) -> dict[str, Any]:
    """Settings menu shown from the title screen."""

    screen_width, screen_height = screen_size
    working = copy.deepcopy(config)
    set_language(working.get("language"))
    selected = 0
    languages = language_options()
    language_codes = [lang.code for lang in languages]
    controller = init_first_controller()
    joystick = init_first_joystick() if controller is None else None

    def _ensure_parent(path: tuple[str, ...]) -> tuple[dict, str]:
        node = working
        for key in path[:-1]:
            node = node.setdefault(key, {})
        return node, path[-1]

    def _get_value(path: tuple[str, ...], default: Any) -> Any:
        node = working
        for key in path[:-1]:
            next_node = node.get(key)
            if not isinstance(next_node, dict):
                return default
            node = next_node
        if isinstance(node, dict):
            return node.get(path[-1], default)
        return default

    def set_value(path: tuple[str, ...], value: Any) -> None:
        node, leaf = _ensure_parent(path)
        node[leaf] = value

    def toggle_row(row: dict) -> None:
        current = bool(_get_value(row["path"], row.get("easy_value", True)))
        set_value(row["path"], not current)

    def set_easy_value(row: dict, use_easy: bool) -> None:
        target = row.get("easy_value", True)
        set_value(row["path"], target if use_easy else not target)

    def cycle_choice(row: dict, direction: int) -> None:
        values = row.get("choices", [])
        if not values:
            return
        current = _get_value(row["path"], values[0])
        try:
            idx = values.index(current)
        except ValueError:
            idx = 0
        idx = (idx + direction) % len(values)
        new_value = values[idx]
        set_value(row["path"], new_value)
        on_change = row.get("on_change")
        if on_change:
            on_change(new_value)

    def build_sections() -> list[dict]:
        return [
            {
                "label": tr("settings.sections.menu"),
                "rows": [
                    {
                        "type": "action",
                        "label": tr("settings.rows.return_to_title"),
                    }
                ],
            },
            {
                "label": tr("settings.sections.localization"),
                "rows": [
                    {
                        "type": "choice",
                        "label": tr("settings.rows.language"),
                        "path": ("language",),
                        "choices": language_codes,
                        "get_display": get_language_name,
                        "on_change": set_language,
                    }
                ],
            },
            {
                "label": tr("settings.sections.player_support"),
                "rows": [
                    {
                        "label": tr("settings.rows.footprints"),
                        "path": ("footprints", "enabled"),
                        "easy_value": True,
                        "left_label": tr("common.on"),
                        "right_label": tr("common.off"),
                    },
                    {
                        "label": tr("settings.rows.car_hint"),
                        "path": ("car_hint", "enabled"),
                        "easy_value": True,
                        "left_label": tr("common.on"),
                        "right_label": tr("common.off"),
                    },
                ],
            },
            {
                "label": tr("settings.sections.tougher_enemies"),
                "rows": [
                    {
                        "label": tr("settings.rows.fast_zombies"),
                        "path": ("fast_zombies", "enabled"),
                        "easy_value": False,
                        "left_label": tr("common.off"),
                        "right_label": tr("common.on"),
                    },
                    {
                        "label": tr("settings.rows.steel_beams"),
                        "path": ("steel_beams", "enabled"),
                        "easy_value": False,
                        "left_label": tr("common.off"),
                        "right_label": tr("common.on"),
                    },
                ],
            },
        ]

    def rebuild_rows() -> tuple[list[dict], list[dict], list[str]]:
        current_sections = build_sections()
        flat_rows: list[dict] = []
        flat_sections: list[str] = []
        for section in current_sections:
            for row in section["rows"]:
                flat_rows.append(row)
                flat_sections.append(section["label"])
        return current_sections, flat_rows, flat_sections

    sections, rows, row_sections = rebuild_rows()
    row_count = len(rows)
    last_language = get_language()

    def _exit_settings() -> dict[str, Any]:
        save_config(working, config_path)
        return working

    while True:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                return config
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
            if is_select_event(event):
                return _exit_settings()
            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_LEFTBRACKET:
                    nudge_window_scale(0.5)
                    continue
                if event.key == pygame.K_RIGHTBRACKET:
                    nudge_window_scale(2.0)
                    continue
                if event.key == pygame.K_f:
                    toggle_fullscreen()
                    continue
                if event.key in (pygame.K_ESCAPE, pygame.K_BACKSPACE):
                    return _exit_settings()
                if event.key in (pygame.K_UP, pygame.K_w):
                    selected = (selected - 1) % row_count
                if event.key in (pygame.K_DOWN, pygame.K_s):
                    selected = (selected + 1) % row_count
                current_row = rows[selected]
                row_type = current_row.get("type", "toggle")
                if event.key in (pygame.K_SPACE, pygame.K_RETURN):
                    if row_type == "action":
                        return _exit_settings()
                    if row_type == "toggle":
                        toggle_row(current_row)
                    elif row_type == "choice":
                        cycle_choice(current_row, 1)
                if event.key == pygame.K_LEFT and row_type != "action":
                    if row_type == "toggle":
                        set_easy_value(current_row, True)
                    elif row_type == "choice":
                        cycle_choice(current_row, -1)
                if event.key == pygame.K_RIGHT and row_type != "action":
                    if row_type == "toggle":
                        set_easy_value(current_row, False)
                    elif row_type == "choice":
                        cycle_choice(current_row, 1)
                if event.key == pygame.K_r:
                    working = copy.deepcopy(DEFAULT_CONFIG)
                    set_language(working.get("language"))
            if event.type == pygame.JOYBUTTONDOWN or (
                CONTROLLER_BUTTON_DOWN is not None
                and event.type == CONTROLLER_BUTTON_DOWN
            ):
                current_row = rows[selected]
                row_type = current_row.get("type", "toggle")
                if is_confirm_event(event):
                    if row_type == "action":
                        return _exit_settings()
                    if row_type == "toggle":
                        toggle_row(current_row)
                    elif row_type == "choice":
                        cycle_choice(current_row, 1)
                if CONTROLLER_BUTTON_DOWN is not None and event.type == CONTROLLER_BUTTON_DOWN:
                    if (
                        CONTROLLER_BUTTON_DPAD_UP is not None
                        and event.button == CONTROLLER_BUTTON_DPAD_UP
                    ):
                        selected = (selected - 1) % row_count
                    if (
                        CONTROLLER_BUTTON_DPAD_DOWN is not None
                        and event.button == CONTROLLER_BUTTON_DPAD_DOWN
                    ):
                        selected = (selected + 1) % row_count
                    if (
                        CONTROLLER_BUTTON_DPAD_LEFT is not None
                        and event.button == CONTROLLER_BUTTON_DPAD_LEFT
                        and row_type != "action"
                    ):
                        if row_type == "toggle":
                            set_easy_value(current_row, True)
                        elif row_type == "choice":
                            cycle_choice(current_row, -1)
                    if (
                        CONTROLLER_BUTTON_DPAD_RIGHT is not None
                        and event.button == CONTROLLER_BUTTON_DPAD_RIGHT
                        and row_type != "action"
                    ):
                        if row_type == "toggle":
                            set_easy_value(current_row, False)
                        elif row_type == "choice":
                            cycle_choice(current_row, 1)
            if event.type == pygame.JOYHATMOTION:
                current_row = rows[selected]
                row_type = current_row.get("type", "toggle")
                hat_x, hat_y = event.value
                if hat_y == 1:
                    selected = (selected - 1) % row_count
                elif hat_y == -1:
                    selected = (selected + 1) % row_count
                if hat_x == -1 and row_type != "action":
                    if row_type == "toggle":
                        set_easy_value(current_row, True)
                    elif row_type == "choice":
                        cycle_choice(current_row, -1)
                elif hat_x == 1 and row_type != "action":
                    if row_type == "toggle":
                        set_easy_value(current_row, False)
                    elif row_type == "choice":
                        cycle_choice(current_row, 1)

        current_language = get_language()
        if current_language != last_language:
            sections, rows, row_sections = rebuild_rows()
            row_count = len(rows)
            selected %= row_count
            last_language = current_language

        screen.fill(BLACK)
        show_message(
            screen,
            tr("settings.title"),
            26,
            LIGHT_GRAY,
            (screen_width // 2, 20),
        )

        try:
            font_settings = get_font_settings()
            label_font = load_font(
                font_settings.resource, font_settings.scaled_size(12)
            )
            value_font = load_font(
                font_settings.resource, font_settings.scaled_size(12)
            )
            section_font = load_font(
                font_settings.resource, font_settings.scaled_size(13)
            )
            highlight_color = (70, 70, 70)

            row_height = 20
            start_y = 46

            segment_width = 30
            segment_height = 18
            segment_gap = 10
            segment_total_width = segment_width * 2 + segment_gap

            column_margin = 24
            column_width = screen_width // 2 - column_margin * 2
            section_spacing = 4
            row_indent = 12
            value_padding = 20

            section_states: dict[str, dict] = {}
            y_cursor = start_y
            for section in sections:
                header_surface = section_font.render(
                    section["label"], False, LIGHT_GRAY
                )
                section_states[section["label"]] = {
                    "next_y": y_cursor + header_surface.get_height() + 4,
                    "header_surface": header_surface,
                    "header_pos": (column_margin, y_cursor),
                }
                rows_in_section = len(section["rows"])
                y_cursor = (
                    section_states[section["label"]]["next_y"]
                    + rows_in_section * row_height
                    + section_spacing
                )

            for state in section_states.values():
                screen.blit(state["header_surface"], state["header_pos"])

            for idx, row in enumerate(rows):
                section_label = row_sections[idx]
                state = section_states[section_label]
                col_x = column_margin + row_indent
                row_width = column_width - row_indent + value_padding
                row_type = row.get("type", "toggle")
                value = None
                if row_type != "action":
                    value = _get_value(
                        row["path"],
                        row.get("easy_value", row.get("choices", [None])[0]),
                    )
                row_y_current = state["next_y"]
                state["next_y"] += row_height

                highlight_rect = pygame.Rect(
                    col_x, row_y_current - 2, row_width, row_height
                )
                if idx == selected:
                    pygame.draw.rect(screen, highlight_color, highlight_rect)

                label_surface = label_font.render(row["label"], False, WHITE)
                label_rect = label_surface.get_rect(
                    topleft=(
                        col_x,
                        row_y_current + (row_height - label_surface.get_height()) // 2,
                    )
                )
                screen.blit(label_surface, label_rect)
                if row_type == "choice":
                    display_fn = row.get("get_display")
                    display_text = (
                        display_fn(value)
                        if display_fn and value is not None
                        else str(value)
                    )
                    value_surface = value_font.render(display_text, False, WHITE)
                    value_rect = value_surface.get_rect(
                        midright=(
                            col_x + row_width,
                            row_y_current + row_height // 2,
                        )
                    )
                    screen.blit(value_surface, value_rect)
                elif row_type == "toggle":
                    slider_y = row_y_current + (row_height - segment_height) // 2 - 2
                    slider_x = col_x + row_width - segment_total_width
                    left_rect = pygame.Rect(
                        slider_x, slider_y, segment_width, segment_height
                    )
                    right_rect = pygame.Rect(
                        left_rect.right + segment_gap,
                        slider_y,
                        segment_width,
                        segment_height,
                    )

                    left_active = value == row["easy_value"]
                    right_active = not left_active

                    def draw_segment(
                        rect: pygame.Rect, text: str, active: bool
                    ) -> None:
                        base_color = (35, 35, 35)
                        active_color = (60, 90, 60) if active else base_color
                        outline_color = GREEN if active else LIGHT_GRAY
                        pygame.draw.rect(screen, active_color, rect)
                        pygame.draw.rect(screen, outline_color, rect, width=2)
                        text_surface = value_font.render(text, False, WHITE)
                        text_rect = text_surface.get_rect(center=rect.center)
                        screen.blit(text_surface, text_rect)

                    draw_segment(left_rect, row["left_label"], left_active)
                    draw_segment(right_rect, row["right_label"], right_active)

            hint_start_y = start_y
            hint_start_x = screen_width // 2 + 16
            hint_font = load_font(font_settings.resource, font_settings.scaled_size(11))
            hint_lines = [
                tr("settings.hints.navigate"),
                tr("settings.hints.adjust"),
                tr("settings.hints.toggle"),
                tr("settings.hints.reset"),
                tr("settings.hints.exit"),
            ]
            hint_line_height = hint_font.get_linesize()
            hint_max_width = screen_width - hint_start_x - 16
            y_cursor = hint_start_y
            for line in hint_lines:
                hint_surface = hint_font.render(line, False, WHITE)
                hint_rect = hint_surface.get_rect(topleft=(hint_start_x, y_cursor))
                screen.blit(hint_surface, hint_rect)
                y_cursor += hint_line_height

            y_cursor += 26
            window_hint = tr("menu.window_hint")
            for line in _wrap_text(window_hint, hint_font, hint_max_width):
                hint_surface = hint_font.render(line, False, WHITE)
                hint_rect = hint_surface.get_rect(topleft=(hint_start_x, y_cursor))
                screen.blit(hint_surface, hint_rect)
                y_cursor += hint_line_height

            path_font = load_font(font_settings.resource, font_settings.scaled_size(11))
            config_text = tr("settings.config_path", path=str(config_path))
            progress_text = tr(
                "settings.progress_path", path=str(user_progress_path())
            )
            line_height = path_font.get_linesize()
            config_surface = path_font.render(config_text, False, LIGHT_GRAY)
            progress_surface = path_font.render(progress_text, False, LIGHT_GRAY)
            config_rect = config_surface.get_rect(
                midtop=(screen_width // 2, screen_height - 32 - line_height)
            )
            progress_rect = progress_surface.get_rect(
                midtop=(screen_width // 2, screen_height - 32)
            )
            screen.blit(config_surface, config_rect)
            screen.blit(progress_surface, progress_rect)
        except pygame.error as e:
            print(f"Error rendering settings: {e}")

        present(screen)
        clock.tick(fps)
