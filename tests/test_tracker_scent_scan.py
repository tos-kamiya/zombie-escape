from zombie_escape.entities import Wall, Zombie
from zombie_escape.entities.movement import _zombie_update_tracker_target
from zombie_escape.models import Footprint


def _make_footprint(pos: tuple[float, float], time_ms: int) -> Footprint:
    return Footprint(pos=pos, time=time_ms)


def _force_scan(zombie: Zombie) -> None:
    zombie.tracker_scan_interval_ms = 0
    zombie.tracker_last_scan_time = -999999


def test_tracker_picks_latest_visible_footprint() -> None:
    zombie = Zombie(10, 10, tracker=True)
    _force_scan(zombie)
    footprints = [
        _make_footprint((30, 10), 1000),
        _make_footprint((40, 10), 2000),
    ]
    _zombie_update_tracker_target(zombie, footprints, [])
    assert zombie.tracker_target_pos == (40, 10)


def test_tracker_skips_blocked_latest_footprint() -> None:
    zombie = Zombie(10, 10, tracker=True)
    _force_scan(zombie)
    wall = Wall(30, 0, 10, 20)
    footprints = [
        _make_footprint((50, 10), 3000),
        _make_footprint((10, 50), 2000),
        _make_footprint((30, 10), 1000),
    ]
    _zombie_update_tracker_target(zombie, footprints, [wall])
    assert zombie.tracker_target_pos == (10, 50)


def test_tracker_limits_to_top_k_candidates() -> None:
    zombie = Zombie(10, 10, tracker=True)
    _force_scan(zombie)
    wall = Wall(20, 0, 5, 30)
    footprints = [
        _make_footprint((50, 10), 4000),
        _make_footprint((60, 15), 3000),
        _make_footprint((70, 5), 2000),
        _make_footprint((10, 40), 1000),
    ]
    _zombie_update_tracker_target(zombie, footprints, [wall])
    assert zombie.tracker_target_pos is None
