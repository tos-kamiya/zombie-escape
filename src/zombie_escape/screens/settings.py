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
    ClickTarget,
    ClickableMap,
    CommonAction,
    InputHelper,
    MouseUiGuard,
)
from ..localization import (
    get_font_settings,
    get_language,
    get_language_name,
    language_options,
    set_language,
)
from ..localization import translate as tr
from ..progress import user_progress_path
from ..render import blit_text_wrapped, wrap_text
from ..screens import TITLE_HEADER_Y, TITLE_SECTION_TOP
from ..windowing import (
    adjust_menu_logical_size,
    nudge_menu_window_scale,
    present,
    sync_window_size,
    toggle_fullscreen,
)


class SettingsScreenRunner:
    def __init__(
        self,
        *,
        screen: surface.Surface,
        clock: time.Clock,
        config: dict[str, Any],
        fps: int,
        config_path: Path,
        screen_size: tuple[int, int],
    ) -> None:
        self.screen = screen
        self.clock = clock
        self.fps = fps
        self.config = config
        self.config_path = config_path
        self.screen_size = screen_size

        screen_width, screen_height = screen.get_size()
        if screen_width <= 0 or screen_height <= 0:
            screen_width, screen_height = screen_size
        self.screen_width = screen_width
        self.screen_height = screen_height

        self.working = copy.deepcopy(config)
        set_language(self.working.get("language"))
        self.selected = 0
        self.languages = language_options()
        self.language_codes = [lang.code for lang in self.languages]
        self.input_helper = InputHelper()
        self.mouse_ui_guard = MouseUiGuard()
        self.row_click_map = ClickableMap()

        self.sections, self.rows, self.row_sections = self._rebuild_rows()
        self.row_count = len(self.rows)
        self.last_language = get_language()
        pygame.mouse.set_visible(True)

        self.row_hitboxes: list[pygame.Rect] = [
            pygame.Rect(0, 0, 0, 0) for _ in range(self.row_count)
        ]
        self.left_toggle_hitboxes: list[pygame.Rect | None] = [
            None for _ in range(self.row_count)
        ]
        self.right_toggle_hitboxes: list[pygame.Rect | None] = [
            None for _ in range(self.row_count)
        ]

    def run(self) -> dict[str, Any]:
        while True:
            events = pygame.event.get()
            for event in events:
                transition = self._handle_event(event, events)
                if transition is not None:
                    return transition

            snapshot = self.input_helper.snapshot(events, pygame.key.get_pressed())
            transition = self._handle_snapshot(snapshot)
            if transition is not None:
                return transition

            self._render_frame()
            present(self.screen)
            self.clock.tick(self.fps)
            self.mouse_ui_guard.end_frame()

    def _ensure_parent(self, path: tuple[str, ...]) -> tuple[dict[str, Any], str]:
        node = self.working
        for key in path[:-1]:
            node = node.setdefault(key, {})
        return node, path[-1]

    def _get_value(self, path: tuple[str, ...], default: Any) -> Any:
        node: Any = self.working
        for key in path[:-1]:
            next_node = node.get(key) if isinstance(node, dict) else None
            if not isinstance(next_node, dict):
                return default
            node = next_node
        if isinstance(node, dict):
            return node.get(path[-1], default)
        return default

    def _set_value(self, path: tuple[str, ...], value: Any) -> None:
        node, leaf = self._ensure_parent(path)
        node[leaf] = value

    def _toggle_row(self, row: dict[str, Any]) -> None:
        current = bool(self._get_value(row["path"], row.get("easy_value", True)))
        self._set_value(row["path"], not current)

    def _set_easy_value(self, row: dict[str, Any], use_easy: bool) -> None:
        target = row.get("easy_value", True)
        self._set_value(row["path"], target if use_easy else not target)

    def _cycle_choice(self, row: dict[str, Any], direction: int) -> None:
        values = row.get("choices", [])
        if not values:
            return
        current = self._get_value(row["path"], values[0])
        try:
            idx = values.index(current)
        except ValueError:
            idx = 0
        idx = (idx + direction) % len(values)
        new_value = values[idx]
        self._set_value(row["path"], new_value)
        on_change = row.get("on_change")
        if on_change:
            on_change(new_value)

    def _build_sections(self) -> list[dict[str, Any]]:
        return [
            {
                "label": tr("settings.sections.menu"),
                "rows": [
                    {
                        "type": "action",
                        "label": tr("settings.rows.return_to_title"),
                        "action": "exit_settings",
                    },
                    {
                        "type": "action",
                        "label": tr("menu.fullscreen_toggle"),
                        "action": "toggle_fullscreen",
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
                        "choices": self.language_codes,
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

    def _rebuild_rows(self) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[str]]:
        current_sections = self._build_sections()
        flat_rows: list[dict[str, Any]] = []
        flat_sections: list[str] = []
        for section in current_sections:
            for row in section["rows"]:
                flat_rows.append(row)
                flat_sections.append(section["label"])
        return current_sections, flat_rows, flat_sections

    def _refresh_rows_if_language_changed(self) -> None:
        current_language = get_language()
        if current_language == self.last_language:
            return
        self.sections, self.rows, self.row_sections = self._rebuild_rows()
        self.row_count = len(self.rows)
        self.selected %= self.row_count
        self.last_language = current_language

    def _exit_settings(self) -> dict[str, Any]:
        save_config(self.working, self.config_path)
        return self.working

    def _activate_action(self, row: dict[str, Any]) -> dict[str, Any] | None:
        action = row.get("action", "exit_settings")
        if action == "toggle_fullscreen":
            toggle_fullscreen()
            adjust_menu_logical_size()
            return None
        return self._exit_settings()

    def _handle_event(
        self,
        event: pygame.event.Event,
        events: list[pygame.event.Event],
    ) -> dict[str, Any] | None:
        if event.type == pygame.QUIT:
            return self.config
        if event.type in (pygame.WINDOWSIZECHANGED, pygame.VIDEORESIZE):
            sync_window_size(event)
            adjust_menu_logical_size()
            return None
        if event.type == pygame.WINDOWFOCUSLOST:
            self.mouse_ui_guard.handle_focus_event(event)
            return None
        if event.type == pygame.WINDOWFOCUSGAINED:
            self.mouse_ui_guard.handle_focus_event(event)
            return None
        if event.type == pygame.MOUSEMOTION and self.mouse_ui_guard.can_process_mouse():
            hover_target = self.row_click_map.pick_hover(event.pos)
            if isinstance(hover_target, int):
                self.selected = hover_target
            return None
        if (
            event.type == pygame.MOUSEBUTTONUP
            and event.button == 1
            and self.mouse_ui_guard.can_process_mouse()
        ):
            clicked_target = self.row_click_map.pick_click(event.pos)
            if isinstance(clicked_target, int):
                self.selected = clicked_target
                current_row = self.rows[self.selected]
                row_type = current_row.get("type", "toggle")
                if row_type == "action":
                    return self._activate_action(current_row)
                if row_type == "toggle":
                    left_rect = self.left_toggle_hitboxes[self.selected]
                    right_rect = self.right_toggle_hitboxes[self.selected]
                    if left_rect and left_rect.collidepoint(event.pos):
                        self._set_easy_value(current_row, True)
                    elif right_rect and right_rect.collidepoint(event.pos):
                        self._set_easy_value(current_row, False)
                    else:
                        self._toggle_row(current_row)
                elif row_type == "choice":
                    row_rect = self.row_hitboxes[self.selected]
                    direction = -1 if event.pos[0] < row_rect.centerx else 1
                    self._cycle_choice(current_row, direction)
            return None

        self.input_helper.handle_device_event(event)
        if event.type == pygame.KEYDOWN:
            if event.key == pygame.K_LEFTBRACKET:
                nudge_menu_window_scale(0.5)
                return None
            if event.key == pygame.K_RIGHTBRACKET:
                nudge_menu_window_scale(2.0)
                return None
            if event.key == pygame.K_f:
                toggle_fullscreen()
                adjust_menu_logical_size()
                return None
            if event.key in (pygame.K_ESCAPE, pygame.K_BACKSPACE):
                return self._exit_settings()
            if event.key == pygame.K_r:
                self.working = copy.deepcopy(DEFAULT_CONFIG)
                set_language(self.working.get("language"))
                self.sections, self.rows, self.row_sections = self._rebuild_rows()
                self.row_count = len(self.rows)
                self.selected %= self.row_count
                self.last_language = get_language()
                return None
        return None

    def _handle_snapshot(self, snapshot: Any) -> dict[str, Any] | None:
        if snapshot.pressed(CommonAction.BACK):
            return self._exit_settings()
        if snapshot.pressed(CommonAction.UP):
            self.selected = (self.selected - 1) % self.row_count
        if snapshot.pressed(CommonAction.DOWN):
            self.selected = (self.selected + 1) % self.row_count

        current_row = self.rows[self.selected]
        row_type = current_row.get("type", "toggle")
        if snapshot.pressed(CommonAction.CONFIRM):
            if row_type == "action":
                return self._activate_action(current_row)
            if row_type == "toggle":
                self._toggle_row(current_row)
            elif row_type == "choice":
                self._cycle_choice(current_row, 1)
        if snapshot.pressed(CommonAction.LEFT) and row_type != "action":
            if row_type == "toggle":
                self._set_easy_value(current_row, True)
            elif row_type == "choice":
                self._cycle_choice(current_row, -1)
        if snapshot.pressed(CommonAction.RIGHT) and row_type != "action":
            if row_type == "toggle":
                self._set_easy_value(current_row, False)
            elif row_type == "choice":
                self._cycle_choice(current_row, 1)
        return None

    def _render_frame(self) -> None:
        self._refresh_rows_if_language_changed()
        self.row_hitboxes = [pygame.Rect(0, 0, 0, 0) for _ in range(self.row_count)]
        self.left_toggle_hitboxes = [None for _ in range(self.row_count)]
        self.right_toggle_hitboxes = [None for _ in range(self.row_count)]
        row_targets: list[ClickTarget] = []

        self.screen.fill(BLACK)
        try:
            font_settings = get_font_settings()
            highlight_color = (65, 65, 65)
            title_text = tr("settings.title")
            title_font = load_font(font_settings.resource, font_settings.scaled_size(33))
            title_lines = wrap_text(title_text, title_font, self.screen_width)
            title_line_height = int(
                round(title_font.get_linesize() * font_settings.line_height_scale)
            )
            title_height = max(1, len(title_lines)) * title_line_height
            title_width = max(
                (title_font.size(line)[0] for line in title_lines if line), default=0
            )
            title_topleft = (
                self.screen_width // 2 - title_width // 2,
                TITLE_HEADER_Y - title_height // 2,
            )
            blit_text_wrapped(
                self.screen,
                title_text,
                title_font,
                LIGHT_GRAY,
                title_topleft,
                self.screen_width,
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
            column_width = self.screen_width // 2 - column_margin * 2
            section_spacing = 4
            row_indent = 12
            value_padding = 20

            section_states: dict[str, dict[str, Any]] = {}
            y_cursor = start_y
            header_font = load_font(font_settings.resource, font_settings.scaled_size(11))
            for section in self.sections:
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
                    self.screen,
                    state["header_text"],
                    header_font,
                    LIGHT_GRAY,
                    state["header_pos"],
                    column_width,
                    line_height_scale=font_settings.line_height_scale,
                )

            label_font = load_font(font_settings.resource, font_settings.scaled_size(11))
            value_font = load_font(font_settings.resource, font_settings.scaled_size(11))
            for idx, row in enumerate(self.rows):
                section_label = self.row_sections[idx]
                state = section_states[section_label]
                col_x = column_margin + row_indent
                row_width = column_width - row_indent + value_padding
                row_type = row.get("type", "toggle")
                value = None
                if row_type != "action":
                    value = self._get_value(
                        row["path"],
                        row.get("easy_value", row.get("choices", [None])[0]),
                    )
                row_y_current = state["next_y"]
                state["next_y"] += row_height

                highlight_rect = pygame.Rect(
                    col_x, row_y_current - 2, row_width, row_height
                )
                self.row_hitboxes[idx] = highlight_rect.copy()
                row_targets.append(ClickTarget(idx, highlight_rect.copy()))
                if idx == self.selected:
                    pygame.draw.rect(self.screen, highlight_color, highlight_rect)

                label_height = int(
                    round(label_font.get_linesize() * font_settings.line_height_scale)
                )
                blit_text_wrapped(
                    self.screen,
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
                        self.screen,
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
                    self.left_toggle_hitboxes[idx] = left_rect.copy()
                    self.right_toggle_hitboxes[idx] = right_rect.copy()

                    left_active = value == row["easy_value"]
                    right_active = not left_active

                    self._draw_toggle_segment(
                        value_font=value_font,
                        font_settings=font_settings,
                        rect=left_rect,
                        text=row["left_label"],
                        active=left_active,
                    )
                    self._draw_toggle_segment(
                        value_font=value_font,
                        font_settings=font_settings,
                        rect=right_rect,
                        text=row["right_label"],
                        active=right_active,
                    )

            self._render_hints(font_settings=font_settings, start_y=start_y)
            self._render_paths(font_settings=font_settings)
        except pygame.error as e:
            print(f"Error rendering settings: {e}")

        self.row_click_map.set_targets(row_targets)

    def _draw_toggle_segment(
        self,
        *,
        value_font: pygame.font.Font,
        font_settings: Any,
        rect: pygame.Rect,
        text: str,
        active: bool,
    ) -> None:
        base_color = (35, 35, 35)
        active_color = (60, 90, 60) if active else base_color
        outline_color = GREEN if active else LIGHT_GRAY
        pygame.draw.rect(self.screen, active_color, rect)
        pygame.draw.rect(self.screen, outline_color, rect, width=2)
        text_width = value_font.size(text)[0]
        text_height = int(
            round(value_font.get_linesize() * font_settings.line_height_scale)
        )
        blit_text_wrapped(
            self.screen,
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

    def _render_hints(self, *, font_settings: Any, start_y: int) -> None:
        hint_start_x = self.screen_width // 2 + 16
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
        hint_max_width = self.screen_width - hint_start_x - 16
        y_cursor = start_y
        for line in hint_lines:
            blit_text_wrapped(
                self.screen,
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
            self.screen,
            window_hint,
            hint_font,
            WHITE,
            (hint_start_x, y_cursor),
            hint_max_width,
            line_height_scale=font_settings.line_height_scale,
        )
        _ = window_height  # keep local behavior equivalent

    def _render_paths(self, *, font_settings: Any) -> None:
        config_text = tr("settings.config_path", path=str(self.config_path))
        progress_text = tr("settings.progress_path", path=str(user_progress_path()))
        path_font = load_font(font_settings.resource, font_settings.scaled_size(11))
        line_height = int(
            round(path_font.get_linesize() * font_settings.line_height_scale)
        )
        pane_x = self.screen_width // 2 + 16
        pane_width = self.screen_width - pane_x - 16
        config_lines = wrap_text(config_text, path_font, pane_width)
        progress_lines = wrap_text(progress_text, path_font, pane_width)
        config_height = max(1, len(config_lines)) * line_height
        progress_height = max(1, len(progress_lines)) * line_height
        gap = max(4, line_height // 2)
        block_height = config_height + gap + progress_height
        block_top = self.screen_height - 16 - block_height

        blit_text_wrapped(
            self.screen,
            config_text,
            path_font,
            LIGHT_GRAY,
            (pane_x, block_top),
            pane_width,
            line_height_scale=font_settings.line_height_scale,
        )
        blit_text_wrapped(
            self.screen,
            progress_text,
            path_font,
            LIGHT_GRAY,
            (pane_x, block_top + config_height + gap),
            pane_width,
            line_height_scale=font_settings.line_height_scale,
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
    runner = SettingsScreenRunner(
        screen=screen,
        clock=clock,
        config=config,
        fps=fps,
        config_path=config_path,
        screen_size=screen_size,
    )
    return runner.run()
