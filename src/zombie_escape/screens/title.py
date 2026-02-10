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
from ..render import blit_text_wrapped, wrap_text
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
    TITLE_HEADER_Y,
    TITLE_SECTION_TOP,
)
from ..windowing import (
    adjust_menu_logical_size,
    nudge_menu_window_scale,
    present,
    sync_window_size,
    toggle_fullscreen,
)

try:  # pragma: no cover - version fallback not critical for tests
    from ..__about__ import __version__
except Exception:  # pragma: no cover - fallback version
    __version__ = "0.0.0-unknown"

MAX_SEED_DIGITS = 19
_README_URLS: dict[str, str] = {
    "en": "https://github.com/tos-kamiya/zombie-escape/blob/main/README.md",
    "ja": "https://github.com/tos-kamiya/zombie-escape/blob/main/README-ja_JP.md",
}
_STAGE6_URLS: dict[str, str] = {
    "en": "https://github.com/tos-kamiya/zombie-escape/blob/main/docs/stages-6plus.md",
    "ja": "https://github.com/tos-kamiya/zombie-escape/blob/main/docs/stages-6plus-ja_JP.md",
}
_UNCLEARED_STAGE_COLOR: tuple[int, int, int] = (220, 80, 80)


def _open_readme_link(*, use_stage6: bool = False) -> None:
    """Open the GitHub README or Stage 6+ guide for the active UI language."""

    language = get_language()
    if use_stage6:
        url = _STAGE6_URLS.get(language, _STAGE6_URLS["en"])
    else:
        url = _README_URLS.get(language, _README_URLS["en"])
    try:
        webbrowser.open(url, new=0, autoraise=True)
    except Exception as exc:  # pragma: no cover - best effort only
        print(f"Unable to open README URL {url}: {exc}")


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

    width, height = screen.get_size()
    if width <= 0 or height <= 0:
        width, height = screen_size
    stage_options_all: list[dict] = [
        {"type": "stage", "stage": stage, "available": stage.available}
        for stage in stages
        if stage.available
    ]
    first_page_size = 5
    other_page_size = 10
    stage_pages: list[list[dict]] = []
    if stage_options_all:
        stage_pages.append(stage_options_all[:first_page_size])
        for i in range(first_page_size, len(stage_options_all), other_page_size):
            stage_pages.append(stage_options_all[i : i + other_page_size])
    resource_options: list[dict[str, Any]] = [
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
        required = stage_options_all[:first_page_size]
        return all(stage_progress.get(option["stage"].id, 0) > 0 for option in required)

    def _page_index_for_stage(stage_idx: int) -> int:
        if stage_idx < first_page_size:
            return 0
        return 1 + (stage_idx - first_page_size) // other_page_size

    current_page = 0
    if stage_options_all:
        for idx, opt in enumerate(stage_options_all):
            if opt["stage"].id == default_stage_id:
                target_page = _page_index_for_stage(idx)
                if _page_available(target_page):
                    current_page = target_page
                break

    def _build_options(page_index: int) -> tuple[list[dict], list[dict]]:
        page_index = max(0, min(page_index, len(stage_pages) - 1))
        stage_options = stage_pages[page_index] if stage_pages else []
        options = list(stage_options) + resource_options
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
    pygame.event.pump()
    # Drop any queued confirm events from startup/controller init glitches.
    confirm_event_types = [pygame.JOYBUTTONDOWN]
    if CONTROLLER_BUTTON_DOWN is not None:
        confirm_event_types.append(CONTROLLER_BUTTON_DOWN)
    pygame.event.clear(confirm_event_types)
    pygame.event.clear([pygame.KEYDOWN])
    confirm_armed_at = pygame.time.get_ticks() + 300

    def _render_frame() -> None:
        screen.fill(BLACK)
        try:
            font_settings = get_font_settings()

            def _get_font(size: int) -> pygame.font.Font:
                return load_font(font_settings.resource, size)

            def _measure_text(
                text: str, font: pygame.font.Font, max_width: int
            ) -> tuple[int, int, int]:
                lines = wrap_text(text, font, max_width)
                line_height = int(
                    round(font.get_linesize() * font_settings.line_height_scale)
                )
                height = max(1, len(lines)) * line_height
                width = max((font.size(line)[0] for line in lines if line), default=0)
                return width, height, line_height

            base_stage_size = font_settings.scaled_size(11)
            selected_stage_size = font_settings.scaled_size(22)
            line_height_scale = font_settings.line_height_scale
            base_row_height = (
                int(
                    round(_get_font(base_stage_size).get_linesize() * line_height_scale)
                )
                + 2
            )
            selected_row_height = (
                int(
                    round(
                        _get_font(selected_stage_size).get_linesize()
                        * line_height_scale
                    )
                )
                + 2
            )
            list_column_x = 24
            list_column_width = width // 2 - 36
            info_column_x = width // 2 + 12
            info_column_width = width - info_column_x - 24
            section_top = TITLE_SECTION_TOP
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
            section_size = font_settings.scaled_size(11)
            section_font = _get_font(section_size)
            header_width, header_height, _ = _measure_text(
                stage_header_text, section_font, list_column_width
            )
            blit_text_wrapped(
                screen,
                stage_header_text,
                section_font,
                LIGHT_GRAY,
                (list_column_x, section_top),
                list_column_width,
                line_height_scale=font_settings.line_height_scale,
            )
            stage_header_rect = pygame.Rect(
                list_column_x, section_top, max(header_width, 1), header_height
            )
            stage_rows_start = stage_header_rect.bottom + 6
            resource_row_height = base_row_height
            resource_offset = resource_row_height
            stage_row_heights = [
                (selected_row_height if idx == selected else base_row_height)
                for idx in range(stage_count)
            ]
            fixed_stage_block_height = (
                base_row_height * max(stage_count - 1, 0) + selected_row_height
            )
            action_header_pos = (
                list_column_x,
                stage_rows_start + fixed_stage_block_height + 14 + resource_offset,
            )
            action_header_text = tr("menu.sections.resources")
            action_width, action_height, _ = _measure_text(
                action_header_text, section_font, list_column_width
            )
            blit_text_wrapped(
                screen,
                action_header_text,
                section_font,
                LIGHT_GRAY,
                action_header_pos,
                list_column_width,
                line_height_scale=font_settings.line_height_scale,
            )
            action_header_rect = pygame.Rect(
                action_header_pos[0], action_header_pos[1], max(action_width, 1), action_height
            )
            action_rows_start = action_header_rect.bottom + 6

            row_top = stage_rows_start
            for idx, option in enumerate(stage_options):
                row_height = stage_row_heights[idx]
                highlight_rect = pygame.Rect(
                    list_column_x, row_top - 2, list_column_width, row_height
                )
                cleared = stage_progress.get(option["stage"].id, 0) > 0
                base_color = WHITE if cleared else _UNCLEARED_STAGE_COLOR
                color = base_color
                is_selected = idx == selected
                if is_selected:
                    pygame.draw.rect(screen, highlight_color, highlight_rect)
                label = option["stage"].name
                if not option.get("available"):
                    locked_suffix = tr("menu.locked_suffix")
                    label = f"{label} {locked_suffix}"
                    color = GRAY
                stage_option_size = (
                    selected_stage_size if is_selected else base_stage_size
                )
                stage_option_font = _get_font(stage_option_size)
                text_height = int(
                    round(
                        stage_option_font.get_linesize()
                        * font_settings.line_height_scale
                    )
                )
                blit_text_wrapped(
                    screen,
                    label,
                    stage_option_font,
                    color,
                    (
                        list_column_x + 8,
                        row_top + (row_height - text_height) // 2,
                    ),
                    10_000,
                    line_height_scale=font_settings.line_height_scale,
                )
                row_top += row_height

            resource_option_size = font_settings.scaled_size(11)
            resource_option_font = _get_font(resource_option_size)
            for idx, option in enumerate(resource_options):
                option_idx = stage_count + idx
                row_top = action_rows_start + idx * resource_row_height
                highlight_rect = pygame.Rect(
                    list_column_x, row_top - 2, list_column_width, resource_row_height
                )
                is_selected = option_idx == selected
                if is_selected:
                    pygame.draw.rect(screen, highlight_color, highlight_rect)
                if option["type"] == "settings":
                    label = tr("menu.settings")
                elif option["type"] == "readme":
                    label_key = (
                        "menu.readme_stage6" if current_page > 0 else "menu.readme"
                    )
                    label = f"> {tr(label_key)}"
                else:
                    label = tr("menu.quit")
                color = WHITE
                text_height = int(
                    round(
                        resource_option_font.get_linesize()
                        * font_settings.line_height_scale
                    )
                )
                blit_text_wrapped(
                    screen,
                    label,
                    resource_option_font,
                    color,
                    (
                        list_column_x + 8,
                        row_top + (resource_row_height - text_height) // 2,
                    ),
                    list_column_width - 12,
                    line_height_scale=font_settings.line_height_scale,
                )

            current = options[selected]
            desc_area_top = section_top
            if current["type"] == "stage":
                desc_size = font_settings.scaled_size(11)
                desc_font = _get_font(desc_size)
                desc_color = WHITE if current.get("available") else GRAY
                desc_lines = wrap_text(
                    current["stage"].description, desc_font, info_column_width
                )
                _, _, desc_line_height = _measure_text(
                    current["stage"].description, desc_font, info_column_width
                )
                desc_height = max(1, len(desc_lines)) * desc_line_height
                desc_panel_padding = 6
                desc_panel_rect = pygame.Rect(
                    info_column_x - desc_panel_padding,
                    desc_area_top - desc_panel_padding,
                    info_column_width + desc_panel_padding * 2,
                    desc_height + desc_panel_padding * 2,
                )
                desc_panel = pygame.Surface(
                    (desc_panel_rect.width, desc_panel_rect.height), pygame.SRCALPHA
                )
                desc_panel.fill((0, 0, 0, 140))
                screen.blit(desc_panel, desc_panel_rect.topleft)
                blit_text_wrapped(
                    screen,
                    current["stage"].description,
                    desc_font,
                    desc_color,
                    (info_column_x, desc_area_top),
                    info_column_width,
                    line_height_scale=font_settings.line_height_scale,
                )

            option_help_top = desc_area_top
            help_text = ""
            if current["type"] == "settings":
                help_text = tr("menu.option_help.settings")
            elif current["type"] == "quit":
                help_text = tr("menu.option_help.quit")
            elif current["type"] == "readme":
                help_key = (
                    "menu.option_help.readme_stage6"
                    if current_page > 0
                    else "menu.option_help.readme"
                )
                help_text = tr(help_key)

            if help_text:
                desc_size = font_settings.scaled_size(11)
                desc_font = _get_font(desc_size)
                blit_text_wrapped(
                    screen,
                    help_text,
                    desc_font,
                    WHITE,
                    (info_column_x, option_help_top),
                    info_column_width,
                    line_height_scale=font_settings.line_height_scale,
                )

            hint_size = font_settings.scaled_size(11)
            hint_font = _get_font(hint_size)
            hint_line_height = int(
                round(hint_font.get_linesize() * font_settings.line_height_scale)
            )
            hint_start_y = action_header_pos[1]
            hint_step = hint_line_height
            if current_page == 0:
                hint_lines = [tr("menu.hints.navigate")]
                if len(stage_pages) > 1 and _page_available(1):
                    hint_lines.append(tr("menu.hints.page_switch"))
                hint_lines.extend(tr("menu.hints.confirm").splitlines())
                for offset, line in enumerate(hint_lines):
                    blit_text_wrapped(
                        screen,
                        line,
                        hint_font,
                        WHITE,
                        (info_column_x, hint_start_y + offset * hint_step),
                        info_column_width,
                        line_height_scale=font_settings.line_height_scale,
                    )

            seed_value_display = (
                current_seed_text if current_seed_text else tr("menu.seed_empty")
            )
            seed_label = tr("menu.seed_label", value=seed_value_display)
            seed_offset_y = hint_step
            seed_width, seed_height, _ = _measure_text(
                seed_label, hint_font, info_column_width
            )
            seed_bottom = height - 30 + seed_offset_y
            blit_text_wrapped(
                screen,
                seed_label,
                hint_font,
                LIGHT_GRAY,
                (info_column_x, seed_bottom - seed_height),
                info_column_width,
                line_height_scale=font_settings.line_height_scale,
            )
            seed_rect = pygame.Rect(
                info_column_x, seed_bottom - seed_height, max(seed_width, 1), seed_height
            )

            if current_page == 0:
                seed_hint = tr("menu.seed_hint")
                seed_hint_lines = wrap_text(seed_hint, hint_font, info_column_width)
                seed_hint_height = len(seed_hint_lines) * hint_line_height
                seed_hint_top = seed_rect.top - 4 - seed_hint_height
                blit_text_wrapped(
                    screen,
                    seed_hint,
                    hint_font,
                    LIGHT_GRAY,
                    (info_column_x, seed_hint_top),
                    info_column_width,
                    line_height_scale=font_settings.line_height_scale,
                )

            title_text = tr("game.title")
            title_font = _get_font(font_settings.scaled_size(33))
            title_width, title_height, _ = _measure_text(
                title_text, title_font, width
            )
            title_topleft = (
                width // 2 - title_width // 2,
                TITLE_HEADER_Y - title_height // 2,
            )
            blit_text_wrapped(
                screen,
                title_text,
                title_font,
                LIGHT_GRAY,
                title_topleft,
                width,
                line_height_scale=font_settings.line_height_scale,
            )
            title_rect = pygame.Rect(
                title_topleft[0], title_topleft[1], max(title_width, 1), title_height
            )
            version_font = _get_font(font_settings.scaled_size(11))
            version_text = f"v{__version__}"
            version_width, version_height, _ = _measure_text(
                version_text, version_font, width
            )
            version_topleft = (
                title_rect.right + 4,
                title_rect.bottom - version_height,
            )
            blit_text_wrapped(
                screen,
                version_text,
                version_font,
                LIGHT_GRAY,
                version_topleft,
                width - version_topleft[0],
                line_height_scale=font_settings.line_height_scale,
            )

        except pygame.error as e:
            print(f"Error rendering title screen: {e}")

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
                adjust_menu_logical_size()
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
                    nudge_menu_window_scale(0.5)
                    continue
                if event.key == pygame.K_RIGHTBRACKET:
                    nudge_menu_window_scale(2.0)
                    continue
                if event.key == pygame.K_f:
                    toggle_fullscreen()
                    adjust_menu_logical_size()
                    continue
                if event.key == pygame.K_LEFT:
                    if current_page > 0:
                        current_page -= 1
                        options, stage_options = _build_options(current_page)
                        selected = 0
                    continue
                if event.key == pygame.K_RIGHT:
                    if current_page < len(stage_pages) - 1 and _page_available(
                        current_page + 1
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
                    if pygame.time.get_ticks() < confirm_armed_at:
                        continue
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
                        _open_readme_link(use_stage6=current_page > 0)
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
                    if pygame.time.get_ticks() < confirm_armed_at:
                        continue
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
                        _open_readme_link(use_stage6=current_page > 0)
                        continue
                    if current["type"] == "quit":
                        return ScreenTransition(
                            ScreenID.EXIT,
                            seed_text=current_seed_text,
                            seed_is_auto=current_seed_auto,
                        )
                if (
                    CONTROLLER_BUTTON_DOWN is not None
                    and event.type == CONTROLLER_BUTTON_DOWN
                ):
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
                        if current_page < len(stage_pages) - 1 and _page_available(
                            current_page + 1
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
                    if current_page < len(stage_pages) - 1 and _page_available(
                        current_page + 1
                    ):
                        current_page += 1
                        options, stage_options = _build_options(current_page)
                        selected = 0

        _render_frame()
        present(screen)
        clock.tick(fps)
