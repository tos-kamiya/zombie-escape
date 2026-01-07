from __future__ import annotations

from typing import TYPE_CHECKING, Any

import pygame
from pygame import surface, time

from ..colors import LIGHT_GRAY, RED, WHITE, YELLOW
from ..gameplay_constants import (
    CAR_HINT_DELAY_MS_DEFAULT,
    DEFAULT_FLASHLIGHT_SPAWN_COUNT,
    SURVIVOR_STAGE_WAITING_CAR_COUNT,
    SURVIVAL_TIME_ACCEL_SUBSTEPS,
    SURVIVAL_TIME_ACCEL_MAX_SUBSTEP,
)
from ..gameplay import logic
from ..localization import translate as tr
from ..models import Stage
from ..render import draw, prewarm_fog_overlays, show_message
from ..rng import generate_seed, seed_rng
from ..progress import record_stage_clear
from ..screens import ScreenID, ScreenTransition, present

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

    game_data = logic.initialize_game_state(config, stage)
    game_data.state.seed = applied_seed
    game_data.state.debug_mode = debug_mode
    if debug_mode and stage.survival_stage:
        goal_ms = max(0, stage.survival_goal_ms)
        if goal_ms > 0:
            remaining = 3 * 60 * 1000  # 3 minutes in ms
            game_data.state.survival_elapsed_ms = max(0, goal_ms - remaining)
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
    last_fov_target = None

    layout_data = logic.generate_level_from_blueprint(game_data, config)
    logic.sync_ambient_palette_with_flashlights(game_data, force=True)
    initial_waiting = (
        SURVIVOR_STAGE_WAITING_CAR_COUNT if stage.rescue_stage else 1
    )
    player, waiting_cars = logic.setup_player_and_cars(
        game_data, layout_data, car_count=initial_waiting
    )
    game_data.player = player
    game_data.waiting_cars = waiting_cars
    game_data.car = None
    # Only top up if initial placement spawned fewer than the intended baseline (shouldn't happen)
    logic.maintain_waiting_car_supply(
        game_data, minimum=logic.waiting_car_target_count(stage)
    )
    logic.apply_passenger_speed_penalty(game_data)

    if stage.rescue_stage:
        logic.spawn_survivors(game_data, layout_data)

    if stage.requires_fuel:
        fuel_spawn_count = getattr(stage, "fuel_spawn_count", 1)
        fuel_can = logic.place_fuel_can(
            layout_data["walkable_cells"],
            player,
            cars=game_data.waiting_cars,
            count=fuel_spawn_count,
        )
        if fuel_can:
            game_data.fuel = fuel_can
            game_data.groups.all_sprites.add(fuel_can, layer=1)
    flashlights = logic.place_flashlights(
        layout_data["walkable_cells"],
        player,
        cars=game_data.waiting_cars,
        count=max(1, DEFAULT_FLASHLIGHT_SPAWN_COUNT),
    )
    game_data.flashlights = flashlights
    game_data.groups.all_sprites.add(flashlights, layer=1)

    if stage.companion_stage:
        companion = logic.place_companion(
            layout_data["walkable_cells"], player, cars=game_data.waiting_cars
        )
        if companion:
            game_data.companion = companion
            game_data.groups.all_sprites.add(companion, layer=2)

    logic.spawn_initial_zombies(game_data, player, layout_data, config)
    logic.update_footprints(game_data, config)
    last_fov_target = player

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
                        last_fov_target,
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
            if event.type == pygame.WINDOWFOCUSLOST:
                paused_focus = True
            if event.type == pygame.MOUSEBUTTONDOWN:
                paused_focus = False
                paused_manual = False
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
                if event.key == pygame.K_ESCAPE:
                    return ScreenTransition(ScreenID.TITLE)
                if event.key == pygame.K_p:
                    paused_manual = not paused_manual

        paused = paused_manual or paused_focus
        if paused:
            draw(
                render_assets,
                screen,
                game_data,
                last_fov_target,
                config=config,
                do_flip=not show_pause_overlay,
                present_fn=present,
            )
            if show_pause_overlay:
                overlay = pygame.Surface((screen_width, screen_height), pygame.SRCALPHA)
                overlay.fill((0, 0, 0, 150))
                pygame.draw.circle(
                    overlay,
                    LIGHT_GRAY,
                    (screen_width // 2, screen_height // 2),
                    35,
                    width=3,
                )
                bar_width = 8
                bar_height = 30
                gap = 9
                cx, cy = screen_width // 2, screen_height // 2
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
                    (screen_width // 2, screen_height // 2 + 24),
                )
                show_message(
                    screen,
                    tr("hud.resume_hint"),
                    18,
                    LIGHT_GRAY,
                    (screen_width // 2, screen_height // 2 + 70),
                )
                present(screen)
            continue

        keys = pygame.key.get_pressed()
        accel_allowed = not (
            game_data.state.game_over or game_data.state.game_won
        )
        accel_active = accel_allowed and (
            keys[pygame.K_LSHIFT] or keys[pygame.K_RSHIFT]
        )
        game_data.state.time_accel_active = accel_active
        substeps = SURVIVAL_TIME_ACCEL_SUBSTEPS if accel_active else 1
        sub_dt = (
            min(dt, SURVIVAL_TIME_ACCEL_MAX_SUBSTEP) if accel_active else dt
        )
        frame_fov_target = None
        for _ in range(substeps):
            player_ref = game_data.player
            if player_ref is None:
                break
            car_ref = game_data.car
            player_dx, player_dy, car_dx, car_dy = logic.process_player_input(
                keys, player_ref, car_ref
            )
            logic.update_entities(
                game_data, player_dx, player_dy, car_dx, car_dy, config
            )
            logic.update_footprints(game_data, config)
            step_ms = int(sub_dt * 1000)
            if accel_active:
                step_ms = max(1, step_ms)
            game_data.state.elapsed_play_ms += step_ms
            logic.update_survival_timer(game_data, step_ms)
            logic.cleanup_survivor_messages(game_data.state)
            sub_fov_target = logic.check_interactions(game_data, config)
            if sub_fov_target:
                frame_fov_target = sub_fov_target
            if game_data.state.game_over or game_data.state.game_won:
                break

        if frame_fov_target:
            last_fov_target = frame_fov_target
        else:
            frame_fov_target = last_fov_target

        player = game_data.player
        if player is None:
            raise ValueError("Player missing from game data")

        car_hint_conf = config.get("car_hint", {})
        hint_delay = car_hint_conf.get("delay_ms", CAR_HINT_DELAY_MS_DEFAULT)
        elapsed_ms = game_data.state.elapsed_play_ms
        has_fuel = game_data.state.has_fuel
        hint_enabled = car_hint_conf.get("enabled", True) and not stage.survival_stage
        hint_target = None
        hint_color = YELLOW
        hint_expires_at = game_data.state.hint_expires_at
        hint_target_type = game_data.state.hint_target_type

        active_car = game_data.car if game_data.car and game_data.car.alive() else None
        if hint_enabled:
            if not has_fuel and game_data.fuel and game_data.fuel.alive():
                target_type = "fuel"
            elif not player.in_car and (
                active_car or logic.alive_waiting_cars(game_data)
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
                        waiting_target = logic.nearest_waiting_car(
                            game_data, (player.x, player.y)
                        )
                        if waiting_target:
                            hint_target = waiting_target.rect.center

        draw(
            render_assets,
            screen,
            game_data,
            frame_fov_target,
            config=config,
            hint_target=hint_target,
            hint_color=hint_color,
            present_fn=present,
        )

    # Should not reach here, but return to title if it happens
    return ScreenTransition(ScreenID.TITLE)
