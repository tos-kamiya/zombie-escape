from __future__ import annotations

from typing import Any

import pygame
from pygame import surface

from ..colors import YELLOW, get_environment_palette
from ..models import FuelProgress, GameData
from ..render_assets import RenderAssets
from .entity_layer import _draw_entities, _draw_lineformer_train_markers
from .fog import _draw_fog_of_war, prewarm_fog_overlays
from .fx import _draw_decay_fx, _draw_fade_in_overlay, _draw_falling_fx
from .hud import (
    _build_objective_lines,
    _draw_endurance_timer,
    _draw_hint_indicator,
    _draw_inventory_icons,
    _draw_objective,
    _draw_status_bar,
    _draw_survivor_messages,
    _draw_timed_message,
    _draw_time_accel_indicator,
)
from .shadows import (
    _draw_wall_shadows,
    _get_shadow_layer,
    draw_entity_shadows_by_mode,
)
from .text_overlay import (
    blit_message,
    blit_message_wrapped,
    blit_text_wrapped,
    draw_pause_overlay,
    wrap_text,
)
from .world_tiles import _draw_footprints, _draw_play_area

__all__ = [
    "blit_message",
    "blit_message_wrapped",
    "blit_text_wrapped",
    "draw",
    "draw_pause_overlay",
    "prewarm_fog_overlays",
    "wrap_text",
]


