from __future__ import annotations

from typing import Any

import pygame

from ..colors import DAWN_AMBIENT_PALETTE_KEY, ambient_palette_key_for_flashlights
from ..entities_constants import SURVIVOR_MAX_SAFE_PASSENGERS
from ..localization import translate as tr
from ..models import GameData, Groups, LevelLayout, ProgressState, Stage
from ..screen_constants import FPS
from ..entities import Camera
from .ambient import _set_ambient_palette
from .constants import INTRO_MESSAGE_DISPLAY_FRAMES


def _frames_to_ms(frames: int) -> int:
    if frames <= 0:
        return 0
    return max(1, int(round((1000 / max(1, FPS)) * frames)))


def schedule_timed_message(
    state: ProgressState,
    text: str | None,
    *,
    duration_frames: int,
    clear_on_input: bool = False,
) -> None:
    if not text:
        state.timed_message = None
        state.timed_message_until = 0
        state.timed_message_clear_on_input = False
        return
    duration_ms = _frames_to_ms(duration_frames)
    state.timed_message = text
    state.timed_message_until = state.elapsed_play_ms + duration_ms
    state.timed_message_clear_on_input = clear_on_input


def initialize_game_state(config: dict[str, Any], stage: Stage) -> GameData:
    """Initialize and return the base game state objects."""
    starts_with_fuel = not stage.requires_fuel
    if stage.endurance_stage:
        starts_with_fuel = False
    starts_with_flashlight = False
    initial_flashlights = 1 if starts_with_flashlight else 0
    initial_palette_key = ambient_palette_key_for_flashlights(initial_flashlights)
    intro_message = tr(stage.intro_key) if stage.intro_key else None
    game_state = ProgressState(
        game_over=False,
        game_won=False,
        timed_message=None,
        timed_message_until=0,
        timed_message_clear_on_input=False,
        game_over_at=None,
        scaled_overview=None,
        overview_created=False,
        footprints=[],
        last_footprint_pos=None,
        footprint_visible_toggle=True,
        elapsed_play_ms=0,
        has_fuel=starts_with_fuel,
        flashlight_count=initial_flashlights,
        shoes_count=0,
        ambient_palette_key=initial_palette_key,
        hint_expires_at=0,
        hint_target_type=None,
        fuel_message_until=0,
        buddy_rescued=0,
        buddy_onboard=0,
        buddy_merged_count=0,
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
        show_fps=False,
        falling_zombies=[],
        falling_spawn_carry=0,
        dust_rings=[],
        player_wall_target_cell=None,
        player_wall_target_ttl=0,
    )
    if intro_message:
        schedule_timed_message(
            game_state,
            intro_message,
            duration_frames=INTRO_MESSAGE_DISPLAY_FRAMES,
            clear_on_input=True,
        )

    # Create sprite groups
    all_sprites = pygame.sprite.LayeredUpdates()
    wall_group = pygame.sprite.Group()
    zombie_group = pygame.sprite.Group()
    survivor_group = pygame.sprite.Group()

    # Create camera
    cell_size = stage.cell_size
    level_width = stage.grid_cols * cell_size
    level_height = stage.grid_rows * cell_size
    camera = Camera(level_width, level_height)

    # Define level layout (will be filled by blueprint generation)
    field_rect = pygame.Rect(0, 0, level_width, level_height)

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
            field_rect=field_rect,
            outside_cells=set(),
            walkable_cells=[],
            outer_wall_cells=set(),
            wall_cells=set(),
            pitfall_cells=set(),
            car_walkable_cells=set(),
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
        blueprint=None,
        fuel=None,
        flashlights=[],
        shoes=[],
    )


def carbonize_outdoor_zombies(game_data: GameData) -> None:
    """Petrify zombies that have already broken through to the exterior."""
    outside_cells = game_data.layout.outside_cells
    if not outside_cells:
        return
    cell_size = game_data.cell_size
    if cell_size <= 0:
        return
    group = game_data.groups.zombie_group
    if not group:
        return
    for zombie in list(group):
        if not zombie.alive():
            continue
        cell = (
            int(zombie.rect.centerx // cell_size),
            int(zombie.rect.centery // cell_size),
        )
        if cell in outside_cells:
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
