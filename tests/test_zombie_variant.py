from zombie_escape.gameplay.spawn import _create_zombie
from zombie_escape.entities_constants import ZombieKind
from zombie_escape.entities.zombie_dog import ZombieDog
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
        zombie_normal_ratio=1.0,
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


def test_zombie_solitary_ratio_controls_solitary() -> None:
    config = {"fast_zombies": {"enabled": False}}
    stage_on = Stage(
        id="stage_test_solitary_on",
        name_key="stages.stage1.name",
        description_key="stages.stage1.description",
        zombie_solitary_ratio=1.0,
    )
    zombie = _create_zombie(config, stage=stage_on)
    assert zombie.kind == ZombieKind.SOLITARY


def test_zombie_tracker_dog_ratio_controls_tracker_dog_variant() -> None:
    config = {"fast_zombies": {"enabled": False}}
    stage_on = Stage(
        id="stage_test_tracker_dog_on",
        name_key="stages.stage1.name",
        description_key="stages.stage1.description",
        zombie_dog_ratio=0.0,
        zombie_nimble_dog_ratio=0.0,
        zombie_tracker_dog_ratio=1.0,
    )
    zombie = _create_zombie(config, stage=stage_on)
    assert isinstance(zombie, ZombieDog)
    assert zombie.kind == ZombieKind.DOG
    assert str(zombie.variant) in {"tracker", "ZombieDogVariant.TRACKER"}
