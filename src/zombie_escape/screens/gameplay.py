from __future__ import annotations

import math
import os
from pathlib import Path
from typing import TYPE_CHECKING, Any

import pygame
from pygame import surface, time

from ..colors import LIGHT_GRAY, RED, WHITE, YELLOW
from ..font_utils import load_font, render_text_surface
from ..gameplay_constants import (
    CAR_HINT_DELAY_MS_DEFAULT,
    SURVIVAL_TIME_ACCEL_SUBSTEPS,
    SURVIVAL_TIME_ACCEL_MAX_SUBSTEP,
)
from ..gameplay import (
    MapGenerationError,
    apply_passenger_speed_penalty,
    check_interactions,
    cleanup_survivor_messages,
    generate_level_from_blueprint,
    initialize_game_state,
    maintain_waiting_car_supply,
    nearest_waiting_car,
    place_empty_fuel_can,
    schedule_timed_message,
    place_flashlights,
    place_fuel_can,
    place_fuel_station,
    place_shoes,
    process_player_input,
    setup_player_and_cars,
    spawn_initial_patrol_bots,
    spawn_initial_zombies,
    spawn_houseplants,
    spawn_survivors,
    sync_ambient_palette_with_flashlights,
    update_entities,
    update_footprints,
    update_endurance_timer,
)
from ..gameplay.state import frames_to_ms, ms_to_frames
from ..gameplay.constants import (
    INTRO_MESSAGE_DISPLAY_FRAMES,
    LAYER_ITEMS,
)
from ..input_utils import (
    ClickTarget,
    ClickableMap,
    CommonAction,
    InputHelper,
    MouseUiGuard,
)
from ..gameplay.spawn import _alive_waiting_cars
from ..world_grid import build_wall_index
from ..entities.walls import consume_wall_index_dirty
from ..localization import get_font_settings, translate as tr
from ..models import FuelMode, FuelProgress, Stage
from ..render import (
    draw,
    draw_debug_overview,
    draw_pause_overlay,
    prewarm_fog_overlays,
    blit_message_wrapped,
)
from ..render_constants import (
    GAMEPLAY_FONT_SIZE,
    TIMED_MESSAGE_LEFT_X,
    TIMED_MESSAGE_TOP_Y,
)
from ..rng import generate_seed, seed_rng
from ..progress import record_stage_clear
from ..screens import ScreenID, ScreenTransition
from ..windowing import nudge_window_scale, present, sync_window_size, toggle_fullscreen

if TYPE_CHECKING:
    from ..render import RenderAssets


_SHARED_FOG_CACHE: dict[str, Any] | None = None
_MOUSE_STEERING_DEADZONE_SCALE = 2.0
_MOUSE_ACCEL_HOLD_SCALE = 1.2
_MOUSE_CURSOR_PERSIST_MS = 10_000
_PAUSE_HOTSPOT_COLOR = (48, 48, 48)
_PAUSE_HOTSPOT_TRI_SIZE = 7


def _resolve_hint_target_type(
    *,
    stage: Stage,
    fuel_progress: FuelProgress,
    game_data: Any,
    player_in_car: bool,
    active_car: Any,
    report_internal_error_once: callable,
) -> str | None:
    if stage.fuel_mode == FuelMode.REFUEL_CHAIN:
        if fuel_progress < FuelProgress.EMPTY_CAN:
            if game_data.empty_fuel_can and game_data.empty_fuel_can.alive():
                return "empty_fuel_can"
            report_internal_error_once("missing_empty_fuel_can_for_refuel")
            return None
        if fuel_progress == FuelProgress.EMPTY_CAN:
            if game_data.fuel_station and game_data.fuel_station.alive():
                return "fuel_station"
            report_internal_error_once("missing_fuel_station_for_refuel")
            return None
        if not player_in_car and (active_car or _alive_waiting_cars(game_data)):
            return "car"
        return None

    if stage.fuel_mode == FuelMode.FUEL_CAN and fuel_progress < FuelProgress.FULL_CAN:
        if game_data.fuel and game_data.fuel.alive():
            return "fuel"
        report_internal_error_once("missing_fuel_can_for_fuel_mode")
        return None

    if not player_in_car and (active_car or _alive_waiting_cars(game_data)):
        return "car"
    return None


def _resolve_hint_target_position(
    *,
    target_type: str | None,
    game_data: Any,
    active_car: Any,
    player_pos: tuple[float, float],
) -> tuple[float, float] | None:
    if not target_type:
        return None
    if target_type == "fuel" and game_data.fuel and game_data.fuel.alive():
        return game_data.fuel.rect.center
    if (
        target_type == "empty_fuel_can"
        and game_data.empty_fuel_can
        and game_data.empty_fuel_can.alive()
    ):
        return game_data.empty_fuel_can.rect.center
    if (
        target_type == "fuel_station"
        and game_data.fuel_station
        and game_data.fuel_station.alive()
    ):
        return game_data.fuel_station.rect.center
    if target_type == "car":
        if active_car:
            return active_car.rect.center
        waiting_target = nearest_waiting_car(game_data, player_pos)
        if waiting_target:
            return waiting_target.rect.center
    return None


