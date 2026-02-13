import pytest

from zombie_escape.models import FuelObjective, Stage


def test_stage_default_zombie_spawn_count_per_interval_is_one() -> None:
    stage = Stage(
        id="stage_test_defaults",
        name_key="stages.stage1.name",
        description_key="stages.stage1.description",
    )
    assert stage.zombie_spawn_count_per_interval == 1


def test_stage_refuel_chain_requires_fuel_station_count() -> None:
    with pytest.raises(AssertionError):
        Stage(
            id="stage_test_refuel_invalid",
            name_key="stages.stage1.name",
            description_key="stages.stage1.description",
            fuel_objective=FuelObjective.REFUEL_CHAIN,
            fuel_station_spawn_count=0,
        )