def draw(
    assets: RenderAssets,
    screen: surface.Surface,
    game_data: GameData,
    *,
    config: dict[str, Any],
    hint_target: tuple[int, int] | None = None,
    contact_hint_targets: list[tuple[str, tuple[int, int]]] | None = None,
    hint_color: tuple[int, int, int] | None = None,
    fps: float | None = None,
) -> None:
    hint_color = hint_color or YELLOW
    state = game_data.state
    player = game_data.player
    if player is None:
        raise ValueError("draw requires an active player on game_data")

    camera = game_data.camera
    stage = game_data.stage
    outside_cells = game_data.layout.outside_cells
    all_sprites = game_data.groups.all_sprites
    has_fuel = state.fuel_progress == FuelProgress.FULL_CAN
    has_empty_fuel_can = state.fuel_progress == FuelProgress.EMPTY_CAN
    flashlight_count = state.flashlight_count
    active_car = game_data.car if game_data.car and game_data.car.alive() else None
    if player.in_car and game_data.car and game_data.car.alive():
        fov_target = game_data.car
    else:
        fov_target = player

    palette = get_environment_palette(state.ambient_palette_key)
    screen.fill(palette.outside)

    _draw_play_area(
        screen,
        camera.apply_rect,
        pygame.Rect(
            -camera.camera.x,
            -camera.camera.y,
            assets.screen_width,
            assets.screen_height,
        ),
        assets,
        palette,
        game_data.layout.field_rect,
        outside_cells,
        game_data.layout.fall_spawn_cells,
        game_data.layout.pitfall_cells,
        game_data.layout.fire_floor_cells,
        game_data.layout.metal_floor_cells,
        game_data.layout.puddle_cells,
        game_data.layout.moving_floor_cells,
        state.electrified_cells,
        game_data.cell_size,
        elapsed_ms=int(state.clock.elapsed_ms),
    )
    shadows_enabled = config.get("visual", {}).get("shadows", {}).get("enabled", True)
    if shadows_enabled:
        dawn_shadow_mode = bool(stage and stage.endurance_stage and state.dawn_ready)
        lsp = (
            None
            if dawn_shadow_mode
            else (fov_target.rect.center if fov_target else None)
        )
        light_source_pos: tuple[float, float] | None = (
            (float(lsp[0]), float(lsp[1])) if lsp is not None else None
        )
        shadow_layer = _get_shadow_layer(screen.get_size())
        shadow_layer.fill((0, 0, 0, 0))
        drew_shadow = _draw_wall_shadows(
            shadow_layer,
            camera.apply_rect,
            wall_cells=game_data.layout.wall_cells,
            steel_beam_cells=game_data.layout.steel_beam_cells,
            outer_wall_cells=game_data.layout.outer_wall_cells,
            cell_size=game_data.cell_size,
            light_source_pos=light_source_pos,
        )
        drew_shadow |= draw_entity_shadows_by_mode(
            shadow_layer,
            camera.apply_rect,
            all_sprites,
            dawn_shadow_mode=dawn_shadow_mode,
            light_source_pos=light_source_pos,
            outside_cells=outside_cells,
            cell_size=game_data.cell_size,
            flashlight_count=flashlight_count,
        )
        if drew_shadow:
            screen.blit(shadow_layer, (0, 0))
    _draw_footprints(
        screen,
        camera.apply_rect,
        assets,
        state.footprints,
        config=config,
        now_ms=state.clock.elapsed_ms,
    )
    _draw_entities(
        screen,
        [(entity, camera.apply_rect(entity.rect)) for entity in all_sprites],
        player,
        has_fuel=has_fuel,
        has_empty_fuel_can=has_empty_fuel_can,
        show_fuel_indicator=not (stage and stage.endurance_stage),
    )
    marker_draw_data_screen = []
    for (
        world_x,
        world_y,
        angle_rad,
    ) in game_data.lineformer_trains.iter_marker_draw_data(
        game_data.groups.zombie_group
    ):
        world_center = pygame.Rect(
            int(round(world_x)),
            int(round(world_y)),
            0,
            0,
        )
        center_x, center_y = camera.apply_rect(world_center).topleft
        marker_draw_data_screen.append((center_x, center_y, angle_rad))
    _draw_lineformer_train_markers(
        screen,
        marker_draw_data_screen,
    )

    _draw_decay_fx(
        screen,
        camera.apply_rect,
        state.decay_effects,
    )

    _draw_falling_fx(
        screen,
        camera.apply_rect,
        state.falling_zombies,
        state.flashlight_count,
        state.dust_rings,
        state.clock.elapsed_ms,
    )

    _draw_hint_indicator(
        screen,
        camera,
        assets,
        player,
        hint_target,
        contact_hint_targets=contact_hint_targets,
        hint_color=hint_color,
        stage=stage,
        flashlight_count=flashlight_count,
    )
    fov_center_screen: tuple[int, int] | None = None
    if fov_target is not None:
        fov_center_screen = tuple(map(int, camera.apply(fov_target).center))
    _draw_fog_of_war(
        screen,
        assets,
        game_data.fog,
        fov_center_screen,
        stage=stage,
        flashlight_count=flashlight_count,
        dawn_ready=state.dawn_ready,
    )

    objective_lines = _build_objective_lines(
        stage=stage,
        state=state,
        player=player,
        active_car=active_car,
        fuel_progress=state.fuel_progress,
        buddy_merged_count=state.buddy_merged_count,
        buddy_required=stage.buddy_required_count if stage else 0,
    )
    if objective_lines:
        _draw_objective(objective_lines, screen=screen)
    _draw_inventory_icons(
        screen,
        assets,
        has_fuel=has_fuel,
        has_empty_fuel_can=has_empty_fuel_can,
        flashlight_count=flashlight_count,
        shoes_count=state.shoes_count,
        player_in_car=player.in_car,
        buddy_onboard=state.buddy_onboard,
        survivors_onboard=state.survivors_onboard,
        passenger_capacity=state.survivor_capacity,
    )
    _draw_survivor_messages(screen, assets, list(state.survivor_messages))
    _draw_endurance_timer(screen, assets, stage=stage, state=state)
    _draw_time_accel_indicator(screen, assets, stage=stage, state=state)
    _draw_status_bar(
        screen,
        assets,
        config,
        stage=stage,
        seed=state.seed,
        debug_mode=state.debug_mode,
        zombie_group=game_data.groups.zombie_group,
        lineformer_marker_count=game_data.lineformer_trains.total_marker_count(),
        falling_spawn_carry=state.falling_spawn_carry,
        show_fps=state.show_fps,
        fps=fps,
    )

    _draw_fade_in_overlay(screen, state)
    _draw_timed_message(
        screen,
        assets,
        message=state.timed_message,
        elapsed_play_ms=state.clock.elapsed_ms,
    )