def _spawn_stage_items(
    *,
    game_data: Any,
    layout_data: dict[str, Any],
    player: Any,
) -> None:
    stage = game_data.stage
    occupied_centers: set[tuple[int, int]] = set()
    cell_size = game_data.cell_size

    if stage.fuel_mode < FuelMode.START_FULL:
        fuel_spawn_count = stage.fuel_spawn_count
        empty_fuel_can_spawn_count = stage.empty_fuel_can_spawn_count
        fuel_station_spawn_count = stage.fuel_station_spawn_count
        if stage.endurance_stage:
            fuel_spawn_count = 0
            empty_fuel_can_spawn_count = 0
            fuel_station_spawn_count = 0
        if stage.fuel_mode == FuelMode.REFUEL_CHAIN:
            empty_fuel_can = place_empty_fuel_can(
                layout_data["empty_fuel_can_cells"],
                cell_size,
                player,
                cars=game_data.waiting_cars,
                reserved_centers=occupied_centers,
                count=empty_fuel_can_spawn_count,
            )
            if empty_fuel_can:
                game_data.empty_fuel_can = empty_fuel_can
                game_data.groups.all_sprites.add(empty_fuel_can, layer=LAYER_ITEMS)
                occupied_centers.add(empty_fuel_can.rect.center)
            fuel_station = place_fuel_station(
                layout_data["fuel_station_cells"],
                cell_size,
                player,
                cars=game_data.waiting_cars,
                reserved_centers=occupied_centers,
                count=fuel_station_spawn_count,
            )
            if fuel_station:
                game_data.fuel_station = fuel_station
                game_data.groups.all_sprites.add(fuel_station, layer=LAYER_ITEMS)
                occupied_centers.add(fuel_station.rect.center)
        else:
            fuel_can = place_fuel_can(
                layout_data["fuel_cells"],
                cell_size,
                player,
                cars=game_data.waiting_cars,
                reserved_centers=occupied_centers,
                count=fuel_spawn_count,
            )
            if fuel_can:
                game_data.fuel = fuel_can
                game_data.groups.all_sprites.add(fuel_can, layer=LAYER_ITEMS)
                occupied_centers.add(fuel_can.rect.center)

    flashlight_count = stage.initial_flashlight_count
    flashlights = place_flashlights(
        layout_data["flashlight_cells"],
        cell_size,
        player,
        cars=game_data.waiting_cars,
        reserved_centers=occupied_centers,
        count=max(0, flashlight_count),
    )
    game_data.flashlights = flashlights
    game_data.groups.all_sprites.add(flashlights, layer=LAYER_ITEMS)
    for flashlight in flashlights:
        occupied_centers.add(flashlight.rect.center)

    shoes_count = stage.initial_shoes_count
    shoes_list = place_shoes(
        layout_data["shoes_cells"],
        cell_size,
        player,
        cars=game_data.waiting_cars,
        reserved_centers=occupied_centers,
        count=max(0, shoes_count),
    )
    game_data.shoes = shoes_list
    game_data.groups.all_sprites.add(shoes_list, layer=LAYER_ITEMS)


