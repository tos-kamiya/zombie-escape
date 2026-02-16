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
        zombie_normal_ratio=1.0,
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
    head_a = Zombie(95, 100, kind=ZombieKind.LINEFORMER)
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
    assert manager.trains[train_b].history[0] == (head_a.x, head_a.y)


def test_lone_train_does_not_merge_when_not_near_destination_trail() -> None:
    game_data = _make_game_data()
    manager = game_data.lineformer_trains
    zombie_group = game_data.groups.zombie_group

    target = Zombie(100, 100, kind=ZombieKind.NORMAL)
    head_a = Zombie(95, 100, kind=ZombieKind.LINEFORMER)
    head_b = Zombie(120, 100, kind=ZombieKind.LINEFORMER)
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
    dst_train = manager.trains[train_b]
    dst_train.marker_positions.append((100.0, 100.0))
    dst_train.history.clear()
    dst_train.history.append((200.0, 200.0))
    dst_train.history.append((220.0, 200.0))

    manager.pre_update(game_data, config={}, now_ms=100)

    assert train_a in manager.trains
    assert train_b in manager.trains


def test_marker_position_interpolates_along_discrete_history() -> None:
    game_data = _make_game_data()
    manager = game_data.lineformer_trains
    zombie_group = game_data.groups.zombie_group

    head = Zombie(100, 100, kind=ZombieKind.LINEFORMER)
    zombie_group.add(head)
    train_id = manager.create_train_for_head(
        head,
        target_id=None,
        now_ms=0,
    )
    assert manager.append_marker(train_id, (100, 100))
    train = manager.trains[train_id]
    train.history.clear()
    train.history.append((80.0, 100.0))
    train.history.append((100.0, 100.0))
    head.x = 110.0
    head.y = 100.0

    manager.post_update(zombie_group)

    marker_x, marker_y = train.marker_positions[0]
    assert marker_x == 86.0
    assert marker_y == 100.0


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


def test_lineformer_head_base_speed_stays_constant_in_pre_update() -> None:
    game_data = _make_game_data()
    manager = game_data.lineformer_trains
    zombie_group = game_data.groups.zombie_group

    target = Zombie(100, 100, kind=ZombieKind.NORMAL)
    head = Zombie(95, 100, kind=ZombieKind.LINEFORMER)
    zombie_group.add(target, head)
    manager.create_train_for_head(
        head,
        target_id=target.lineformer_id,
        now_ms=0,
    )

    idle_speed = head.initial_speed
    manager.pre_update(game_data, config={}, now_ms=100)
    assert head.initial_speed == idle_speed

    target.kill()
    manager.pre_update(game_data, config={}, now_ms=200)
    assert head.initial_speed == idle_speed
