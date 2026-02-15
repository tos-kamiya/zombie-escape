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
    CommonAction,
    InputHelper,
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
from ..render import blit_text_wrapped, wrap_text
from ..progress import user_progress_path
from ..screens import TITLE_HEADER_Y, TITLE_SECTION_TOP
from ..windowing import (
    adjust_menu_logical_size,
    nudge_menu_window_scale,
    present,
    sync_window_size,
    toggle_fullscreen,
)


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

    screen_width, screen_height = screen.get_size()
    if screen_width <= 0 or screen_height <= 0:
        screen_width, screen_height = screen_size
    working = copy.deepcopy(config)
    set_language(working.get("language"))
    selected = 0
    languages = language_options()
    language_codes = [lang.code for lang in languages]
    input_helper = InputHelper()

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
            {
                "label": tr("settings.sections.visual"),
                "rows": [
                    {
                        "label": tr("settings.rows.shadows"),
                        "path": ("visual", "shadows", "enabled"),
                        "easy_value": True,
                        "left_label": tr("common.on"),
                        "right_label": tr("common.off"),
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
    pygame.mouse.set_visible(True)
    row_hitboxes: list[pygame.Rect] = [pygame.Rect(0, 0, 0, 0) for _ in range(row_count)]
    left_toggle_hitboxes: list[pygame.Rect | None] = [None for _ in range(row_count)]
    right_toggle_hitboxes: list[pygame.Rect | None] = [None for _ in range(row_count)]
    mouse_guard_frames = 0

    def _exit_settings() -> dict[str, Any]:
        save_config(working, config_path)
        return working

    def _render_frame() -> None:
        nonlocal last_language, sections, rows, row_sections, row_count, selected
        nonlocal row_hitboxes, left_toggle_hitboxes, right_toggle_hitboxes
        current_language = get_language()
        if current_language != last_language:
            sections, rows, row_sections = rebuild_rows()
            row_count = len(rows)
            selected %= row_count
            last_language = current_language
        row_hitboxes = [pygame.Rect(0, 0, 0, 0) for _ in range(row_count)]
        left_toggle_hitboxes = [None for _ in range(row_count)]
        right_toggle_hitboxes = [None for _ in range(row_count)]

        screen.fill(BLACK)
        try:
            font_settings = get_font_settings()
            highlight_color = (70, 70, 70)
            title_text = tr("settings.title")
            title_font = load_font(font_settings.resource, font_settings.scaled_size(33))
            title_lines = wrap_text(title_text, title_font, screen_width)
            title_line_height = int(
                round(title_font.get_linesize() * font_settings.line_height_scale)
            )
            title_height = max(1, len(title_lines)) * title_line_height
            title_width = max(
                (title_font.size(line)[0] for line in title_lines if line), default=0
            )
            title_topleft = (
                screen_width // 2 - title_width // 2,
                TITLE_HEADER_Y - title_height // 2,
            )
            blit_text_wrapped(
                screen,
                title_text,
                title_font,
                LIGHT_GRAY,
                title_topleft,
                screen_width,
                line_height_scale=font_settings.line_height_scale,
            )

            row_height = (
                int(
                    round(
                        load_font(
                            font_settings.resource, font_settings.scaled_size(11)
                        ).get_linesize()
                        * font_settings.line_height_scale
                    )
                )
                + 2
            )
            start_y = TITLE_SECTION_TOP

            segment_width = int(round(30 * 1.5 * 0.8))
            segment_height = int(round(18 * 0.8))
            segment_gap = 10
            segment_total_width = segment_width * 2 + segment_gap

            column_margin = 24
            column_width = screen_width // 2 - column_margin * 2
            section_spacing = 4
            row_indent = 12
            value_padding = 20

            section_states: dict[str, dict] = {}
            y_cursor = start_y
            header_font = load_font(font_settings.resource, font_settings.scaled_size(11))
            for section in sections:
                header_lines = wrap_text(section["label"], header_font, column_width)
                header_line_height = int(
                    round(header_font.get_linesize() * font_settings.line_height_scale)
                )
                header_height = max(1, len(header_lines)) * header_line_height
                section_states[section["label"]] = {
                    "next_y": y_cursor + header_height + 4,
                    "header_text": section["label"],
                    "header_pos": (column_margin, y_cursor),
                }
                rows_in_section = len(section["rows"])
                y_cursor = (
                    section_states[section["label"]]["next_y"]
                    + rows_in_section * row_height
                    + section_spacing
                )

            for state in section_states.values():
                blit_text_wrapped(
                    screen,
                    state["header_text"],
                    header_font,
                    LIGHT_GRAY,
                    state["header_pos"],
                    column_width,
                    line_height_scale=font_settings.line_height_scale,
                )

            label_font = load_font(font_settings.resource, font_settings.scaled_size(11))
            value_font = load_font(font_settings.resource, font_settings.scaled_size(11))
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
                row_hitboxes[idx] = highlight_rect.copy()
                if idx == selected:
                    pygame.draw.rect(screen, highlight_color, highlight_rect)

                label_height = int(
                    round(
                        label_font.get_linesize() * font_settings.line_height_scale
                    )
                )
                blit_text_wrapped(
                    screen,
                    row["label"],
                    label_font,
                    WHITE,
                    (
                        col_x,
                        row_y_current + (row_height - label_height) // 2,
                    ),
                    row_width,
                    line_height_scale=font_settings.line_height_scale,
                )
                if row_type == "choice":
                    display_fn = row.get("get_display")
                    display_text = (
                        display_fn(value)
                        if display_fn and value is not None
                        else str(value)
                    )
                    text_width = value_font.size(display_text)[0]
                    text_height = int(
                        round(
                            value_font.get_linesize() * font_settings.line_height_scale
                        )
                    )
                    blit_text_wrapped(
                        screen,
                        display_text,
                        value_font,
                        WHITE,
                        (
                            col_x + row_width - text_width,
                            row_y_current + (row_height - text_height) // 2,
                        ),
                        row_width,
                        line_height_scale=font_settings.line_height_scale,
                    )
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
                    left_toggle_hitboxes[idx] = left_rect.copy()
                    right_toggle_hitboxes[idx] = right_rect.copy()

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
                        text_width = value_font.size(text)[0]
                        text_height = int(
                            round(
                                value_font.get_linesize()
                                * font_settings.line_height_scale
                            )
                        )
                        blit_text_wrapped(
                            screen,
                            text,
                            value_font,
                            WHITE,
                            (
                                rect.centerx - text_width // 2,
                                rect.centery - text_height // 2,
                            ),
                            rect.width,
                            line_height_scale=font_settings.line_height_scale,
                        )

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
            hint_line_height = int(
                round(hint_font.get_linesize() * font_settings.line_height_scale)
            )
            hint_max_width = screen_width - hint_start_x - 16
            y_cursor = hint_start_y
            for line in hint_lines:
                blit_text_wrapped(
                    screen,
                    line,
                    hint_font,
                    WHITE,
                    (hint_start_x, y_cursor),
                    hint_max_width,
                    line_height_scale=font_settings.line_height_scale,
                )
                y_cursor += hint_line_height

            y_cursor += 26
            window_hint = tr("menu.window_hint")
            window_lines = wrap_text(window_hint, hint_font, hint_max_width)
            window_height = max(1, len(window_lines)) * hint_line_height
            blit_text_wrapped(
                screen,
                window_hint,
                hint_font,
                WHITE,
                (hint_start_x, y_cursor),
                hint_max_width,
                line_height_scale=font_settings.line_height_scale,
            )
            y_cursor += window_height

            config_text = tr("settings.config_path", path=str(config_path))
            progress_text = tr("settings.progress_path", path=str(user_progress_path()))
            path_font = load_font(font_settings.resource, font_settings.scaled_size(11))
            config_width = path_font.size(config_text)[0]
            config_height = int(
                round(path_font.get_linesize() * font_settings.line_height_scale)
            )
            progress_width = path_font.size(progress_text)[0]
            config_top = screen_height - 32 - config_height
            blit_text_wrapped(
                screen,
                config_text,
                path_font,
                LIGHT_GRAY,
                (screen_width // 2 - config_width // 2, config_top),
                screen_width,
                line_height_scale=font_settings.line_height_scale,
            )
            blit_text_wrapped(
                screen,
                progress_text,
                path_font,
                LIGHT_GRAY,
                (screen_width // 2 - progress_width // 2, screen_height - 32),
                screen_width,
                line_height_scale=font_settings.line_height_scale,
            )
        except pygame.error as e:
            print(f"Error rendering settings: {e}")

        present(screen)
        clock.tick(fps)

    while True:
        events = pygame.event.get()
        for event in events:
            if event.type == pygame.QUIT:
                return config
            if event.type in (pygame.WINDOWSIZECHANGED, pygame.VIDEORESIZE):
                sync_window_size(event)
                adjust_menu_logical_size()
                continue
            if event.type == pygame.WINDOWFOCUSLOST:
                continue
            if event.type == pygame.WINDOWFOCUSGAINED:
                mouse_guard_frames = 1
                continue
            if (
                event.type == pygame.MOUSEMOTION
                and pygame.mouse.get_focused()
                and mouse_guard_frames == 0
            ):
                for idx, rect in enumerate(row_hitboxes):
                    if rect.collidepoint(event.pos):
                        selected = idx
                        break
                continue
            if (
                event.type == pygame.MOUSEBUTTONUP
                and event.button == 1
                and pygame.mouse.get_focused()
                and mouse_guard_frames == 0
            ):
                clicked_index: int | None = None
                for idx, rect in enumerate(row_hitboxes):
                    if rect.collidepoint(event.pos):
                        clicked_index = idx
                        break
                if clicked_index is not None:
                    selected = clicked_index
                    current_row = rows[selected]
                    row_type = current_row.get("type", "toggle")
                    if row_type == "action":
                        return _exit_settings()
                    if row_type == "toggle":
                        left_rect = left_toggle_hitboxes[selected]
                        right_rect = right_toggle_hitboxes[selected]
                        if left_rect and left_rect.collidepoint(event.pos):
                            set_easy_value(current_row, True)
                        elif right_rect and right_rect.collidepoint(event.pos):
                            set_easy_value(current_row, False)
                        else:
                            toggle_row(current_row)
                    elif row_type == "choice":
                        row_rect = row_hitboxes[selected]
                        direction = -1 if event.pos[0] < row_rect.centerx else 1
                        cycle_choice(current_row, direction)
                continue
            input_helper.handle_device_event(event)
            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_LEFTBRACKET:
                    nudge_menu_window_scale(0.5)
                    continue
                if event.key == pygame.K_RIGHTBRACKET:
                    nudge_menu_window_scale(2.0)
                    continue
                if event.key == pygame.K_f:
                    toggle_fullscreen()
                    adjust_menu_logical_size()
                    continue
                if event.key in (pygame.K_ESCAPE, pygame.K_BACKSPACE):
                    return _exit_settings()
                if event.key == pygame.K_r:
                    working = copy.deepcopy(DEFAULT_CONFIG)
                    set_language(working.get("language"))

        snapshot = input_helper.snapshot(events, pygame.key.get_pressed())
        if snapshot.pressed(CommonAction.BACK):
            return _exit_settings()
        if snapshot.pressed(CommonAction.UP):
            selected = (selected - 1) % row_count
        if snapshot.pressed(CommonAction.DOWN):
            selected = (selected + 1) % row_count
        current_row = rows[selected]
        row_type = current_row.get("type", "toggle")
        if snapshot.pressed(CommonAction.CONFIRM):
            if row_type == "action":
                return _exit_settings()
            if row_type == "toggle":
                toggle_row(current_row)
            elif row_type == "choice":
                cycle_choice(current_row, 1)
        if snapshot.pressed(CommonAction.LEFT) and row_type != "action":
            if row_type == "toggle":
                set_easy_value(current_row, True)
            elif row_type == "choice":
                cycle_choice(current_row, -1)
        if snapshot.pressed(CommonAction.RIGHT) and row_type != "action":
            if row_type == "toggle":
                set_easy_value(current_row, False)
            elif row_type == "choice":
                cycle_choice(current_row, 1)

        _render_frame()
        present(screen)
        clock.tick(fps)
        if mouse_guard_frames > 0:
            mouse_guard_frames -= 1