class GameplayScreenRunner:
    def __init__(
        self,
        *,
        screen: surface.Surface,
        clock: time.Clock,
        config: dict[str, Any],
        fps: int,
        stage: Stage,
        show_pause_overlay: bool,
        seed: int | None,
        render_assets: "RenderAssets",
        debug_mode: bool = False,
        show_fps: bool = False,
        profiler: object | None = None,
        profiler_output: Path | None = None,
    ) -> None:
        self.screen = screen
        self.clock = clock
        self.config = config
        self.fps = fps
        self.stage = stage
        self.show_pause_overlay = show_pause_overlay
        self.seed = seed
        self.render_assets = render_assets
        self.debug_mode = debug_mode
        self.show_fps = show_fps
        self.profiler = profiler
        self.profiler_output = profiler_output

        self.screen_width = screen.get_width()
        self.screen_height = screen.get_height()
        self.use_busy_loop = os.environ.get("ZOMBIE_ESCAPE_BUSY_LOOP") == "1"
        self.mouse_hidden = False
        self.profiling_active = False
        self.paused_manual = False
        self.paused_focus = False
        self.pause_selected_index = 0
        self.pause_option_ids = ["resume", "title"]
        self.pause_option_click_map = ClickableMap()
        self.pause_mouse_ui_guard = MouseUiGuard()
        self.pause_hotspot_inside_prev = False
        self.debug_overview = False
        self.reported_internal_errors: set[str] = set()
        self.input_helper = InputHelper()
        self.mouse_steering_active = False
        self.mouse_cursor_screen_pos: tuple[int, int] | None = None
        self.mouse_cursor_visible_until_ms = 0

        self.game_data: Any = None
        self.overview_surface: surface.Surface | None = None

    def run(self) -> ScreenTransition:
        transition = self._setup_game()
        if transition is not None:
            return transition
        assert self.game_data is not None
        assert self.overview_surface is not None

        self._set_mouse_hidden(pygame.mouse.get_focused())
        while True:
            frame_ms = (
                self.clock.tick_busy_loop(self.fps)
                if self.use_busy_loop
                else self.clock.tick(self.fps)
            )
            dt = frame_ms / 1000.0
            current_fps = self.clock.get_fps()

            if self._is_game_finished(frame_ms, current_fps):
                return self._finalize(
                    ScreenTransition(
                        ScreenID.GAME_OVER,
                        stage=self.stage,
                        game_data=self.game_data,
                        config=self.config,
                    )
                )

            transition, input_snapshot = self._handle_runtime_events()
            if transition is not None:
                return transition

            if self.paused_manual or self.paused_focus:
                self._set_mouse_hidden(False)
                self._render_paused_state(current_fps)
                continue
            self._set_mouse_hidden(pygame.mouse.get_focused())

            self._update_world(dt, input_snapshot)
            if self.debug_overview:
                draw_debug_overview(
                    self.render_assets,
                    self.screen,
                    self.overview_surface,
                    self.game_data,
                    self.config,
                    screen_width=self.screen_width,
                    screen_height=self.screen_height,
                )
                present(self.screen)
                continue

            self._draw_game_frame(current_fps)

    def _setup_game(self) -> ScreenTransition | None:
        seed_value = self.seed if self.seed is not None else generate_seed()
        applied_seed = seed_rng(seed_value)
        loading_started_ms = pygame.time.get_ticks()
        self._show_loading_still()

        self.game_data = initialize_game_state(self.config, self.stage)
        self.game_data.state.seed = applied_seed
        self.game_data.state.debug_mode = self.debug_mode
        self.game_data.state.show_fps = self.show_fps

        global _SHARED_FOG_CACHE
        if _SHARED_FOG_CACHE is None:
            prewarm_fog_overlays(
                self.game_data.fog,
                self.render_assets,
                stage=self.stage,
            )
            _SHARED_FOG_CACHE = self.game_data.fog
        else:
            self.game_data.fog = _SHARED_FOG_CACHE

        if self.stage.intro_key and self.game_data.state.timed_message:
            loading_elapsed_ms = max(0, pygame.time.get_ticks() - loading_started_ms)
            remaining_ms = max(
                0, frames_to_ms(INTRO_MESSAGE_DISPLAY_FRAMES) - loading_elapsed_ms
            )
            schedule_timed_message(
                self.game_data.state,
                tr(self.stage.intro_key),
                duration_frames=max(0, ms_to_frames(remaining_ms)),
                clear_on_input=True,
                color=LIGHT_GRAY,
                align="left",
                now_ms=self.game_data.state.clock.elapsed_ms,
            )

        try:
            layout, layout_data, wall_group, all_sprites, blueprint = (
                generate_level_from_blueprint(
                    self.stage,
                    self.config,
                    seed=self.game_data.state.seed,
                    ambient_palette_key=self.game_data.state.ambient_palette_key,
                )
            )
            self.game_data.layout = layout
            self.game_data.blueprint = blueprint
            self.game_data.groups.wall_group = wall_group
            self.game_data.groups.all_sprites = all_sprites
            self.game_data.wall_index_dirty = True
        except MapGenerationError:
            self.screen.fill((0, 0, 0))
            blit_message_wrapped(
                self.screen,
                tr("errors.map_generation_failed"),
                16,
                RED,
                (self.screen_width // 2, self.screen_height // 2),
                max_width=self.screen_width - 40,
            )
            present(self.screen)
            pygame.time.delay(3000)
            return self._finalize(ScreenTransition(ScreenID.TITLE))

        sync_ambient_palette_with_flashlights(self.game_data, force=True)
        initial_waiting = max(0, self.stage.waiting_car_target_count)
        player, waiting_cars = setup_player_and_cars(
            self.game_data, layout_data, car_count=initial_waiting
        )
        self.game_data.player = player
        self.game_data.waiting_cars = waiting_cars
        self.game_data.car = None
        maintain_waiting_car_supply(
            self.game_data, minimum=self.stage.waiting_car_target_count
        )
        apply_passenger_speed_penalty(self.game_data)
        spawn_survivors(self.game_data, layout_data)
        _spawn_stage_items(
            game_data=self.game_data,
            layout_data=layout_data,
            player=player,
        )
        spawn_initial_zombies(self.game_data, player, layout_data, self.config)
        spawn_initial_patrol_bots(self.game_data, player, layout_data)

        hp_list = spawn_houseplants(self.game_data, layout_data)
        hp_cells = layout_data.get("houseplant_cells", [])
        for cell, hp in zip(hp_cells, hp_list):
            self.game_data.houseplants[cell] = hp

        update_footprints(self.game_data, self.config)
        level_rect = self.game_data.layout.field_rect
        self.overview_surface = pygame.Surface((level_rect.width, level_rect.height))
        return None

    def _handle_runtime_events(self) -> tuple[ScreenTransition | None, Any]:
        assert self.game_data is not None
        events = pygame.event.get()
        for event in events:
            if event.type == pygame.QUIT:
                return (
                    self._finalize(ScreenTransition(ScreenID.EXIT)),
                    self.input_helper.snapshot(events, pygame.key.get_pressed()),
                )
            if event.type in (pygame.WINDOWSIZECHANGED, pygame.VIDEORESIZE):
                sync_window_size(event, game_data=self.game_data)
                continue
            self.input_helper.handle_device_event(event)
            if event.type == pygame.WINDOWFOCUSLOST:
                self.paused_focus = True
                self.pause_selected_index = 0
                self.pause_mouse_ui_guard.handle_focus_event(event)
            if event.type == pygame.WINDOWFOCUSGAINED:
                self.pause_mouse_ui_guard.handle_focus_event(event)
            if (
                not (self.paused_manual or self.paused_focus)
                and event.type == pygame.MOUSEMOTION
            ):
                now_inside_hotspot = self._pause_hotspot_kind_at(event.pos) is not None
                if now_inside_hotspot and not self.pause_hotspot_inside_prev:
                    self.paused_manual = True
                    self.pause_selected_index = 0
                self.pause_hotspot_inside_prev = now_inside_hotspot
                continue
            if (
                (self.paused_manual or self.paused_focus)
                and event.type == pygame.MOUSEMOTION
                and self.pause_mouse_ui_guard.can_process_mouse()
            ):
                hover_target = self.pause_option_click_map.pick_hover(event.pos)
                if isinstance(hover_target, int):
                    self.pause_selected_index = hover_target
                continue
            if (
                (self.paused_manual or self.paused_focus)
                and event.type == pygame.MOUSEBUTTONUP
                and event.button == 1
                and self.pause_mouse_ui_guard.can_process_mouse()
            ):
                click_target = self.pause_option_click_map.pick_click(event.pos)
                if isinstance(click_target, int):
                    self.pause_selected_index = click_target
                    transition = self._activate_pause_selection()
                    if transition is not None:
                        return transition, self.input_helper.snapshot(
                            events, pygame.key.get_pressed()
                        )
                continue
            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_F10:
                    if self.profiler is not None:
                        if self.profiling_active:
                            self._dump_profile()
                            self.profiling_active = False
                        else:
                            self.profiler.enable()
                            self.profiling_active = True
                            print("Profile started (F10 to stop and save).")
                    continue
                if event.key == pygame.K_LEFTBRACKET:
                    nudge_window_scale(0.5, game_data=self.game_data)
                    continue
                if event.key == pygame.K_RIGHTBRACKET:
                    nudge_window_scale(2.0, game_data=self.game_data)
                    continue
                if event.key == pygame.K_f:
                    toggle_fullscreen(game_data=self.game_data)
                    continue
                if self.debug_mode and event.key == pygame.K_o:
                    self.debug_overview = not self.debug_overview

        snapshot = self.input_helper.snapshot(events, pygame.key.get_pressed())
        if self.debug_mode:
            if snapshot.pressed(CommonAction.BACK):
                return self._finalize(ScreenTransition(ScreenID.TITLE)), snapshot
            if snapshot.pressed(CommonAction.START):
                self.paused_manual = not self.paused_manual
                if self.paused_manual:
                    self.pause_selected_index = 0
        else:
            if not (self.paused_manual or self.paused_focus) and (
                snapshot.pressed(CommonAction.BACK) or snapshot.pressed(CommonAction.START)
            ):
                self.paused_manual = True
                self.pause_selected_index = 0
            elif self.paused_manual or self.paused_focus:
                if snapshot.pressed(CommonAction.UP):
                    self.pause_selected_index = (
                        self.pause_selected_index - 1
                    ) % len(self.pause_option_ids)
                if snapshot.pressed(CommonAction.DOWN):
                    self.pause_selected_index = (
                        self.pause_selected_index + 1
                    ) % len(self.pause_option_ids)
                if snapshot.pressed(CommonAction.START):
                    self.paused_manual = False
                    self.paused_focus = False
                elif snapshot.pressed(CommonAction.BACK):
                    return self._finalize(ScreenTransition(ScreenID.TITLE)), snapshot
                elif snapshot.pressed(CommonAction.CONFIRM):
                    transition = self._activate_pause_selection()
                    if transition is not None:
                        return transition, snapshot
        self.pause_mouse_ui_guard.end_frame()
        return None, snapshot

    def _update_world(self, dt: float, input_snapshot: Any) -> None:
        assert self.game_data is not None
        game_data = self.game_data
        state = game_data.state
        groups = game_data.groups
        keys = pygame.key.get_pressed()
        accel_allowed = not (state.game_over or state.game_won)
        player_ref = game_data.player
        mouse_accel_active = (
            accel_allowed
            and player_ref is not None
            and self._is_mouse_accel_active(player_ref)
        )
        accel_active = accel_allowed and (
            input_snapshot.held(CommonAction.ACCEL) or mouse_accel_active
        )
        state.time_accel_active = accel_active
        substeps = SURVIVAL_TIME_ACCEL_SUBSTEPS if accel_active else 1
        sub_dt = min(dt, SURVIVAL_TIME_ACCEL_MAX_SUBSTEP) if accel_active else dt
        if consume_wall_index_dirty():
            game_data.wall_index_dirty = True
        if game_data.wall_index is None or game_data.wall_index_dirty:
            game_data.wall_index = build_wall_index(
                groups.wall_group, cell_size=game_data.cell_size
            )
            game_data.wall_index_dirty = False
        wall_index = game_data.wall_index
        pad_vector = input_snapshot.move_vector

        for _ in range(substeps):
            player_ref = game_data.player
            if player_ref is None:
                break
            car_ref = game_data.car
            steering_pad = self._resolve_steering_pad_input(
                player=player_ref,
                keys=keys,
                pad_vector=pad_vector,
            )
            player_dx, player_dy, car_dx, car_dy = process_player_input(
                keys,
                player_ref,
                car_ref,
                shoes_count=state.shoes_count,
                pad_input=steering_pad,
            )
            if (
                state.timed_message
                and state.timed_message.clear_on_input
                and (player_dx or player_dy or car_dx or car_dy)
            ):
                state.timed_message = None
            update_entities(
                game_data,
                player_dx,
                player_dy,
                car_dx,
                car_dy,
                self.config,
                wall_index=wall_index,
            )
            update_footprints(game_data, self.config)
            step_ms = int(sub_dt * 1000)
            if accel_active:
                step_ms = max(1, step_ms)
            time_scale = 4.0 / max(1, substeps) if accel_active else 1.0
            state.clock.time_scale = time_scale
            step_ms = state.clock.tick(step_ms)
            update_endurance_timer(game_data, step_ms)
            cleanup_survivor_messages(state)
            check_interactions(game_data, self.config)
            if state.game_over or state.game_won:
                break

        player_ref = game_data.player
        if player_ref is None:
            return
        mobile_entities: list[pygame.sprite.Sprite] = []
        if player_ref.alive():
            mobile_entities.append(player_ref)
        car_ref = game_data.car
        if car_ref and car_ref.alive():
            mobile_entities.append(car_ref)
        mobile_entities.extend(
            [zombie for zombie in groups.zombie_group if zombie.alive()]
        )
        mobile_entities.extend(
            [
                survivor
                for survivor in groups.survivor_group
                if survivor.alive()
            ]
        )
        mobile_entities.extend(
            [bot for bot in groups.patrol_bot_group if bot.alive()]
        )
        state.spatial_index.rebuild(mobile_entities)

    def _draw_game_frame(self, current_fps: float) -> None:
        assert self.game_data is not None
        game_data = self.game_data
        state = game_data.state
        player = game_data.player
        if player is None:
            raise ValueError("Player missing from game data")

        car_hint_conf = self.config.get("car_hint", {})
        hint_delay = car_hint_conf.get("delay_ms", CAR_HINT_DELAY_MS_DEFAULT)
        elapsed_ms = state.clock.elapsed_ms
        fuel_progress = state.fuel_progress
        hint_enabled = car_hint_conf.get("enabled", True) and not self.stage.endurance_stage
        hint_target = None
        hint_color = YELLOW
        hint_expires_at = state.hint_expires_at
        hint_target_type = state.hint_target_type
        active_car = game_data.car if game_data.car and game_data.car.alive() else None

        if hint_enabled:
            target_type = _resolve_hint_target_type(
                stage=self.stage,
                fuel_progress=fuel_progress,
                game_data=game_data,
                player_in_car=player.in_car,
                active_car=active_car,
                report_internal_error_once=self._report_internal_error_once,
            )
            if target_type != hint_target_type:
                state.hint_target_type = target_type
                state.hint_expires_at = (
                    elapsed_ms + hint_delay if target_type else 0
                )
                hint_expires_at = state.hint_expires_at

            if target_type and hint_expires_at and elapsed_ms >= hint_expires_at and not player.in_car:
                hint_target_raw = _resolve_hint_target_position(
                    target_type=target_type,
                    game_data=game_data,
                    active_car=active_car,
                    player_pos=(player.x, player.y),
                )
                hint_target = (
                    (int(hint_target_raw[0]), int(hint_target_raw[1]))
                    if hint_target_raw
                    else None
                )

        draw(
            self.render_assets,
            self.screen,
            game_data,
            config=self.config,
            hint_target=hint_target,
            hint_color=hint_color,
            fps=current_fps,
        )
        self._draw_player_time_accel_indicator()
        self._draw_pause_hotspot_hint()
        self._draw_mouse_steering_overlay()
        if self.profiling_active:
            font_settings = get_font_settings()
            font = load_font(font_settings.resource, font_settings.scaled_size(11))
            label = render_text_surface(
                font,
                "PROFILE ON",
                RED,
                line_height_scale=font_settings.line_height_scale,
            )
            self.screen.blit(label, (6, 6))
        present(self.screen)

    def _render_paused_state(self, current_fps: float) -> None:
        assert self.overview_surface is not None
        assert self.game_data is not None
        if self.debug_overview:
            draw_debug_overview(
                self.render_assets,
                self.screen,
                self.overview_surface,
                self.game_data,
                self.config,
                screen_width=self.screen_width,
                screen_height=self.screen_height,
            )
        else:
            draw(
                self.render_assets,
                self.screen,
                self.game_data,
                config=self.config,
                fps=current_fps,
            )
        if self.show_pause_overlay:
            labels = [tr("hud.pause_menu_resume"), tr("hud.pause_menu_title")]
            option_rects = draw_pause_overlay(
                self.screen,
                menu_labels=labels,
                selected_index=self.pause_selected_index,
            )
            targets = [
                ClickTarget(i, rect)
                for i, rect in enumerate(option_rects)
                if i < len(self.pause_option_ids)
            ]
            self.pause_option_click_map.set_targets(targets)
        present(self.screen)

    def _activate_pause_selection(self) -> ScreenTransition | None:
        selected_id = self.pause_option_ids[self.pause_selected_index]
        if selected_id == "resume":
            self.paused_manual = False
            self.paused_focus = False
            return None
        if selected_id == "title":
            return self._finalize(ScreenTransition(ScreenID.TITLE))
        return None

    def _is_game_finished(self, frame_ms: int, current_fps: float) -> bool:
        assert self.game_data is not None
        game_data = self.game_data
        state = game_data.state
        if not (state.game_over or state.game_won):
            return False
        state.clock.time_scale = 1.0
        state.clock.tick(frame_ms)
        if state.game_won:
            record_stage_clear(self.stage.id)
        if state.game_over and not state.game_won:
            if state.game_over_at is None:
                state.game_over_at = state.clock.elapsed_ms
            if (
                state.clock.elapsed_ms - state.game_over_at
                < 1000
            ):
                if self.debug_overview:
                    assert self.overview_surface is not None
                    draw_debug_overview(
                        self.render_assets,
                        self.screen,
                        self.overview_surface,
                        self.game_data,
                        self.config,
                        screen_width=self.screen_width,
                        screen_height=self.screen_height,
                    )
                else:
                    draw(
                        self.render_assets,
                        self.screen,
                        game_data,
                        config=self.config,
                        hint_color=None,
                        fps=current_fps,
                    )
                present(self.screen)
                return False
        return True

    def _report_internal_error_once(self, code: str) -> None:
        if code in self.reported_internal_errors:
            return
        self.reported_internal_errors.add(code)
        print(f"INTERNAL ERROR: {code}")
        schedule_timed_message(
            self.game_data.state,
            tr("hud.internal_error"),
            duration_frames=ms_to_frames(3000),
            clear_on_input=False,
            color=RED,
            now_ms=self.game_data.state.clock.elapsed_ms,
        )

    def _show_loading_still(self) -> None:
        self.screen.fill((0, 0, 0))
        if self.stage.intro_key:
            intro_text = tr(self.stage.intro_key)
            font_settings = get_font_settings()
            font_size = font_settings.scaled_size(GAMEPLAY_FONT_SIZE * 2)
            font = load_font(font_settings.resource, font_size)
            line_height = int(round(font.get_linesize() * font_settings.line_height_scale))
            x = TIMED_MESSAGE_LEFT_X
            y = TIMED_MESSAGE_TOP_Y
            for line in intro_text.splitlines():
                if not line:
                    y += line_height
                    continue
                rendered = font.render(line, False, WHITE)
                self.screen.blit(rendered, (x, y))
                y += line_height
        present(self.screen)
        pygame.event.pump()

    def _resolve_steering_pad_input(
        self,
        *,
        player: Any,
        keys: Any,
        pad_vector: tuple[float, float],
    ) -> tuple[float, float]:
        keyboard_vector = self._read_keyboard_vector(keys)
        keyboard_active = keyboard_vector != (0.0, 0.0)
        pad_active = pad_vector != (0.0, 0.0)
        if keyboard_active or pad_active:
            self.mouse_steering_active = False
            return pad_vector
        mouse_vector = self._read_mouse_steering_vector(player)
        if mouse_vector is None:
            return pad_vector
        return mouse_vector

    @staticmethod
    def _read_keyboard_vector(keys: Any) -> tuple[float, float]:
        dx, dy = 0.0, 0.0
        if keys[pygame.K_w] or keys[pygame.K_UP]:
            dy -= 1.0
        if keys[pygame.K_s] or keys[pygame.K_DOWN]:
            dy += 1.0
        if keys[pygame.K_a] or keys[pygame.K_LEFT]:
            dx -= 1.0
        if keys[pygame.K_d] or keys[pygame.K_RIGHT]:
            dx += 1.0
        return dx, dy

    def _read_mouse_steering_vector(self, player: Any) -> tuple[float, float] | None:
        if self.paused_focus or not pygame.mouse.get_focused():
            self.mouse_steering_active = False
            return None
        self.mouse_cursor_screen_pos = tuple(map(int, pygame.mouse.get_pos()))
        buttons = pygame.mouse.get_pressed(3)
        if not buttons or not buttons[0]:
            self.mouse_steering_active = False
            return None
        assert self.game_data is not None
        player_screen_pos = self.game_data.camera.apply(player).center
        mouse_screen_pos = self.mouse_cursor_screen_pos
        dx = float(mouse_screen_pos[0] - player_screen_pos[0])
        dy = float(mouse_screen_pos[1] - player_screen_pos[1])
        magnitude = math.hypot(dx, dy)
        deadzone = max(2, int(getattr(player, "radius", 4) * _MOUSE_STEERING_DEADZONE_SCALE))
        self.mouse_steering_active = True
        self.mouse_cursor_visible_until_ms = pygame.time.get_ticks() + _MOUSE_CURSOR_PERSIST_MS
        if magnitude <= float(deadzone):
            return 0.0, 0.0
        return dx / magnitude, dy / magnitude

    def _draw_mouse_steering_overlay(self) -> None:
        if not pygame.mouse.get_focused():
            return
        now_ms = pygame.time.get_ticks()
        if not self.mouse_steering_active and now_ms > self.mouse_cursor_visible_until_ms:
            return
        self.mouse_cursor_screen_pos = tuple(map(int, pygame.mouse.get_pos()))
        mx, my = self.mouse_cursor_screen_pos
        overlay = pygame.Surface(self.screen.get_size(), pygame.SRCALPHA)
        if self.mouse_steering_active and pygame.mouse.get_pressed(3)[0]:
            color = (255, 255, 255, 240)
            width = 2
        else:
            color = (255, 255, 255, 220)
            width = 1
        half = 5
        pygame.draw.line(overlay, color, (mx - half, my), (mx + half, my), width=width)
        pygame.draw.line(overlay, color, (mx, my - half), (mx, my + half), width=width)
        self.screen.blit(overlay, (0, 0))

    def _is_mouse_accel_active(self, player: Any) -> bool:
        if self.paused_manual or self.paused_focus or not pygame.mouse.get_focused():
            return False
        buttons = pygame.mouse.get_pressed(3)
        if not buttons or not buttons[0]:
            return False
        mouse_pos = tuple(map(int, pygame.mouse.get_pos()))
        if self._pause_hotspot_kind_at(mouse_pos) is not None:
            # Prefer pause hotspot behavior over mouse-hold acceleration.
            return False
        assert self.game_data is not None
        player_screen_pos = self.game_data.camera.apply(player).center
        dx = float(mouse_pos[0] - player_screen_pos[0])
        dy = float(mouse_pos[1] - player_screen_pos[1])
        distance = math.hypot(dx, dy)
        accel_radius = max(2, int(getattr(player, "radius", 4) * _MOUSE_ACCEL_HOLD_SCALE))
        return distance <= float(accel_radius)

    def _draw_player_time_accel_indicator(self) -> None:
        assert self.game_data is not None
        state = self.game_data.state
        player = self.game_data.player
        if not state.time_accel_active or player is None:
            return
        player_screen_center = self.game_data.camera.apply(player).center
        font_settings = get_font_settings()
        font = load_font(font_settings.resource, font_settings.scaled_size(11))
        label = render_text_surface(
            font,
            ">> 4x",
            WHITE,
            line_height_scale=font_settings.line_height_scale,
        )
        label_rect = label.get_rect(
            center=(int(player_screen_center[0]), int(player_screen_center[1] - 12))
        )
        self.screen.blit(label, label_rect)

    def _compute_present_rect(self) -> pygame.Rect:
        window = pygame.display.get_surface()
        if window is None:
            return pygame.Rect(0, 0, self.screen_width, self.screen_height)
        window_width, window_height = window.get_size()
        logical_width, logical_height = self.screen.get_size()
        if logical_width <= 0 or logical_height <= 0:
            return pygame.Rect(0, 0, window_width, window_height)
        scale_x = window_width / float(logical_width)
        scale_y = window_height / float(logical_height)
        scale = min(scale_x, scale_y)
        present_width = max(1, int(logical_width * scale))
        present_height = max(1, int(logical_height * scale))
        offset_x = (window_width - present_width) // 2
        offset_y = (window_height - present_height) // 2
        return pygame.Rect(offset_x, offset_y, present_width, present_height)

    def _pause_hotspot_kind_at(self, pos: tuple[int, int]) -> str | None:
        present_rect = self._compute_present_rect()
        if not present_rect.collidepoint(pos):
            return None
        local_x = int(pos[0]) - present_rect.left
        local_y = int(pos[1]) - present_rect.top
        local_w = present_rect.width
        local_h = present_rect.height
        tri_size = max(
            8,
            int(
                _PAUSE_HOTSPOT_TRI_SIZE
                * (present_rect.width / max(1, self.screen_width))
            ),
        )
        if local_x + local_y <= tri_size:
            return "corner"
        if (local_w - 1 - local_x) + local_y <= tri_size:
            return "corner"
        if local_x + (local_h - 1 - local_y) <= tri_size:
            return "corner"
        if (local_w - 1 - local_x) + (local_h - 1 - local_y) <= tri_size:
            return "corner"
        return None

    def _draw_pause_hotspot_hint(self) -> None:
        w, h = self.screen.get_size()
        s = _PAUSE_HOTSPOT_TRI_SIZE
        top_left = [(1, 1), (1 + s, 1), (1, 1 + s)]
        top_right = [(w - 2, 1), (w - 2 - s, 1), (w - 2, 1 + s)]
        bottom_left = [(1, h - 2), (1 + s, h - 2), (1, h - 2 - s)]
        bottom_right = [(w - 2, h - 2), (w - 2 - s, h - 2), (w - 2, h - 2 - s)]
        pygame.draw.polygon(self.screen, _PAUSE_HOTSPOT_COLOR, top_left)
        pygame.draw.polygon(self.screen, _PAUSE_HOTSPOT_COLOR, top_right)
        pygame.draw.polygon(self.screen, _PAUSE_HOTSPOT_COLOR, bottom_left)
        pygame.draw.polygon(self.screen, _PAUSE_HOTSPOT_COLOR, bottom_right)

    def _dump_profile(self) -> None:
        if self.profiler is None or self.profiler_output is None:
            return
        try:
            import pstats
        except Exception:
            return
        if self.profiling_active:
            self.profiler.disable()
            self.profiling_active = False
        output_path = self.profiler_output
        self.profiler.dump_stats(output_path)
        summary_path = output_path.with_suffix(".txt")
        with summary_path.open("w", encoding="utf-8") as handle:
            stats = pstats.Stats(self.profiler, stream=handle).sort_stats("tottime")
            stats.print_stats(50)
        print(f"Profile saved to {output_path} and {summary_path}")

    def _set_mouse_hidden(self, hidden: bool) -> None:
        if self.mouse_hidden == hidden:
            return
        pygame.mouse.set_visible(not hidden)
        self.mouse_hidden = hidden

    def _finalize(self, transition: ScreenTransition) -> ScreenTransition:
        self._set_mouse_hidden(False)
        if self.profiling_active:
            self._dump_profile()
        return transition


def gameplay_screen(
    screen: surface.Surface,
    clock: time.Clock,
    config: dict[str, Any],
    fps: int,
    stage: Stage,
    *,
    show_pause_overlay: bool,
    seed: int | None,
    render_assets: "RenderAssets",
    debug_mode: bool = False,
    show_fps: bool = False,
    profiler: "object | None" = None,
    profiler_output: Path | None = None,
) -> ScreenTransition:
    runner = GameplayScreenRunner(
        screen=screen,
        clock=clock,
        config=config,
        fps=fps,
        stage=stage,
        show_pause_overlay=show_pause_overlay,
        seed=seed,
        render_assets=render_assets,
        debug_mode=debug_mode,
        show_fps=show_fps,
        profiler=profiler,
        profiler_output=profiler_output,
    )
    return runner.run()
