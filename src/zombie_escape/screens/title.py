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
from ..render_assets import (
    build_flashlight_surface,
    get_character_icon,
    get_tile_icon,
)
from ..rng import generate_seed
from ..input_utils import (
    ClickTarget,
    ClickableMap,
    CommonAction,
    InputHelper,
    KeyboardShortcut,
    MouseUiGuard,
    read_mouse_state,
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
_UNCLEARED_STAGE_COLOR: tuple[int, int, int] = (220, 80, 80)


def _stage_guide_url_for_page(*, page_index: int, language: str) -> str:
    start_stage = 6 + max(0, page_index - 1) * 10
    if language == "ja":
        return (
            "https://github.com/tos-kamiya/zombie-escape/blob/main/docs/"
            f"stages-{start_stage}plus-ja_JP.md"
        )
    return (
        "https://github.com/tos-kamiya/zombie-escape/blob/main/docs/"
        f"stages-{start_stage}plus.md"
    )


def _open_readme_link(*, page_index: int = 0) -> None:
    """Open the README (page 0) or a stage-page guide (pages 1+)."""

    language = get_language()
    if page_index > 0:
        url = _stage_guide_url_for_page(page_index=page_index, language=language)
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


class TitleScreenController:
    """Stateful title-screen controller to keep rendering/input logic cohesive."""

    def __init__(
        self,
        *,
        screen: surface.Surface,
        clock: time.Clock,
        config: dict[str, Any],
        fps: int,
        stages: Sequence[Stage],
        default_stage_id: str,
        screen_size: tuple[int, int],
        seed_text: str | None,
        seed_is_auto: bool,
    ) -> None:
        self.screen = screen
        self.clock = clock
        self.config = config
        self.fps = fps
        self.default_stage_id = default_stage_id

        width, height = screen.get_size()
        if width <= 0 or height <= 0:
            width, height = screen_size
        self.width = width
        self.height = height

        self.stage_options_all: list[dict[str, Any]] = [
            {"type": "stage", "stage": stage, "available": stage.available}
            for stage in stages
            if stage.available
        ]
        self.first_page_size = 5
        self.other_page_size = 10
        self.stage_pages: list[list[dict[str, Any]]] = []
        if self.stage_options_all:
            self.stage_pages.append(self.stage_options_all[: self.first_page_size])
            for i in range(
                self.first_page_size,
                len(self.stage_options_all),
                self.other_page_size,
            ):
                self.stage_pages.append(
                    self.stage_options_all[i : i + self.other_page_size]
                )
        self.resource_base_options: list[dict[str, Any]] = [
            {"type": "settings"},
            {"type": "readme"},
            {"type": "quit"},
        ]
        generated = seed_text is None
        self.current_seed_text = (
            seed_text if seed_text is not None else _generate_auto_seed_text()
        )
        self.current_seed_auto = seed_is_auto or generated
        self.stage_progress, _ = load_progress()

        self.icon_radius = 3
        self.icon_surfaces = self._build_icon_surfaces()

        self.current_page = 0
        if self.stage_options_all:
            for idx, opt in enumerate(self.stage_options_all):
                if opt["stage"].id == self.default_stage_id:
                    target_page = self._page_index_for_stage(idx)
                    if self._page_available(target_page):
                        self.current_page = target_page
                    break

        self.options, self.stage_options = self._build_options(self.current_page)
        selected_stage_index = next(
            (
                i
                for i, opt in enumerate(self.options)
                if opt["type"] == "stage" and opt["stage"].id == self.default_stage_id
            ),
            0,
        )
        self.selected = min(selected_stage_index, len(self.options) - 1)
        self.input_helper = InputHelper()
        self.option_click_map = ClickableMap()
        self.page_button_click_map = ClickableMap()
        self.mouse_ui_guard = MouseUiGuard()
        self.stage_pane_rect = pygame.Rect(0, 0, 0, 0)

        pygame.mouse.set_visible(True)
        pygame.event.pump()
        confirm_event_types = [pygame.JOYBUTTONDOWN]
        controller_button_down = getattr(pygame, "CONTROLLERBUTTONDOWN", None)
        if controller_button_down is not None:
            confirm_event_types.append(controller_button_down)
        pygame.event.clear(confirm_event_types)
        pygame.event.clear([pygame.KEYDOWN])
        self.confirm_armed_at = pygame.time.get_ticks() + 300

    def _create_lettered_zombie(self, letter: str) -> pygame.Surface:
        surf = get_character_icon("zombie", self.icon_radius).copy()
        if not letter:
            return surf
        w, h = surf.get_size()
        color = WHITE
        ox, oy = w - 5, h - 6
        if letter == "T":
            pygame.draw.line(surf, color, (ox, oy), (ox + 2, oy))
            pygame.draw.line(surf, color, (ox + 1, oy), (ox + 1, oy + 4))
        elif letter == "W":
            pygame.draw.line(surf, color, (ox, oy), (ox, oy + 4))
            pygame.draw.line(surf, color, (ox + 2, oy + 1), (ox + 2, oy + 4))
            pygame.draw.line(surf, color, (ox + 4, oy), (ox + 4, oy + 4))
            pygame.draw.line(surf, color, (ox, oy + 4), (ox + 4, oy + 4))
        elif letter == "L":
            pygame.draw.line(surf, color, (ox, oy), (ox, oy + 4))
            pygame.draw.line(surf, color, (ox, oy + 4), (ox + 2, oy + 4))
        elif letter == "S":
            pygame.draw.line(surf, color, (ox, oy), (ox + 2, oy))
            pygame.draw.line(surf, color, (ox, oy + 2), (ox + 2, oy + 2))
            pygame.draw.line(surf, color, (ox, oy + 4), (ox + 2, oy + 4))
            pygame.draw.line(surf, color, (ox, oy), (ox, oy + 2))
            pygame.draw.line(surf, color, (ox + 2, oy + 2), (ox + 2, oy + 4))
        return surf

    def _create_lettered_zombie_dog(self, letter: str) -> pygame.Surface:
        surf = get_character_icon("zombie_dog", self.icon_radius).copy()
        if not letter:
            return surf
        w, h = surf.get_size()
        color = WHITE
        ox, oy = w - 5, h - 6
        if letter == "N":
            pygame.draw.line(surf, color, (ox, oy + 4), (ox, oy))
            pygame.draw.line(surf, color, (ox, oy), (ox + 4, oy + 4))
            pygame.draw.line(surf, color, (ox + 4, oy + 4), (ox + 4, oy))
        elif letter == "T":
            pygame.draw.line(surf, color, (ox, oy), (ox + 4, oy))
            pygame.draw.line(surf, color, (ox + 2, oy), (ox + 2, oy + 4))
        return surf

    def _build_forbidden_icon(self, base_icon: pygame.Surface) -> pygame.Surface:
        cw, ch = self.icon_surfaces["flashlight"].get_size()
        forbidden = pygame.Surface((cw, ch), pygame.SRCALPHA)
        bw, bh = base_icon.get_size()
        forbidden.blit(base_icon, ((cw - bw) // 2, (ch - bh) // 2))
        shade = pygame.Surface((cw, ch), pygame.SRCALPHA)
        shade.fill((0, 0, 0, 80))
        forbidden.blit(shade, (0, 0))
        x0, y0 = 1, 1
        x1, y1 = cw - 2, ch - 2
        pygame.draw.line(forbidden, BLACK, (x0, y0), (x1, y1), width=2)
        pygame.draw.line(forbidden, BLACK, (x1, y0), (x0, y1), width=2)
        pygame.draw.line(forbidden, (255, 50, 50), (x0, y0), (x1, y1), width=1)
        pygame.draw.line(forbidden, (255, 50, 50), (x1, y0), (x0, y1), width=1)
        return forbidden

    def _build_icon_surfaces(self) -> dict[str, pygame.Surface]:
        icon_surfaces: dict[str, pygame.Surface] = {
            "buddy": get_character_icon("buddy", self.icon_radius),
            "survivor": get_character_icon("survivor", self.icon_radius),
            "zombie": self._create_lettered_zombie(""),
            "zombie_tracker": self._create_lettered_zombie("T"),
            "zombie_wall": self._create_lettered_zombie("W"),
            "zombie_line": self._create_lettered_zombie("L"),
            "zombie_solitary": self._create_lettered_zombie("S"),
            "zombie_dog": get_character_icon("zombie_dog", self.icon_radius),
            "zombie_dog_nimble": self._create_lettered_zombie_dog("N"),
            "zombie_dog_tracker": self._create_lettered_zombie_dog("T"),
            "patrol_bot": get_character_icon("patrol_bot", self.icon_radius),
            "carrier_bot": get_character_icon("carrier_bot", self.icon_radius),
            "car": pygame.transform.rotate(
                get_character_icon("car", self.icon_radius), -90
            ),
            "fuel_can": get_character_icon("fuel_can", self.icon_radius),
            "empty_fuel_can": get_character_icon("empty_fuel_can", self.icon_radius),
            "flashlight": build_flashlight_surface(
                int(self.icon_radius * 3.2), int(self.icon_radius * 3.2)
            ),
            "shoes": get_character_icon("shoes", self.icon_radius),
            "pitfall": get_tile_icon("pitfall", self.icon_radius),
            "fall_spawn": get_tile_icon("fall_spawn", self.icon_radius),
            "moving_floor": get_tile_icon("moving_floor", self.icon_radius),
            "fire_floor": get_tile_icon("fire_floor", self.icon_radius),
            "puddle": get_tile_icon("puddle", self.icon_radius),
            "spiky_plant": get_tile_icon("spiky_plant", self.icon_radius),
        }
        self.icon_surfaces = icon_surfaces
        icon_surfaces["car_forbidden"] = self._build_forbidden_icon(
            icon_surfaces["car"]
        )
        icon_surfaces["flashlight_forbidden"] = self._build_forbidden_icon(
            icon_surfaces["flashlight"]
        )
        return icon_surfaces

    def _get_stage_icons(self, stage: Stage) -> list[pygame.Surface]:
        icons: list[pygame.Surface] = []
        if stage.endurance_stage:
            icons.append(self.icon_surfaces["car_forbidden"])

        from ..models import FuelMode

        if stage.fuel_mode == FuelMode.FUEL_CAN:
            icons.append(self.icon_surfaces["fuel_can"])
        elif stage.fuel_mode == FuelMode.REFUEL_CHAIN:
            icons.append(self.icon_surfaces["empty_fuel_can"])

        if stage.buddy_required_count > 0:
            icons.append(self.icon_surfaces["buddy"])
        if stage.survivor_rescue_stage:
            icons.append(self.icon_surfaces["survivor"])

        has_zombie = (
            stage.exterior_spawn_weight > 0
            or stage.interior_spawn_weight > 0
            or stage.interior_fall_spawn_weight > 0
        )
        if has_zombie:
            if stage.zombie_normal_ratio > 0:
                icons.append(self.icon_surfaces["zombie"])
            if stage.zombie_tracker_ratio > 0:
                icons.append(self.icon_surfaces["zombie_tracker"])
            if stage.zombie_wall_hugging_ratio > 0:
                icons.append(self.icon_surfaces["zombie_wall"])
            if stage.zombie_lineformer_ratio > 0:
                icons.append(self.icon_surfaces["zombie_line"])
            if stage.zombie_solitary_ratio > 0:
                icons.append(self.icon_surfaces["zombie_solitary"])

        if stage.zombie_dog_ratio > 0:
            icons.append(self.icon_surfaces["zombie_dog"])
        if stage.zombie_nimble_dog_ratio > 0:
            icons.append(self.icon_surfaces["zombie_dog_nimble"])
        if stage.zombie_tracker_dog_ratio > 0:
            icons.append(self.icon_surfaces["zombie_dog_tracker"])
        if stage.spiky_plant_density > 0 or stage.spiky_plant_zones:
            icons.append(self.icon_surfaces["spiky_plant"])

        if (
            stage.interior_fall_spawn_weight > 0
            or stage.fall_spawn_zones
            or stage.fall_spawn_cell_ratio > 0
        ):
            icons.append(self.icon_surfaces["fall_spawn"])
        if stage.pitfall_density > 0 or stage.pitfall_zones:
            icons.append(self.icon_surfaces["pitfall"])
        if stage.moving_floor_zones or stage.moving_floor_cells:
            icons.append(self.icon_surfaces["moving_floor"])
        if stage.fire_floor_density > 0 or stage.fire_floor_zones:
            icons.append(self.icon_surfaces["fire_floor"])
        if stage.puddle_density > 0 or stage.puddle_zones:
            icons.append(self.icon_surfaces["puddle"])

        if stage.flashlight_spawn_count <= 0:
            icons.append(self.icon_surfaces["flashlight_forbidden"])
        if stage.shoes_spawn_count > 0:
            icons.append(self.icon_surfaces["shoes"])
        if stage.patrol_bot_spawn_rate > 0:
            icons.append(self.icon_surfaces["patrol_bot"])
        if stage.carrier_bot_spawns or stage.carrier_bot_spawn_density > 0:
            icons.append(self.icon_surfaces["carrier_bot"])
        return icons

    def _page_available(self, page_index: int) -> bool:
        if page_index <= 0:
            return True
        if page_index >= len(self.stage_pages):
            return False
        prev_page_index = page_index - 1
        clears_on_prev_page = sum(
            self.stage_progress.get(option["stage"].id, 0) > 0
            for option in self.stage_pages[prev_page_index]
        )
        required_clears = min(5, len(self.stage_pages[prev_page_index]))
        return clears_on_prev_page >= required_clears

    def _page_index_for_stage(self, stage_idx: int) -> int:
        if stage_idx < self.first_page_size:
            return 0
        return 1 + (stage_idx - self.first_page_size) // self.other_page_size

    def _build_options(
        self, page_index: int
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        resource_options = self._build_resource_options(page_index)
        if not self.stage_pages:
            return resource_options, []
        page_index = max(0, min(page_index, len(self.stage_pages) - 1))
        stage_options = self.stage_pages[page_index]
        options = list(stage_options) + resource_options
        return options, stage_options

    def _build_resource_options(self, _page_index: int) -> list[dict[str, Any]]:
        options = list(self.resource_base_options)
        options.insert(0, {"type": "fullscreen"})
        return options

    def _switch_page(self, delta: int) -> None:
        if delta < 0:
            if self.current_page <= 0:
                return
            self.current_page -= 1
        else:
            target_page = self.current_page + 1
            if target_page >= len(self.stage_pages):
                return
            if not self._page_available(target_page):
                return
            self.current_page = target_page
        self.options, self.stage_options = self._build_options(self.current_page)
        self.selected = 0

    def _activate_current_selection(self) -> ScreenTransition | None:
        current = self.options[self.selected]
        if current["type"] == "stage" and current.get("available"):
            seed_value = int(self.current_seed_text) if self.current_seed_text else None
            return ScreenTransition(
                ScreenID.GAMEPLAY,
                stage=current["stage"],
                seed=seed_value,
                seed_text=self.current_seed_text,
                seed_is_auto=self.current_seed_auto,
            )
        if current["type"] == "settings":
            return ScreenTransition(
                ScreenID.SETTINGS,
                seed_text=self.current_seed_text,
                seed_is_auto=self.current_seed_auto,
            )
        if current["type"] == "fullscreen":
            toggle_fullscreen()
            adjust_menu_logical_size()
            return None
        if current["type"] == "readme":
            _open_readme_link(page_index=self.current_page)
            return None
        if current["type"] == "quit":
            return ScreenTransition(
                ScreenID.EXIT,
                seed_text=self.current_seed_text,
                seed_is_auto=self.current_seed_auto,
            )
        return None

    def _current_option_is_fullscreen(self) -> bool:
        return self.options[self.selected].get("type") == "fullscreen"

    def _render_frame(self) -> None:
        self.screen.fill(BLACK)
        try:
            font_settings = get_font_settings()
            option_targets: list[ClickTarget] = []
            page_targets: list[ClickTarget] = []
            self.stage_pane_rect = pygame.Rect(0, 0, 0, 0)

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
            list_column_width = self.width // 2 - 36
            info_column_x = self.width // 2 + 12
            info_column_width = self.width - info_column_x - 24
            section_top = TITLE_SECTION_TOP
            highlight_color = (65, 65, 65)

            stage_count = len(self.stage_options)
            stage_header_text = tr("menu.sections.stage_select")
            can_go_left = self.current_page > 0
            can_go_right = self.current_page < len(
                self.stage_pages
            ) - 1 and self._page_available(self.current_page + 1)
            show_page_arrows = len(self.stage_pages) > 1 and (
                can_go_left or can_go_right
            )
            section_size = font_settings.scaled_size(11)
            section_font = _get_font(section_size)
            header_width, header_height, _ = _measure_text(
                stage_header_text, section_font, list_column_width
            )
            blit_text_wrapped(
                self.screen,
                stage_header_text,
                section_font,
                LIGHT_GRAY,
                (list_column_x, section_top),
                list_column_width,
                line_height_scale=font_settings.line_height_scale,
            )
            if show_page_arrows:
                tri_w = 6
                tri_h = 10
                tri_gap = 12
                tri_color_enabled = LIGHT_GRAY
                mouse_state = read_mouse_state()
                mouse_pos = mouse_state.pos
                mouse_focused = mouse_state.focused
                header_mid_y = section_top + header_height // 2
                left_enabled = can_go_left
                right_enabled = can_go_right
                left_cx = list_column_x - tri_gap
                right_cx = list_column_x + header_width + tri_gap
                thick = 2
                left_points = [
                    (left_cx + tri_w // 2, header_mid_y - tri_h // 2),
                    (left_cx + tri_w // 2 - thick, header_mid_y - tri_h // 2),
                    (left_cx - tri_w // 2, header_mid_y),
                    (left_cx + tri_w // 2 - thick, header_mid_y + tri_h // 2),
                    (left_cx + tri_w // 2, header_mid_y + tri_h // 2),
                    (left_cx - tri_w // 2 + thick, header_mid_y),
                ]
                right_points = [
                    (right_cx - tri_w // 2, header_mid_y - tri_h // 2),
                    (right_cx - tri_w // 2 + thick, header_mid_y - tri_h // 2),
                    (right_cx + tri_w // 2, header_mid_y),
                    (right_cx - tri_w // 2 + thick, header_mid_y + tri_h // 2),
                    (right_cx - tri_w // 2, header_mid_y + tri_h // 2),
                    (right_cx + tri_w // 2 - thick, header_mid_y),
                ]
                pad = 4
                if left_enabled:
                    left_bg = pygame.Rect(
                        left_cx - tri_w // 2 - pad,
                        header_mid_y - tri_h // 2 - pad,
                        tri_w + pad * 2,
                        tri_h + pad * 2,
                    )
                    if mouse_focused and left_bg.collidepoint(mouse_pos):
                        pygame.draw.rect(self.screen, highlight_color, left_bg)
                    pygame.draw.polygon(self.screen, tri_color_enabled, left_points)
                    page_targets.append(ClickTarget("page_left", left_bg))
                if right_enabled:
                    right_bg = pygame.Rect(
                        right_cx - tri_w // 2 - pad,
                        header_mid_y - tri_h // 2 - pad,
                        tri_w + pad * 2,
                        tri_h + pad * 2,
                    )
                    if mouse_focused and right_bg.collidepoint(mouse_pos):
                        pygame.draw.rect(self.screen, highlight_color, right_bg)
                    pygame.draw.polygon(self.screen, tri_color_enabled, right_points)
                    page_targets.append(ClickTarget("page_right", right_bg))
            stage_header_rect = pygame.Rect(
                list_column_x, section_top, max(header_width, 1), header_height
            )
            stage_rows_start = stage_header_rect.bottom + 6
            resource_row_height = base_row_height
            resource_offset = resource_row_height
            stage_row_heights = [
                (selected_row_height if idx == self.selected else base_row_height)
                for idx in range(stage_count)
            ]
            fixed_stage_block_height = (
                base_row_height * max(stage_count - 1, 0) + selected_row_height
            )
            self.stage_pane_rect = pygame.Rect(
                list_column_x,
                stage_rows_start - 4,
                max(1, list_column_width),
                max(1, fixed_stage_block_height + 8),
            )
            action_header_pos = (
                list_column_x,
                stage_rows_start + fixed_stage_block_height + resource_offset,
            )
            action_header_text = tr("menu.sections.resources")
            action_width, action_height, _ = _measure_text(
                action_header_text, section_font, list_column_width
            )
            blit_text_wrapped(
                self.screen,
                action_header_text,
                section_font,
                LIGHT_GRAY,
                action_header_pos,
                list_column_width,
                line_height_scale=font_settings.line_height_scale,
            )
            action_header_rect = pygame.Rect(
                action_header_pos[0],
                action_header_pos[1],
                max(action_width, 1),
                action_height,
            )
            action_rows_start = action_header_rect.bottom + 6

            row_top = stage_rows_start
            selected_stage_highlight_rect: pygame.Rect | None = None
            for idx, option in enumerate(self.stage_options):
                row_height = stage_row_heights[idx]
                full_content_width = (info_column_x + info_column_width) - list_column_x
                highlight_rect = pygame.Rect(
                    list_column_x, row_top - 2, full_content_width, row_height
                )
                option_targets.append(ClickTarget(idx, highlight_rect.copy()))
                cleared = self.stage_progress.get(option["stage"].id, 0) > 0
                base_color = WHITE if cleared else _UNCLEARED_STAGE_COLOR
                color = base_color
                is_selected = idx == self.selected
                if is_selected:
                    pygame.draw.rect(self.screen, highlight_color, highlight_rect)
                    selected_stage_highlight_rect = highlight_rect.copy()
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
                    self.screen,
                    label,
                    stage_option_font,
                    color,
                    (list_column_x + 8, row_top + (row_height - text_height) // 2),
                    10_000,
                    line_height_scale=font_settings.line_height_scale,
                )
                if cleared and option.get("available"):
                    label_width, _, _ = _measure_text(label, stage_option_font, 10_000)
                    icons = self._get_stage_icons(option["stage"])
                    icon_x = list_column_x + 8 + label_width + 6
                    icon_y_center = row_top + row_height // 2
                    icon_bounds: pygame.Rect | None = None
                    for icon_surf in icons:
                        icon_rect = icon_surf.get_rect(
                            center=(icon_x + icon_surf.get_width() // 2, icon_y_center)
                        )
                        self.screen.blit(icon_surf, icon_rect)
                        icon_bounds = (
                            icon_rect.copy()
                            if icon_bounds is None
                            else icon_bounds.union(icon_rect)
                        )
                        icon_x += icon_surf.get_width() + 2
                    if icon_bounds is not None and not is_selected:
                        icon_overlay = pygame.Surface(
                            (max(1, icon_bounds.width), max(1, icon_bounds.height)),
                            pygame.SRCALPHA,
                        )
                        icon_overlay.fill((0, 0, 0, 80))
                        self.screen.blit(icon_overlay, icon_bounds.topleft)
                row_top += row_height

            resource_option_size = font_settings.scaled_size(11)
            resource_option_font = _get_font(resource_option_size)
            resource_options = self._build_resource_options(self.current_page)
            for idx, option in enumerate(resource_options):
                option_idx = stage_count + idx
                row_top = action_rows_start + idx * resource_row_height
                highlight_rect = pygame.Rect(
                    list_column_x, row_top - 2, list_column_width, resource_row_height
                )
                option_targets.append(ClickTarget(option_idx, highlight_rect.copy()))
                is_selected = option_idx == self.selected
                if is_selected:
                    pygame.draw.rect(self.screen, highlight_color, highlight_rect)
                if option["type"] == "settings":
                    label = tr("menu.settings")
                elif option["type"] == "fullscreen":
                    label = tr("menu.display_mode_window_size")
                elif option["type"] == "readme":
                    label_key = (
                        "menu.readme_stage_group"
                        if self.current_page > 0
                        else "menu.readme"
                    )
                    label = f"> {tr(label_key)}"
                else:
                    label = tr("menu.quit")
                text_height = int(
                    round(
                        resource_option_font.get_linesize()
                        * font_settings.line_height_scale
                    )
                )
                blit_text_wrapped(
                    self.screen,
                    label,
                    resource_option_font,
                    WHITE,
                    (
                        list_column_x + 8,
                        row_top + (resource_row_height - text_height) // 2,
                    ),
                    list_column_width - 12,
                    line_height_scale=font_settings.line_height_scale,
                )

            current = self.options[self.selected]
            desc_area_top = section_top
            if current["type"] == "stage":
                desc_anchor_gap = 4
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
                if selected_stage_highlight_rect is not None:
                    if self.selected < stage_count // 2:
                        desc_area_top = (
                            selected_stage_highlight_rect.bottom + desc_anchor_gap
                        )
                    else:
                        desc_area_top = (
                            selected_stage_highlight_rect.top
                            - desc_height
                            - desc_anchor_gap
                        )
                else:
                    desc_area_top = section_top
                desc_area_top = max(
                    section_top, min(desc_area_top, self.height - desc_height - 8)
                )
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
                self.screen.blit(desc_panel, desc_panel_rect.topleft)
                blit_text_wrapped(
                    self.screen,
                    current["stage"].description,
                    desc_font,
                    desc_color,
                    (info_column_x, desc_area_top),
                    info_column_width,
                    line_height_scale=font_settings.line_height_scale,
                )

            option_help_top = desc_area_top
            if current["type"] != "stage":
                option_help_top = action_rows_start
            help_text = ""
            if current["type"] == "settings":
                help_text = tr("menu.option_help.settings")
            elif current["type"] == "fullscreen":
                help_text = tr("menu.option_help.display_mode_window_size")
            elif current["type"] == "quit":
                help_text = tr("menu.option_help.quit")
            elif current["type"] == "readme":
                help_key = (
                    "menu.option_help.readme_stage_group"
                    if self.current_page > 0
                    else "menu.option_help.readme"
                )
                help_text = tr(help_key)
            if help_text:
                desc_size = font_settings.scaled_size(11)
                desc_font = _get_font(desc_size)
                blit_text_wrapped(
                    self.screen,
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
            hint_step = hint_line_height
            seed_offset_y = hint_step
            seed_bottom = self.height - 30 + seed_offset_y
            if self.current_page == 0:
                hint_lines = [tr("menu.hints.navigate")]
                if len(self.stage_pages) > 1 and self._page_available(1):
                    hint_lines.append(tr("menu.hints.page_switch"))
                hint_lines.extend(tr("menu.hints.confirm").splitlines())
                hint_start_y = seed_bottom - (len(hint_lines) * hint_step)
                for offset, line in enumerate(hint_lines):
                    blit_text_wrapped(
                        self.screen,
                        line,
                        hint_font,
                        WHITE,
                        (list_column_x, hint_start_y + offset * hint_step),
                        list_column_width,
                        line_height_scale=font_settings.line_height_scale,
                    )

            seed_value_display = (
                self.current_seed_text
                if self.current_seed_text
                else tr("menu.seed_empty")
            )
            seed_label = tr("menu.seed_label", value=seed_value_display)
            seed_width, seed_height, _ = _measure_text(
                seed_label, hint_font, info_column_width
            )
            blit_text_wrapped(
                self.screen,
                seed_label,
                hint_font,
                LIGHT_GRAY,
                (info_column_x, seed_bottom - seed_height),
                info_column_width,
                line_height_scale=font_settings.line_height_scale,
            )
            seed_rect = pygame.Rect(
                info_column_x,
                seed_bottom - seed_height,
                max(seed_width, 1),
                seed_height,
            )

            if self.current_page == 0:
                seed_hint = tr("menu.seed_hint")
                seed_hint_lines = wrap_text(seed_hint, hint_font, info_column_width)
                seed_hint_height = len(seed_hint_lines) * hint_line_height
                seed_hint_top = seed_rect.top - 4 - seed_hint_height
                blit_text_wrapped(
                    self.screen,
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
                title_text, title_font, self.width
            )
            title_topleft = (
                self.width // 2 - title_width // 2,
                TITLE_HEADER_Y - title_height // 2,
            )
            blit_text_wrapped(
                self.screen,
                title_text,
                title_font,
                LIGHT_GRAY,
                title_topleft,
                self.width,
                line_height_scale=font_settings.line_height_scale,
            )
            title_rect = pygame.Rect(
                title_topleft[0], title_topleft[1], max(title_width, 1), title_height
            )
            version_font = _get_font(font_settings.scaled_size(11))
            version_text = f"v{__version__}"
            version_width, version_height, _ = _measure_text(
                version_text, version_font, self.width
            )
            version_topleft = (title_rect.right + 4, title_rect.bottom - version_height)
            blit_text_wrapped(
                self.screen,
                version_text,
                version_font,
                LIGHT_GRAY,
                version_topleft,
                self.width - version_topleft[0],
                line_height_scale=font_settings.line_height_scale,
            )
            self.option_click_map.set_targets(option_targets)
            self.page_button_click_map.set_targets(page_targets)
        except pygame.error as exc:
            print(f"Error rendering title screen: {exc}")

    def _handle_event(self, event: pygame.event.Event) -> ScreenTransition | None:
        if event.type == pygame.QUIT:
            return ScreenTransition(
                ScreenID.EXIT,
                seed_text=self.current_seed_text,
                seed_is_auto=self.current_seed_auto,
            )
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
            target = self.option_click_map.pick_hover(event.pos)
            if isinstance(target, int):
                self.selected = target
            return None
        if (
            event.type == pygame.MOUSEBUTTONUP
            and event.button == 1
            and self.mouse_ui_guard.can_process_mouse()
            and pygame.time.get_ticks() >= self.confirm_armed_at
        ):
            page_target = self.page_button_click_map.pick_click(event.pos)
            if page_target == "page_left":
                self._switch_page(-1)
                return None
            if page_target == "page_right":
                self._switch_page(1)
                return None
            target = self.option_click_map.pick_click(event.pos)
            if isinstance(target, int):
                self.selected = target
                return self._activate_current_selection()
            return None
        if event.type == pygame.MOUSEWHEEL and self.mouse_ui_guard.can_process_mouse():
            if self.stage_pane_rect.collidepoint(read_mouse_state().pos):
                wheel_y = int(getattr(event, "y", 0))
                if getattr(event, "flipped", False):
                    wheel_y = -wheel_y
                if wheel_y > 0:
                    self._switch_page(-1)
                elif wheel_y < 0:
                    self._switch_page(1)
            return None
        self.input_helper.handle_device_event(event)
        if event.type == pygame.KEYDOWN:
            if event.key == pygame.K_BACKSPACE:
                self.current_seed_text = _generate_auto_seed_text()
                self.current_seed_auto = True
                return None
            if event.unicode and event.unicode.isdigit():
                if self.current_seed_auto:
                    self.current_seed_text = ""
                    self.current_seed_auto = False
                if len(self.current_seed_text) < MAX_SEED_DIGITS:
                    self.current_seed_text += event.unicode
                return None
        return None

    def _handle_snapshot(self, snapshot: Any) -> ScreenTransition | None:
        if snapshot.shortcut_pressed(KeyboardShortcut.WINDOW_SCALE_DOWN):
            nudge_menu_window_scale(0.5)
        if snapshot.shortcut_pressed(KeyboardShortcut.WINDOW_SCALE_UP):
            nudge_menu_window_scale(2.0)
        if snapshot.shortcut_pressed(KeyboardShortcut.TOGGLE_FULLSCREEN):
            toggle_fullscreen()
            adjust_menu_logical_size()
        # Secret pad gesture: hold Select/Back + South(A) to toggle fullscreen.
        if self.input_helper.is_select_held():
            if snapshot.pressed(CommonAction.CONFIRM):
                toggle_fullscreen()
                adjust_menu_logical_size()
                return None
        if snapshot.pressed(CommonAction.LEFT):
            if self._current_option_is_fullscreen():
                nudge_menu_window_scale(0.5)
            else:
                self._switch_page(-1)
        if snapshot.pressed(CommonAction.RIGHT):
            if self._current_option_is_fullscreen():
                nudge_menu_window_scale(2.0)
            else:
                self._switch_page(1)
        if snapshot.pressed(CommonAction.UP):
            self.selected = (self.selected - 1) % len(self.options)
        if snapshot.pressed(CommonAction.DOWN):
            self.selected = (self.selected + 1) % len(self.options)
        if snapshot.pressed(CommonAction.CONFIRM):
            if pygame.time.get_ticks() >= self.confirm_armed_at:
                return self._activate_current_selection()
        return None

    def run(self) -> ScreenTransition:
        while True:
            events = pygame.event.get()
            for event in events:
                transition = self._handle_event(event)
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

    return TitleScreenController(
        screen=screen,
        clock=clock,
        config=config,
        fps=fps,
        stages=stages,
        default_stage_id=default_stage_id,
        screen_size=screen_size,
        seed_text=seed_text,
        seed_is_auto=seed_is_auto,
    ).run()
