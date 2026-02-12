from __future__ import annotations

from zombie_escape.entities import Zombie
from zombie_escape.entities_constants import ZombieKind
from zombie_escape.gameplay.state import initialize_game_state
from zombie_escape.models import Stage


def _make_game_data():
    stage = Stage(
        id="test",
        name_key="stages.test.name",
        description_key="stages.test.description",
    )
    return initialize_game_state({}, stage)


def test_resolve_spawn_target_prefers_existing_train_tail() -> None:
    game_data = _make_game_data()
    manager = game_data.lineformer_trains
    zombie_group = game_data.groups.zombie_group

    target = Zombie(100, 100, kind=ZombieKind.NORMAL)
    head = Zombie(90, 100, kind=ZombieKind.LINEFORMER)
    zombie_group.add(target, head)
    manager.create_train_for_head(
        head,
        target_id=target.lineformer_id,
        now_ms=0,
    )

    train_id, target_id = manager.resolve_spawn_target(
        zombie_group,
        (102, 100),
    )

    assert train_id is not None
    assert target_id is None


def test_dissolving_train_spawns_new_head_from_front_marker() -> None:
    game_data = _make_game_data()
    manager = game_data.lineformer_trains
    zombie_group = game_data.groups.zombie_group

    lost_head = Zombie(120, 120, kind=ZombieKind.LINEFORMER)
    zombie_group.add(lost_head)
    train_id = manager.create_train_for_head(lost_head, target_id=None, now_ms=0)
    manager.append_marker(train_id, (130, 120))
    manager.append_marker(train_id, (140, 120))
    lost_head.kill()

    before_count = len([z for z in zombie_group if z.alive()])
    manager.pre_update(game_data, config={}, now_ms=1000)
    after_count = len([z for z in zombie_group if z.alive()])

    assert after_count == before_count + 1


def test_active_train_merges_into_existing_target_owner_train() -> None:
    game_data = _make_game_data()
    manager = game_data.lineformer_trains
    zombie_group = game_data.groups.zombie_group

    target = Zombie(100, 100, kind=ZombieKind.NORMAL)
    head_a = Zombie(90, 100, kind=ZombieKind.LINEFORMER)
    head_b = Zombie(110, 100, kind=ZombieKind.LINEFORMER)
    zombie_group.add(target, head_a, head_b)

    train_a = manager.create_train_for_head(
        head_a,
        target_id=target.lineformer_id,
        now_ms=0,
    )
    train_b = manager.create_train_for_head(
        head_b,
        target_id=target.lineformer_id,
        now_ms=0,
    )

    manager.pre_update(game_data, config={}, now_ms=100)

    assert train_a not in manager.trains
    assert train_b in manager.trains
    assert len(manager.trains[train_b].marker_positions) >= 1
    assert len(game_data.state.lineformer_merge_effects) == 1


def test_train_with_markers_does_not_merge_even_if_same_target() -> None:
    game_data = _make_game_data()
    manager = game_data.lineformer_trains
    zombie_group = game_data.groups.zombie_group

    target = Zombie(100, 100, kind=ZombieKind.NORMAL)
    head_a = Zombie(92, 100, kind=ZombieKind.LINEFORMER)
    head_b = Zombie(110, 100, kind=ZombieKind.LINEFORMER)
    zombie_group.add(target, head_a, head_b)

    train_a = manager.create_train_for_head(
        head_a,
        target_id=target.lineformer_id,
        now_ms=0,
    )
    manager.append_marker(train_a, (80, 100))
    train_b = manager.create_train_for_head(
        head_b,
        target_id=target.lineformer_id,
        now_ms=0,
    )

    manager.pre_update(game_data, config={}, now_ms=100)

    assert train_a in manager.trains
    assert train_b in manager.trains


def test_train_avoids_target_already_reserved_by_other_train() -> None:
    game_data = _make_game_data()
    manager = game_data.lineformer_trains
    zombie_group = game_data.groups.zombie_group

    claimed_target = Zombie(100, 100, kind=ZombieKind.NORMAL)
    free_target = Zombie(140, 100, kind=ZombieKind.NORMAL)
    head_a = Zombie(96, 100, kind=ZombieKind.LINEFORMER)
    head_b = Zombie(94, 100, kind=ZombieKind.LINEFORMER)
    zombie_group.add(claimed_target, free_target, head_a, head_b)

    train_a = manager.create_train_for_head(
        head_a,
        target_id=claimed_target.lineformer_id,
        now_ms=0,
    )
    train_b = manager.create_train_for_head(
        head_b,
        target_id=None,
        now_ms=0,
    )

    manager.pre_update(game_data, config={}, now_ms=100)

    assert train_a in manager.trains
    assert train_b in manager.trains
    assert head_b.lineformer_follow_target_id != claimed_target.lineformer_id
    assert head_b.lineformer_follow_target_id == free_target.lineformer_id
