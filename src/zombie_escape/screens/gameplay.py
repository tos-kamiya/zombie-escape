from __future__ import annotations

from typing import TYPE_CHECKING, Any

import pygame
from pygame import surface, time

from ..colors import LIGHT_GRAY, RED, WHITE, YELLOW
from ..gameplay_constants import (
    CAR_HINT_DELAY_MS_DEFAULT,
    SURVIVAL_TIME_ACCEL_SUBSTEPS,
    SURVIVAL_TIME_ACCEL_MAX_SUBSTEP,
)
from ..gameplay import (
    apply_passenger_speed_penalty,
    check_interactions,
    cleanup_survivor_messages,
    generate_level_from_blueprint,
    initialize_game_state,
    maintain_waiting_car_supply,
    nearest_waiting_car,
    place_flashlights,
    place_fuel_can,
    process_player_input,
    setup_player_and_cars,
    spawn_initial_zombies,
    spawn_survivors,
    sync_ambient_palette_with_flashlights,
    update_entities,
    update_footprints,
    update_endurance_timer,
)
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
from ..localization import translate as tr
from ..models import Stage
from ..render import draw, prewarm_fog_overlays, show_message
from ..rng import generate_seed, seed_rng
from ..progress import record_stage_clear
from ..screens import (
    ScreenID,
    ScreenTransition,
    present,
    sync_window_size,
)

if TYPE_CHECKING:
    from ..render import RenderAssets


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
) -> ScreenTransition:
    """Main gameplay loop that returns the next screen transition."""

    screen_width = screen.get_width()
    screen_height = screen.get_height()

    seed_value = seed if seed is not None else generate_seed()
    applied_seed = seed_rng(seed_value)

    game_data = initialize_game_state(config, stage)
    game_data.state.seed = applied_seed
    game_data.state.debug_mode = debug_mode
    if debug_mode and stage.endurance_stage:
        goal_ms = max(0, stage.endurance_goal_ms)
        if goal_ms > 0:
            remaining = 3 * 60 * 1000  # 3 minutes in ms
            game_data.state.endurance_elapsed_ms = max(0, goal_ms - remaining)
            game_data.state.dawn_ready = False
            game_data.state.dawn_prompt_at = None
            game_data.state.dawn_carbonized = False
    prewarm_fog_overlays(
        game_data.fog,
        render_assets,
        stage=stage,
    )
    paused_manual = False
    paused_focus = False
    ignore_focus_loss_until = 0
    controller = init_first_controller()
    joystick = init_first_joystick() if controller is None else None

    layout_data = generate_level_from_blueprint(game_data, config)
    sync_ambient_palette_with_flashlights(game_data, force=True)
    initial_waiting = max(0, stage.waiting_car_target_count)
    player, waiting_cars = setup_player_and_cars(
        game_data, layout_data, car_count=initial_waiting
    )
    game_data.player = player
    game_data.waiting_cars = waiting_cars
    game_data.car = None
    # Only top up if initial placement spawned fewer than the intended baseline (shouldn't happen)
    maintain_waiting_car_supply(
        game_data, minimum=stage.waiting_car_target_count
    )
    apply_passenger_speed_penalty(game_data)

    spawn_survivors(game_data, layout_data)

    if stage.requires_fuel:
        fuel_spawn_count = stage.fuel_spawn_count
        fuel_can = place_fuel_can(
            layout_data["walkable_cells"],
            player,
            cars=game_data.waiting_cars,
            count=fuel_spawn_count,
        )
        if fuel_can:
            game_data.fuel = fuel_can
            game_data.groups.all_sprites.add(fuel_can, layer=1)
    flashlight_count = stage.initial_flashlight_count
    flashlights = place_flashlights(
        layout_data["walkable_cells"],
        player,
        cars=game_data.waiting_cars,
        count=max(0, flashlight_count),
    )
    game_data.flashlights = flashlights
    game_data.groups.all_sprites.add(flashlights, layer=1)

    spawn_initial_zombies(game_data, player, layout_data, config)
    update_footprints(game_data, config)
    while True:
        dt = clock.tick(fps) / 1000.0
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
                        present_fn=present,
                    )
                    if game_data.state.game_over_message:
                        show_message(
                            screen,
                            game_data.state.game_over_message,
                            18,
                            RED,
                            (screen_width // 2, screen_height // 2 - 24),
                        )
                    present(screen)
                    continue
            return ScreenTransition(
                ScreenID.GAME_OVER,
                stage=stage,
                game_data=game_data,
                config=config,
            )

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                return ScreenTransition(ScreenID.EXIT)
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
                    continue
                if paused_manual:
                    if event.key == pygame.K_ESCAPE:
                        return ScreenTransition(ScreenID.TITLE)
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
                        return ScreenTransition(ScreenID.TITLE)
                    if is_start_event(event):
                        paused_manual = not paused_manual
                    continue
                if paused_manual:
                    if is_select_event(event):
                        return ScreenTransition(ScreenID.TITLE)
                    if is_start_event(event):
                        paused_manual = False
                    continue
                if is_select_event(event) or is_start_event(event):
                    paused_manual = True
                    continue

        paused = paused_manual or paused_focus
        if paused:
            draw(
                render_assets,
                screen,
                game_data,
                config=config,
                do_flip=not show_pause_overlay,
                present_fn=present,
            )
            if show_pause_overlay:
                overlay = pygame.Surface((screen_width, screen_height), pygame.SRCALPHA)
                overlay.fill((0, 0, 0, 150))
                pause_radius = 53
                cx = screen_width // 2
                cy = screen_height // 2 - 18
                pygame.draw.circle(
                    overlay,
                    LIGHT_GRAY,
                    (cx, cy),
                    pause_radius,
                    width=3,
                )
                bar_width = 10
                bar_height = 38
                gap = 12
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
                show_message(
                    screen,
                    tr("hud.paused"),
                    18,
                    WHITE,
                    (screen_width // 2, 28),
                )
                show_message(
                    screen,
                    tr("hud.pause_hint"),
                    16,
                    LIGHT_GRAY,
                    (screen_width // 2, screen_height // 2 + 70),
                )
                present(screen)
            continue

        keys = pygame.key.get_pressed()
        accel_allowed = not (
            game_data.state.game_over or game_data.state.game_won
        )
        accel_active = accel_allowed and is_accel_active(
            keys, controller, joystick
        )
        game_data.state.time_accel_active = accel_active
        substeps = SURVIVAL_TIME_ACCEL_SUBSTEPS if accel_active else 1
        sub_dt = (
            min(dt, SURVIVAL_TIME_ACCEL_MAX_SUBSTEP) if accel_active else dt
        )
        wall_index = build_wall_index(
            game_data.groups.wall_group, cell_size=game_data.cell_size
        )
        for _ in range(substeps):
            player_ref = game_data.player
            if player_ref is None:
                break
            car_ref = game_data.car
            pad_vector = read_gamepad_move(controller, joystick)
            player_dx, player_dy, car_dx, car_dy = process_player_input(
                keys, player_ref, car_ref, pad_input=pad_vector
            )
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

        player = game_data.player
        if player is None:
            raise ValueError("Player missing from game data")

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
            elif not player.in_car and (
                active_car or _alive_waiting_cars(game_data)
            ):
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
            present_fn=present,
        )

    # Should not reach here, but return to title if it happens
    return ScreenTransition(ScreenID.TITLE)
