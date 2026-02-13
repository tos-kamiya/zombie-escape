import pytest

from zombie_escape.models import Stage


def test_stage_default_zombie_spawn_count_per_interval_is_one() -> None:
    stage = Stage(
        id="stage_test_defaults",
        name_key="stages.stage1.name",
        description_key="stages.stage1.description",
    )
    assert stage.zombie_spawn_count_per_interval == 1


def test_stage_requires_refuel_requires_fuel() -> None:
    with pytest.raises(AssertionError):
        Stage(
            id="stage_test_refuel_invalid",
            name_key="stages.stage1.name",
            description_key="stages.stage1.description",
            requires_refuel=True,
            requires_fuel=False,
        )
