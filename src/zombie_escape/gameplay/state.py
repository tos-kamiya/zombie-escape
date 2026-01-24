from __future__ import annotations

from typing import Any

import pygame

from ..colors import DAWN_AMBIENT_PALETTE_KEY, ambient_palette_key_for_flashlights
from ..entities_constants import SURVIVOR_MAX_SAFE_PASSENGERS
from ..models import GameData, Groups, LevelLayout, ProgressState, Stage
from ..entities import Camera
from .ambient import _set_ambient_palette


def initialize_game_state(config: dict[str, Any], stage: Stage) -> GameData:
    """Initialize and return the base game state objects."""
    starts_with_fuel = not stage.requires_fuel
    if stage.endurance_stage:
        starts_with_fuel = False
    starts_with_flashlight = False
    initial_flashlights = 1 if starts_with_flashlight else 0
    initial_palette_key = ambient_palette_key_for_flashlights(initial_flashlights)
    game_state = ProgressState(
        game_over=False,
        game_won=False,
        game_over_message=None,
        game_over_at=None,
        scaled_overview=None,
        overview_created=False,
        footprints=[],
        last_footprint_pos=None,
        elapsed_play_ms=0,
        has_fuel=starts_with_fuel,
        flashlight_count=initial_flashlights,
        ambient_palette_key=initial_palette_key,
        hint_expires_at=0,
        hint_target_type=None,
        fuel_message_until=0,
        buddy_rescued=0,
        buddy_onboard=0,
        survivors_onboard=0,
        survivors_rescued=0,
        survivor_messages=[],
        survivor_capacity=SURVIVOR_MAX_SAFE_PASSENGERS,
        seed=None,
        endurance_elapsed_ms=0,
        endurance_goal_ms=max(0, stage.endurance_goal_ms),
        dawn_ready=False,
        dawn_prompt_at=None,
        time_accel_active=False,
        last_zombie_spawn_time=0,
        dawn_carbonized=False,
        debug_mode=False,
        falling_zombies=[],
        falling_spawn_carry=0,
        dust_rings=[],
    )

    # Create sprite groups
    all_sprites = pygame.sprite.LayeredUpdates()
    wall_group = pygame.sprite.Group()
    zombie_group = pygame.sprite.Group()
    survivor_group = pygame.sprite.Group()

    # Create camera
    cell_size = stage.tile_size
    level_width = stage.grid_cols * cell_size
    level_height = stage.grid_rows * cell_size
    camera = Camera(level_width, level_height)

    # Define level layout (will be filled by blueprint generation)
    outer_rect = 0, 0, level_width, level_height
    inner_rect = outer_rect

    return GameData(
        state=game_state,
        groups=Groups(
            all_sprites=all_sprites,
            wall_group=wall_group,
            zombie_group=zombie_group,
            survivor_group=survivor_group,
        ),
        camera=camera,
        layout=LevelLayout(
            outer_rect=outer_rect,
            inner_rect=inner_rect,
            outside_rects=[],
            walkable_cells=[],
            outer_wall_cells=set(),
            wall_cells=set(),
            fall_spawn_cells=set(),
            bevel_corners={},
        ),
        fog={
            "hatch_patterns": {},
            "overlays": {},
        },
        stage=stage,
        cell_size=cell_size,
        level_width=level_width,
        level_height=level_height,
        fuel=None,
        flashlights=[],
    )


def carbonize_outdoor_zombies(game_data: GameData) -> None:
    """Petrify zombies that have already broken through to the exterior."""
    outside_rects = game_data.layout.outside_rects or []
    if not outside_rects:
        return
    group = game_data.groups.zombie_group
    if not group:
        return
    for zombie in list(group):
        if not zombie.alive():
            continue
        center = zombie.rect.center
        if any(rect_obj.collidepoint(center) for rect_obj in outside_rects):
            zombie.carbonize()


def update_endurance_timer(game_data: GameData, dt_ms: int) -> None:
    """Advance the endurance countdown and trigger dawn handoff."""
    stage = game_data.stage
    state = game_data.state
    if not stage.endurance_stage:
        return
    if state.endurance_goal_ms <= 0 or dt_ms <= 0:
        return
    state.endurance_elapsed_ms = min(
        state.endurance_goal_ms,
        state.endurance_elapsed_ms + dt_ms,
    )
    if not state.dawn_ready and state.endurance_elapsed_ms >= state.endurance_goal_ms:
        state.dawn_ready = True
        state.dawn_prompt_at = pygame.time.get_ticks()
        _set_ambient_palette(game_data, DAWN_AMBIENT_PALETTE_KEY, force=True)
    if state.dawn_ready:
        carbonize_outdoor_zombies(game_data)
        state.dawn_carbonized = True
