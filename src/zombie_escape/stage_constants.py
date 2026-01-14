"""Stage definitions and defaults."""

from __future__ import annotations

from .gameplay_constants import ZOMBIE_AGING_DURATION_FRAMES
from .models import Stage

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
        exterior_spawn_weight=0.97,
        interior_spawn_weight=0.03,
    ),
    Stage(
        id="stage3",
        name_key="stages.stage3.name",
        description_key="stages.stage3.description",
        available=True,
        companion_stage=True,
        requires_fuel=True,
        exterior_spawn_weight=0.97,
        interior_spawn_weight=0.03,
    ),
    Stage(
        id="stage4",
        name_key="stages.stage4.name",
        description_key="stages.stage4.description",
        available=True,
        rescue_stage=True,
    ),
    Stage(
        id="stage5",
        name_key="stages.stage5.name",
        description_key="stages.stage5.description",
        available=True,
        requires_fuel=True,
        survival_stage=True,
        survival_goal_ms=1_200_000,
        fuel_spawn_count=0,
        exterior_spawn_weight=0.4,
        interior_spawn_weight=0.6,
    ),
    Stage(
        id="stage6",
        name_key="stages.stage6.name",
        description_key="stages.stage6.description",
        available=True,
        requires_fuel=True,
        exterior_spawn_weight=0.8,
        interior_spawn_weight=0.2,
        zombie_normal_ratio=0.4,
        zombie_tracker_ratio=0.6,
        zombie_aging_duration_frames=ZOMBIE_AGING_DURATION_FRAMES * 2,
    ),
    Stage(
        id="stage7",
        name_key="stages.stage7.name",
        description_key="stages.stage7.description",
        available=True,
        companion_stage=True,
        requires_fuel=True,
        exterior_spawn_weight=0.7,
        interior_spawn_weight=0.3,
        zombie_normal_ratio=0.4,
        zombie_tracker_ratio=0.3,
        zombie_wall_follower_ratio=0.3,
    ),
]
DEFAULT_STAGE_ID = "stage1"


__all__ = [
    "STAGES",
    "DEFAULT_STAGE_ID",
]
