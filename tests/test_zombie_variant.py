from zombie_escape.gameplay.logic import create_zombie
from zombie_escape.models import Stage


def test_zombie_tracker_ratio_controls_tracker() -> None:
    config = {"fast_zombies": {"enabled": False}}
    stage_on = Stage(
        id="stage_test_on",
        name_key="stages.stage1.name",
        description_key="stages.stage1.description",
        zombie_tracker_ratio=1.0,
    )
    zombie = create_zombie(config, stage=stage_on)
    assert zombie.tracker is True

    stage_off = Stage(
        id="stage_test_off",
        name_key="stages.stage1.name",
        description_key="stages.stage1.description",
        zombie_tracker_ratio=0.0,
    )
    zombie = create_zombie(config, stage=stage_off)
    assert zombie.tracker is False
