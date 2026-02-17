import pytest

from zombie_escape.models import FuelMode, Stage


def test_stage_default_zombie_spawn_count_per_interval_is_one() -> None:
    stage = Stage(
        id="stage_test_defaults",
        name_key="stages.stage1.name",
        description_key="stages.stage1.description",
        zombie_normal_ratio=1.0,
    )
    assert stage.zombie_spawn_count_per_interval == 1


def test_stage_requires_any_zombie_ratio() -> None:
    with pytest.raises(AssertionError, match="at least one zombie ratio must be > 0"):
        Stage(
            id="stage_test_no_zombie_ratio",
            name_key="stages.stage1.name",
            description_key="stages.stage1.description",
        )


def test_stage_accepts_solitary_only_ratio() -> None:
    stage = Stage(
        id="stage_test_solitary_ratio",
        name_key="stages.stage1.name",
        description_key="stages.stage1.description",
        zombie_solitary_ratio=1.0,
    )
    assert stage.zombie_solitary_ratio == 1.0


def test_stage_refuel_chain_requires_distinct_item_counts() -> None:
    with pytest.raises(AssertionError):
        Stage(
            id="stage_test_refuel_invalid",
            name_key="stages.stage1.name",
            description_key="stages.stage1.description",
            fuel_mode=FuelMode.REFUEL_CHAIN,
            empty_fuel_can_spawn_count=0,
            zombie_normal_ratio=1.0,
        )

    with pytest.raises(AssertionError):
        Stage(
            id="stage_test_refuel_invalid_station",
            name_key="stages.stage1.name",
            description_key="stages.stage1.description",
            fuel_mode=FuelMode.REFUEL_CHAIN,
            fuel_station_spawn_count=0,
            zombie_normal_ratio=1.0,
        )


def test_stage_zone_exclusivity_assertion() -> None:
    """Ensure Stage raises AssertionError when different gimmick zones overlap."""
    # Pitfall vs Houseplant
    with pytest.raises(AssertionError, match="Pitfall and Houseplant zones overlap"):
        Stage(
            id="overlap_1",
            name_key="n",
            description_key="d",
            pitfall_zones=[(10, 10, 2, 2)],
            houseplant_zones=[(11, 11, 1, 1)],  # Overlaps at (11, 11)
            zombie_normal_ratio=1.0,
        )

    # Houseplant vs Puddle
    with pytest.raises(AssertionError, match="Houseplant and Puddle zones overlap"):
        Stage(
            id="overlap_2",
            name_key="n",
            description_key="d",
            houseplant_zones=[(5, 5, 5, 5)],
            puddle_zones=[(9, 9, 2, 2)],  # Overlaps at (9, 9)
            zombie_normal_ratio=1.0,
        )

    # Moving Floor vs Puddle
    with pytest.raises(AssertionError, match="Moving Floor and Puddle zones overlap"):
        Stage(
            id="overlap_3",
            name_key="n",
            description_key="d",
            moving_floor_zones={"U": [(0, 0, 10, 10)]},
            puddle_zones=[(5, 5, 1, 1)],
            zombie_normal_ratio=1.0,
        )

    # Moving Floor vs Reinforced Wall
    with pytest.raises(
        AssertionError, match="Moving Floor and Reinforced Wall zones overlap"
    ):
        Stage(
            id="overlap_4",
            name_key="n",
            description_key="d",
            moving_floor_zones={"U": [(1, 1, 4, 4)]},
            reinforced_wall_zones=[(2, 2, 1, 1)],
            zombie_normal_ratio=1.0,
        )
