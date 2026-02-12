from zombie_escape.gameplay.spawn import _create_zombie
from zombie_escape.entities_constants import ZombieKind
from zombie_escape.models import Stage


def test_zombie_tracker_ratio_controls_tracker() -> None:
    config = {"fast_zombies": {"enabled": False}}
    stage_on = Stage(
        id="stage_test_on",
        name_key="stages.stage1.name",
        description_key="stages.stage1.description",
        zombie_tracker_ratio=1.0,
    )
    zombie = _create_zombie(config, stage=stage_on)
    assert zombie.kind == ZombieKind.TRACKER

    stage_off = Stage(
        id="stage_test_off",
        name_key="stages.stage1.name",
        description_key="stages.stage1.description",
        zombie_tracker_ratio=0.0,
    )
    zombie = _create_zombie(config, stage=stage_off)
    assert zombie.kind != ZombieKind.TRACKER


def test_zombie_lineformer_ratio_controls_lineformer() -> None:
    config = {"fast_zombies": {"enabled": False}}
    stage_on = Stage(
        id="stage_test_lineformer_on",
        name_key="stages.stage1.name",
        description_key="stages.stage1.description",
        zombie_lineformer_ratio=1.0,
    )
    zombie = _create_zombie(config, stage=stage_on)
    assert zombie.kind == ZombieKind.LINEFORMER
