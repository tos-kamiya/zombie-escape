from __future__ import annotations

import os
from pathlib import Path
from typing import TYPE_CHECKING, Any

import pygame
from pygame import surface, time

from ..colors import LIGHT_GRAY, RED, WHITE, YELLOW
from ..font_utils import load_font, render_text_unscaled
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
    schedule_timed_message,
    place_flashlights,
    place_fuel_can,
    place_shoes,
    process_player_input,
    setup_player_and_cars,
    spawn_initial_zombies,
    spawn_survivors,
    sync_ambient_palette_with_flashlights,
    update_entities,
    update_footprints,
    update_endurance_timer,
)
from ..gameplay.state import frames_to_ms, ms_to_frames
from ..gameplay.constants import INTRO_MESSAGE_DISPLAY_FRAMES
from ..input_utils import (
    CONTROLLER_BUTTON_DOWN,
    CONTROLLER_DEVICE_ADDED,
    CONTROLLER_DEVICE_REMOVED,
    init_first_controller,
    init_first_joystick,
    is_accel_active,
    is_select_event,
    is_start_event,
    read_gamepad_move,
)
from ..gameplay.spawn import _alive_waiting_cars
from ..world_grid import build_wall_index
from ..localization import get_font_settings, translate as tr
from ..models import Stage
from ..render import (
    draw,
    draw_debug_overview,
    draw_pause_overlay,
    prewarm_fog_overlays,
    show_message_wrapped,
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
    """Main gameplay loop that returns the next screen transition."""

    screen_width = screen.get_width()
    screen_height = screen.get_height()
    mouse_hidden = False
    use_busy_loop = os.environ.get("ZOMBIE_ESCAPE_BUSY_LOOP") == "1"
    profiling_active = False

    def _dump_profile() -> None:
        nonlocal profiling_active
        if profiler is None or profiler_output is None:
            return
        try:
            import pstats
        except Exception:
            return
        if profiling_active:
            profiler.disable()
            profiling_active = False
        output_path = profiler_output
        profiler.dump_stats(output_path)
        summary_path = output_path.with_suffix(".txt")
        with summary_path.open("w", encoding="utf-8") as handle:
            stats = pstats.Stats(profiler, stream=handle).sort_stats("tottime")
            stats.print_stats(50)
        print(f"Profile saved to {output_path} and {summary_path}")

    def _set_mouse_hidden(hidden: bool) -> None:
        nonlocal mouse_hidden
        if mouse_hidden == hidden:
            return
        pygame.mouse.set_visible(not hidden)
        mouse_hidden = hidden

    def _finalize(transition: ScreenTransition) -> ScreenTransition:
        _set_mouse_hidden(False)
        if profiling_active:
            _dump_profile()
        return transition

    def _show_loading_still() -> None:
        screen.fill((0, 0, 0))
        if stage.intro_key:
            intro_text = tr(stage.intro_key)
            font_settings = get_font_settings()
            font_size = font_settings.scaled_size(GAMEPLAY_FONT_SIZE * 2)
            font = load_font(font_settings.resource, font_size)
            line_height = int(
                round(font.get_linesize() * font_settings.line_height_scale)
            )
            x = TIMED_MESSAGE_LEFT_X
            y = TIMED_MESSAGE_TOP_Y
            for line in intro_text.splitlines():
                if not line:
                    y += line_height
                    continue
                surface = font.render(line, False, WHITE)
                screen.blit(surface, (x, y))
                y += line_height
        present(screen)
        pygame.event.pump()

    seed_value = seed if seed is not None else generate_seed()
    applied_seed = seed_rng(seed_value)

    loading_started_ms = pygame.time.get_ticks()
    _show_loading_still()

    game_data = initialize_game_state(config, stage)
    game_data.state.seed = applied_seed
    game_data.state.debug_mode = debug_mode
    game_data.state.show_fps = show_fps
    if debug_mode and stage.endurance_stage:
        goal_ms = max(0, stage.endurance_goal_ms)
        if goal_ms > 0:
            remaining = 3 * 60 * 1000  # 3 minutes in ms
            game_data.state.endurance_elapsed_ms = max(0, goal_ms - remaining)
            game_data.state.dawn_ready = False
            game_data.state.dawn_prompt_at = None
            game_data.state.dawn_carbonized = False
    global _SHARED_FOG_CACHE
    if _SHARED_FOG_CACHE is None:
        prewarm_fog_overlays(
            game_data.fog,
            render_assets,
            stage=stage,
        )
        _SHARED_FOG_CACHE = game_data.fog
    else:
        game_data.fog = _SHARED_FOG_CACHE
    if stage.intro_key and game_data.state.timed_message:
        loading_elapsed_ms = max(0, pygame.time.get_ticks() - loading_started_ms)
        remaining_ms = max(
            0, frames_to_ms(INTRO_MESSAGE_DISPLAY_FRAMES) - loading_elapsed_ms
        )
        schedule_timed_message(
            game_data.state,
            tr(stage.intro_key),
            duration_frames=max(0, ms_to_frames(remaining_ms)),
            clear_on_input=True,
            color=LIGHT_GRAY,
            align="left",
            now_ms=game_data.state.elapsed_play_ms,
        )
    paused_manual = False
    paused_focus = False
    ignore_focus_loss_until = 0
    debug_overview = False
    controller = init_first_controller()
    joystick = init_first_joystick() if controller is None else None
    _set_mouse_hidden(pygame.mouse.get_focused())

    try:
        layout_data = generate_level_from_blueprint(game_data, config)
    except MapGenerationError:
        # If generation fails after retries, show error and back to title
        screen.fill((0, 0, 0))
        show_message_wrapped(
            screen,
            tr("errors.map_generation_failed"),
            16,
            RED,
            (screen_width // 2, screen_height // 2),
            max_width=screen_width - 40,
        )
        present(screen)
        pygame.time.delay(3000)
        return _finalize(ScreenTransition(ScreenID.TITLE))

    sync_ambient_palette_with_flashlights(game_data, force=True)
    initial_waiting = max(0, stage.waiting_car_target_count)
    player, waiting_cars = setup_player_and_cars(
        game_data, layout_data, car_count=initial_waiting
    )
    game_data.player = player
    game_data.waiting_cars = waiting_cars
    game_data.car = None
    # Only top up if initial placement spawned fewer than the intended baseline (shouldn't happen)
    maintain_waiting_car_supply(game_data, minimum=stage.waiting_car_target_count)
    apply_passenger_speed_penalty(game_data)

    spawn_survivors(game_data, layout_data)

    occupied_centers: set[tuple[int, int]] = set()
    cell_size = game_data.cell_size
    if stage.requires_fuel:
        fuel_spawn_count = stage.fuel_spawn_count
        if stage.endurance_stage:
            fuel_spawn_count = 0
        fuel_can = place_fuel_can(
            layout_data["fuel_cells"] or layout_data["walkable_cells"],
            cell_size,
            player,
            cars=game_data.waiting_cars,
            reserved_centers=occupied_centers,
            count=fuel_spawn_count,
        )
        if fuel_can:
            game_data.fuel = fuel_can
            game_data.groups.all_sprites.add(fuel_can, layer=1)
            occupied_centers.add(fuel_can.rect.center)
    flashlight_count = stage.initial_flashlight_count
    flashlights = place_flashlights(
        layout_data["flashlight_cells"] or layout_data["walkable_cells"],
        cell_size,
        player,
        cars=game_data.waiting_cars,
        reserved_centers=occupied_centers,
        count=max(0, flashlight_count),
    )
    game_data.flashlights = flashlights
    game_data.groups.all_sprites.add(flashlights, layer=1)
    for flashlight in flashlights:
        occupied_centers.add(flashlight.rect.center)

    shoes_count = stage.initial_shoes_count
    shoes_list = place_shoes(
        layout_data["shoes_cells"] or layout_data["walkable_cells"],
        cell_size,
        player,
        cars=game_data.waiting_cars,
        reserved_centers=occupied_centers,
        count=max(0, shoes_count),
    )
    game_data.shoes = shoes_list
    game_data.groups.all_sprites.add(shoes_list, layer=1)

    spawn_initial_zombies(game_data, player, layout_data, config)
    update_footprints(game_data, config)
    level_rect = game_data.layout.field_rect
    overview_surface = pygame.Surface((level_rect.width, level_rect.height))
    while True:
        frame_ms = clock.tick_busy_loop(fps) if use_busy_loop else clock.tick(fps)
        dt = frame_ms / 1000.0
        current_fps = clock.get_fps()
        if game_data.state.game_over or game_data.state.game_won:
            if game_data.state.game_won:
                record_stage_clear(stage.id)
            if game_data.state.game_over and not game_data.state.game_won:
                if game_data.state.game_over_at is None:
                    game_data.state.game_over_at = pygame.time.get_ticks()
                if pygame.time.get_ticks() - game_data.state.game_over_at < 1000:
                    draw(
                        render_assets,
                        screen,
                        game_data,
                        config=config,
                        hint_color=None,
                        fps=current_fps,
                    )
                    present(screen)
                    continue
            return _finalize(
                ScreenTransition(
                    ScreenID.GAME_OVER,
                    stage=stage,
                    game_data=game_data,
                    config=config,
                )
            )

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                return _finalize(ScreenTransition(ScreenID.EXIT))
            if event.type in (pygame.WINDOWSIZECHANGED, pygame.VIDEORESIZE):
                sync_window_size(event, game_data=game_data)
                continue
            if event.type == pygame.WINDOWFOCUSLOST:
                now = pygame.time.get_ticks()
                if now >= ignore_focus_loss_until:
                    paused_focus = True
            if event.type == pygame.WINDOWFOCUSGAINED:
                paused_focus = False
            if event.type == pygame.MOUSEBUTTONDOWN:
                paused_focus = False
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
                if event.key == pygame.K_F10:
                    if profiler is not None:
                        if profiling_active:
                            _dump_profile()
                        else:
                            profiler.enable()
                            profiling_active = True
                            print("Profile started (F10 to stop and save).")
                    continue
                if event.key == pygame.K_LEFTBRACKET:
                    nudge_window_scale(0.5, game_data=game_data)
                    continue
                if event.key == pygame.K_RIGHTBRACKET:
                    nudge_window_scale(2.0, game_data=game_data)
                    continue
                if event.key == pygame.K_f:
                    toggle_fullscreen(game_data=game_data)
                    continue
                if event.key == pygame.K_s and (
                    pygame.key.get_mods() & pygame.KMOD_CTRL
                ):
                    state_snapshot = {
                        k: v
                        for k, v in vars(game_data.state).items()
                        if k != "footprints"
                    }
                    print("STATE DEBUG:", state_snapshot)
                    continue
                if debug_mode:
                    if event.key == pygame.K_ESCAPE:
                        return ScreenTransition(ScreenID.TITLE)
                    if event.key == pygame.K_p:
                        paused_manual = not paused_manual
                    if event.key == pygame.K_o:
                        debug_overview = not debug_overview
                    continue
                if paused_manual:
                    if event.key == pygame.K_ESCAPE:
                        return _finalize(ScreenTransition(ScreenID.TITLE))
                    if event.key == pygame.K_p:
                        paused_manual = False
                    continue
                if event.key in (pygame.K_ESCAPE, pygame.K_p):
                    paused_manual = True
                    continue
            if event.type == pygame.JOYBUTTONDOWN or (
                CONTROLLER_BUTTON_DOWN is not None
                and event.type == CONTROLLER_BUTTON_DOWN
            ):
                if debug_mode:
                    if is_select_event(event):
                        return _finalize(ScreenTransition(ScreenID.TITLE))
                    if is_start_event(event):
                        paused_manual = not paused_manual
                    continue
                if paused_manual:
                    if is_select_event(event):
                        return _finalize(ScreenTransition(ScreenID.TITLE))
                    if is_start_event(event):
                        paused_manual = False
                    continue
                if is_select_event(event) or is_start_event(event):
                    paused_manual = True
                    continue

        _set_mouse_hidden(pygame.mouse.get_focused())

        paused = paused_manual or paused_focus
        if paused:
            if debug_overview:
                draw_debug_overview(
                    render_assets,
                    screen,
                    overview_surface,
                    game_data,
                    config,
                    screen_width=screen_width,
                    screen_height=screen_height,
                )
            else:
                draw(
                    render_assets,
                    screen,
                    game_data,
                    config=config,
                    fps=current_fps,
                )
            if show_pause_overlay:
                draw_pause_overlay(screen)
            present(screen)
            continue

        keys = pygame.key.get_pressed()
        accel_allowed = not (game_data.state.game_over or game_data.state.game_won)
        accel_active = accel_allowed and is_accel_active(keys, controller, joystick)
        game_data.state.time_accel_active = accel_active
        substeps = SURVIVAL_TIME_ACCEL_SUBSTEPS if accel_active else 1
        sub_dt = min(dt, SURVIVAL_TIME_ACCEL_MAX_SUBSTEP) if accel_active else dt
        if game_data.wall_index is None or game_data.wall_index_dirty:
            game_data.wall_index = build_wall_index(
                game_data.groups.wall_group, cell_size=game_data.cell_size
            )
            game_data.wall_index_dirty = False
        wall_index = game_data.wall_index
        for _ in range(substeps):
            player_ref = game_data.player
            if player_ref is None:
                break
            car_ref = game_data.car
            pad_vector = read_gamepad_move(controller, joystick)
            player_dx, player_dy, car_dx, car_dy = process_player_input(
                keys,
                player_ref,
                car_ref,
                shoes_count=game_data.state.shoes_count,
                pad_input=pad_vector,
            )
            if (
                game_data.state.timed_message
                and game_data.state.timed_message.clear_on_input
                and (player_dx or player_dy or car_dx or car_dy)
            ):
                game_data.state.timed_message = None
            update_entities(
                game_data,
                player_dx,
                player_dy,
                car_dx,
                car_dy,
                config,
                wall_index=wall_index,
            )
            update_footprints(game_data, config)
            step_ms = int(sub_dt * 1000)
            if accel_active:
                step_ms = max(1, step_ms)
            game_data.state.elapsed_play_ms += step_ms
            update_endurance_timer(game_data, step_ms)
            cleanup_survivor_messages(game_data.state)
            check_interactions(game_data, config)
            if game_data.state.game_over or game_data.state.game_won:
                break

        player_ref = game_data.player
        if player_ref is not None:
            mobile_entities: list[pygame.sprite.Sprite] = []
            if player_ref.alive():
                mobile_entities.append(player_ref)
            car_ref = game_data.car
            if car_ref and car_ref.alive():
                mobile_entities.append(car_ref)
            mobile_entities.extend(
                [zombie for zombie in game_data.groups.zombie_group if zombie.alive()]
            )
            mobile_entities.extend(
                [
                    survivor
                    for survivor in game_data.groups.survivor_group
                    if survivor.alive()
                ]
            )
            game_data.state.spatial_index.rebuild(mobile_entities)

        player = game_data.player
        if player is None:
            raise ValueError("Player missing from game data")

        if debug_overview:
            draw_debug_overview(
                render_assets,
                screen,
                overview_surface,
                game_data,
                config,
                screen_width=screen_width,
                screen_height=screen_height,
            )
            present(screen)
            continue

        car_hint_conf = config.get("car_hint", {})
        hint_delay = car_hint_conf.get("delay_ms", CAR_HINT_DELAY_MS_DEFAULT)
        elapsed_ms = game_data.state.elapsed_play_ms
        has_fuel = game_data.state.has_fuel
        hint_enabled = car_hint_conf.get("enabled", True) and not stage.endurance_stage
        hint_target = None
        hint_color = YELLOW
        hint_expires_at = game_data.state.hint_expires_at
        hint_target_type = game_data.state.hint_target_type

        active_car = game_data.car if game_data.car and game_data.car.alive() else None
        if hint_enabled:
            if not has_fuel and game_data.fuel and game_data.fuel.alive():
                target_type = "fuel"
            elif not player.in_car and (active_car or _alive_waiting_cars(game_data)):
                target_type = "car"
            else:
                target_type = None

            if target_type != hint_target_type:
                game_data.state.hint_target_type = target_type
                game_data.state.hint_expires_at = (
                    elapsed_ms + hint_delay if target_type else 0
                )
                hint_expires_at = game_data.state.hint_expires_at
                hint_target_type = target_type

            if (
                target_type
                and hint_expires_at
                and elapsed_ms >= hint_expires_at
                and not player.in_car
            ):
                if target_type == "fuel" and game_data.fuel and game_data.fuel.alive():
                    hint_target = game_data.fuel.rect.center
                elif target_type == "car":
                    if active_car:
                        hint_target = active_car.rect.center
                    else:
                        waiting_target = nearest_waiting_car(
                            game_data, (player.x, player.y)
                        )
                        if waiting_target:
                            hint_target = waiting_target.rect.center

        draw(
            render_assets,
            screen,
            game_data,
            config=config,
            hint_target=hint_target,
            hint_color=hint_color,
            fps=current_fps,
        )
        if profiling_active:
            font_settings = get_font_settings()
            font = load_font(font_settings.resource, font_settings.scaled_size(11))
            label = render_text_unscaled(font, "PROFILE ON", RED)
            screen.blit(label, (6, 6))
        present(screen)

    # Should not reach here, but return to title if it happens
    return _finalize(ScreenTransition(ScreenID.TITLE))
