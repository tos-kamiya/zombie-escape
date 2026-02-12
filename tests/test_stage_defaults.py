from zombie_escape.models import Stage


def test_stage_default_zombie_spawn_count_per_interval_is_one() -> None:
    stage = Stage(
        id="stage_test_defaults",
        name_key="stages.stage1.name",
        description_key="stages.stage1.description",
    )
    assert stage.zombie_spawn_count_per_interval == 1
