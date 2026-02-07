"""Stage definitions and defaults."""

from __future__ import annotations

from .entities_constants import ZOMBIE_DECAY_DURATION_FRAMES
from .gameplay_constants import SURVIVOR_SPAWN_RATE
from .level_constants import DEFAULT_GRID_COLS, DEFAULT_GRID_ROWS
from .models import Stage


def _build_stage18_pitfall_zones(
    *,
    grid_cols: int,
    grid_rows: int,
    rooms_per_side: int,
    room_size: int,
    gap_width: int,
) -> list[tuple[int, int, int, int]]:
    pitfall_cells: set[tuple[int, int]] = set()

    # Outer pitfall ring inside the outer wall band.
    for y in range(2, grid_rows - 2):
        pitfall_cells.add((2, y))
        pitfall_cells.add((grid_cols - 3, y))
    for x in range(2, grid_cols - 2):
        pitfall_cells.add((x, 2))
        pitfall_cells.add((x, grid_rows - 3))

    # Room gap bands.
    inner_start = 3
    gap_cols: list[int] = []
    gap_rows: list[int] = []
    step = room_size + gap_width
    for idx in range(1, rooms_per_side):
        gap_start = inner_start + idx * step - gap_width
        gap_cols.extend(range(gap_start, gap_start + gap_width))
        gap_rows.extend(range(gap_start, gap_start + gap_width))
    for x in gap_cols:
        for y in range(3, grid_rows - 3):
            pitfall_cells.add((x, y))
    for y in gap_rows:
        for x in range(3, grid_cols - 3):
            pitfall_cells.add((x, y))

    # Corridor openings (width 1) through the gap bands.
    room_centers = [
        inner_start + (room_size // 2) + idx * step for idx in range(rooms_per_side)
    ]
    for y in room_centers:
        for x in gap_cols:
            pitfall_cells.discard((x, y))
    for x in room_centers:
        for y in gap_rows:
            pitfall_cells.discard((x, y))

    # Faux corridors through the outer pitfall ring.
    for y in room_centers:
        pitfall_cells.discard((2, y))
        pitfall_cells.discard((grid_cols - 3, y))
    for x in room_centers:
        pitfall_cells.discard((x, 2))
        pitfall_cells.discard((x, grid_rows - 3))

    # Jagged room edges: every 2 cells, let the room "bite" into pitfall bands.
    for row in range(rooms_per_side):
        for col in range(rooms_per_side):
            start_x = 3 + col * (room_size + gap_width)
            start_y = 3 + row * (room_size + gap_width)
            for offset in range(0, room_size, 2):
                x = start_x + offset
                y = start_y + offset
                pitfall_cells.discard((x, start_y - 1))
                pitfall_cells.discard((x, start_y + room_size))
                pitfall_cells.discard((start_x - 1, y))
                pitfall_cells.discard((start_x + room_size, y))

    pitfall_zones = [(x, y, 1, 1) for x, y in sorted(pitfall_cells)]
    room_cells: set[tuple[int, int]] = set()
    for row in range(rooms_per_side):
        for col in range(rooms_per_side):
            start_x = 3 + col * (room_size + gap_width)
            start_y = 3 + row * (room_size + gap_width)
            for y in range(start_y, start_y + room_size):
                for x in range(start_x, start_x + room_size):
                    room_cells.add((x, y))

    return pitfall_zones


STAGES: list[Stage] = [
    Stage(
        id="stage1",
        name_key="stages.stage1.name",
        description_key="stages.stage1.description",
        available=True,
        exterior_spawn_weight=0.97,
        interior_spawn_weight=0.03,
    ),
    Stage(
        id="stage2",
        name_key="stages.stage2.name",
        description_key="stages.stage2.description",
        available=True,
        requires_fuel=True,
        initial_interior_spawn_rate=0.007,
        exterior_spawn_weight=0.97,
        interior_spawn_weight=0.03,
    ),
    Stage(
        id="stage3",
        name_key="stages.stage3.name",
        description_key="stages.stage3.description",
        available=True,
        requires_fuel=True,
        buddy_required_count=1,
        initial_interior_spawn_rate=0.007,
        exterior_spawn_weight=0.97,
        interior_spawn_weight=0.03,
    ),
    Stage(
        id="stage4",
        name_key="stages.stage4.name",
        description_key="stages.stage4.description",
        available=True,
        survivor_rescue_stage=True,
        waiting_car_target_count=2,
        initial_interior_spawn_rate=0.007,
        survivor_spawn_rate=SURVIVOR_SPAWN_RATE,
    ),
    Stage(
        id="stage5",
        name_key="stages.stage5.name",
        description_key="stages.stage5.description",
        intro_key="stages.stage5.intro",
        available=True,
        wall_algorithm="default.120%",
        requires_fuel=True,
        endurance_stage=True,
        endurance_goal_ms=1_200_000,
        fuel_spawn_count=0,
        initial_interior_spawn_rate=0.02,
        exterior_spawn_weight=0.15,
        interior_spawn_weight=0.85,
        zombie_decay_duration_frames=int(ZOMBIE_DECAY_DURATION_FRAMES * 1.5),
    ),
    Stage(
        id="stage6",
        name_key="stages.stage6.name",
        description_key="stages.stage6.description",
        available=True,
        requires_fuel=True,
        initial_interior_spawn_rate=0.01,
        exterior_spawn_weight=0.8,
        interior_spawn_weight=0.2,
        zombie_tracker_ratio=0.6,
        zombie_normal_ratio=0.4,
        zombie_decay_duration_frames=ZOMBIE_DECAY_DURATION_FRAMES * 2,
    ),
    Stage(
        id="stage7",
        name_key="stages.stage7.name",
        description_key="stages.stage7.description",
        available=True,
        wall_algorithm="grid_wire",
        requires_fuel=True,
        buddy_required_count=1,
        initial_interior_spawn_rate=0.01,
        exterior_spawn_weight=0.7,
        interior_spawn_weight=0.3,
        zombie_tracker_ratio=0.3,
        zombie_wall_hugging_ratio=0.3,
        zombie_normal_ratio=0.4,
        zombie_decay_duration_frames=ZOMBIE_DECAY_DURATION_FRAMES * 2,
    ),
    Stage(
        id="stage8",
        name_key="stages.stage8.name",
        description_key="stages.stage8.description",
        available=True,
        cell_size=35,
        wall_algorithm="grid_wire",
        requires_fuel=True,
        initial_interior_spawn_rate=0.01,
        exterior_spawn_weight=0.4,
        interior_spawn_weight=0.6,
        zombie_tracker_ratio=0.3,
        zombie_wall_hugging_ratio=0.7,
        zombie_normal_ratio=0,
        zombie_decay_duration_frames=ZOMBIE_DECAY_DURATION_FRAMES * 2,
    ),
    Stage(
        id="stage9",
        name_key="stages.stage9.name",
        description_key="stages.stage9.description",
        available=True,
        cell_size=35,
        requires_fuel=True,
        survivor_rescue_stage=True,
        waiting_car_target_count=1,
        initial_interior_spawn_rate=0.01,
        exterior_spawn_weight=0.4,
        interior_spawn_weight=0.6,
        zombie_tracker_ratio=0.3,
        zombie_wall_hugging_ratio=0.7,
        zombie_normal_ratio=0,
        zombie_decay_duration_frames=ZOMBIE_DECAY_DURATION_FRAMES * 2,
        survivor_spawn_rate=SURVIVOR_SPAWN_RATE,
    ),
    Stage(
        id="stage10",
        name_key="stages.stage10.name",
        description_key="stages.stage10.description",
        intro_key="stages.stage10.intro",
        available=True,
        cell_size=40,
        wall_algorithm="sparse_moore.10%",
        survivor_rescue_stage=True,
        waiting_car_target_count=1,
        initial_interior_spawn_rate=0.02,
        exterior_spawn_weight=0.7,
        interior_spawn_weight=0.3,
        zombie_tracker_ratio=0.4,
        zombie_wall_hugging_ratio=0.2,
        zombie_normal_ratio=0.4,
        zombie_decay_duration_frames=ZOMBIE_DECAY_DURATION_FRAMES * 2,
        survivor_spawn_rate=0.35,
    ),
    Stage(
        id="stage11",
        name_key="stages.stage11.name",
        description_key="stages.stage11.description",
        available=True,
        grid_cols=120,
        grid_rows=7,
        wall_algorithm="sparse_moore.10%",
        initial_shoes_count=1,
        waiting_car_target_count=1,
        initial_interior_spawn_rate=0.1,
        exterior_spawn_weight=0.3,
        interior_spawn_weight=0.7,
        zombie_tracker_ratio=0.5,
        zombie_normal_ratio=0.5,
        zombie_decay_duration_frames=ZOMBIE_DECAY_DURATION_FRAMES * 2,
    ),
    Stage(
        id="stage12",
        name_key="stages.stage12.name",
        description_key="stages.stage12.description",
        available=True,
        grid_cols=32,
        grid_rows=32,
        fall_spawn_zones=[
            (4, 4, 10, 10),
            (4, 18, 10, 10),
            (18, 4, 10, 10),
            (18, 18, 10, 10),
        ],
        requires_fuel=True,
        initial_flashlight_count=5,
        initial_shoes_count=1,
        exterior_spawn_weight=0.5,
        interior_spawn_weight=0.2,
        interior_fall_spawn_weight=0.3,
        zombie_decay_duration_frames=ZOMBIE_DECAY_DURATION_FRAMES * 2,
    ),
    Stage(
        id="stage13",
        name_key="stages.stage13.name",
        description_key="stages.stage13.description",
        available=True,
        grid_cols=46,
        grid_rows=30,
        wall_algorithm="grid_wire",
        fall_spawn_zones=[
            (x, y, 2, 2)
            for y in range(2, DEFAULT_GRID_ROWS - 2, 4)
            for x in range(2, DEFAULT_GRID_COLS - 2, 4)
        ],
        requires_fuel=True,
        buddy_required_count=1,
        initial_flashlight_count=3,
        initial_shoes_count=1,
        exterior_spawn_weight=0.6,
        interior_spawn_weight=0.1,
        interior_fall_spawn_weight=0.3,
        zombie_tracker_ratio=0.3,
        zombie_wall_hugging_ratio=0.3,
        zombie_normal_ratio=0.4,
        zombie_decay_duration_frames=ZOMBIE_DECAY_DURATION_FRAMES * 2,
    ),
    Stage(
        id="stage14",
        name_key="stages.stage14.name",
        description_key="stages.stage14.description",
        available=True,
        grid_cols=34,
        grid_rows=20,
        wall_rubble_ratio=0.35,
        fall_spawn_floor_ratio=0.05,
        requires_fuel=True,
        initial_flashlight_count=3,
        initial_shoes_count=1,
        exterior_spawn_weight=0.2,
        interior_spawn_weight=0.1,
        interior_fall_spawn_weight=0.7,
        zombie_decay_duration_frames=ZOMBIE_DECAY_DURATION_FRAMES * 2,
    ),
    Stage(
        id="stage15",
        name_key="stages.stage15.name",
        description_key="stages.stage15.description",
        intro_key="stages.stage15.intro",
        available=True,
        cell_size=35,
        grid_cols=64,
        grid_rows=24,
        wall_algorithm="grid_wire",
        fall_spawn_zones=[
            (33, 2, 4, 18),
        ],
        requires_fuel=True,
        buddy_required_count=1,
        initial_flashlight_count=3,
        initial_shoes_count=1,
        initial_interior_spawn_rate=0.02,
        exterior_spawn_weight=0.2,
        interior_spawn_weight=0.1,
        interior_fall_spawn_weight=0.7,
        zombie_wall_hugging_ratio=0.5,
        zombie_normal_ratio=0.5,
        zombie_decay_duration_frames=ZOMBIE_DECAY_DURATION_FRAMES * 2,
    ),
    Stage(
        id="stage16",
        name_key="stages.stage16.name",
        description_key="stages.stage16.description",
        available=True,
        cell_size=60,
        grid_cols=40,
        grid_rows=25,
        wall_algorithm="sparse_moore.25%",
        pitfall_density=0.04,
        requires_fuel=True,
        initial_flashlight_count=1,
        initial_shoes_count=1,
        initial_interior_spawn_rate=0.05,
        exterior_spawn_weight=0.7,
        interior_spawn_weight=0.3,
        zombie_decay_duration_frames=ZOMBIE_DECAY_DURATION_FRAMES * 2,
    ),
    Stage(
        id="stage17",
        name_key="stages.stage17.name",
        description_key="stages.stage17.description",
        available=True,
        grid_cols=40,
        grid_rows=26,
        wall_algorithm="sparse_moore.25%",
        wall_rubble_ratio=0.25,
        pitfall_density=0.08,
        requires_fuel=True,
        initial_flashlight_count=1,
        initial_shoes_count=1,
        initial_interior_spawn_rate=0.1,
        exterior_spawn_weight=0.5,
        interior_spawn_weight=0.5,
        zombie_tracker_ratio=1.0,
        zombie_decay_duration_frames=ZOMBIE_DECAY_DURATION_FRAMES * 2,
    ),
    Stage(
        id="stage18",
        name_key="stages.stage18.name",
        description_key="stages.stage18.description",
        available=True,
        grid_cols=36,
        grid_rows=36,
        wall_algorithm="sparse_ortho.30%",
        wall_rubble_ratio=0.15,
        fall_spawn_floor_ratio=0.03,
        pitfall_zones=_build_stage18_pitfall_zones(
            grid_cols=36,
            grid_rows=36,
            rooms_per_side=3,
            room_size=8,
            gap_width=3,
        ),
        requires_fuel=True,
        initial_interior_spawn_rate=0.08,
        exterior_spawn_weight=0.6,
        interior_spawn_weight=0.4,
        zombie_tracker_ratio=0.5,
        zombie_normal_ratio=0.5,
        zombie_decay_duration_frames=ZOMBIE_DECAY_DURATION_FRAMES * 2,
    ),
    Stage(
        id="stage19",
        name_key="stages.stage19.name",
        description_key="stages.stage19.description",
        available=True,
        grid_cols=35,
        grid_rows=35,
        cell_size=35,
        wall_algorithm="grid_wire.170%",
        fall_spawn_floor_ratio=0.02,
        pitfall_density=0.008,
        requires_fuel=True,
        buddy_required_count=1,
        initial_interior_spawn_rate=0.08,
        exterior_spawn_weight=0.4,
        interior_spawn_weight=0.0,
        interior_fall_spawn_weight=0.6,
        zombie_tracker_ratio=0.5,
        zombie_wall_hugging_ratio=0.5,
        zombie_normal_ratio=0,
        zombie_decay_duration_frames=ZOMBIE_DECAY_DURATION_FRAMES * 2,
    ),
    Stage(
        id="stage20",
        name_key="stages.stage20.name",
        description_key="stages.stage20.description",
        intro_key="stages.stage20.intro",
        available=True,
        wall_algorithm="default.150%",
        wall_rubble_ratio=0.2,
        fall_spawn_floor_ratio=0.008,
        fall_spawn_zones=[
            (19, 10, 10, 10),
        ],
        pitfall_density=0.008,
        requires_fuel=True,
        buddy_required_count=3,
        initial_interior_spawn_rate=0.08,
        exterior_spawn_weight=0.4,
        interior_spawn_weight=0.2,
        interior_fall_spawn_weight=0.4,
        zombie_tracker_ratio=0.4,
        zombie_wall_hugging_ratio=0.4,
        zombie_normal_ratio=0.2,
        zombie_decay_duration_frames=ZOMBIE_DECAY_DURATION_FRAMES * 2,
    ),
    Stage(
        id="stage21",
        name_key="stages.stage21.name",
        description_key="stages.stage21.description",
        available=True,
        cell_size=60,
        grid_cols=35,
        grid_rows=25,
        wall_algorithm="grid_wire.20%",
        pitfall_density=0.02,
        requires_fuel=True,
        initial_interior_spawn_rate=0.1,
        exterior_spawn_weight=0.5,
        interior_spawn_weight=0.5,
        zombie_dog_ratio=0.5,
        zombie_normal_ratio=0.5,
        zombie_tracker_ratio=0.0,
        zombie_wall_hugging_ratio=0.0,
    ),
]
DEFAULT_STAGE_ID = "stage1"


__all__ = [
    "STAGES",
    "DEFAULT_STAGE_ID",
]
