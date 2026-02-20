from zombie_escape.entities import Zombie
from zombie_escape.entities_constants import ZombieKind
from zombie_escape.render_constants import ANGLE_BINS


def test_wall_hugger_marker_cache_uses_three_states() -> None:
    zombie = Zombie(100, 100, kind=ZombieKind.WALL_HUGGER)

    zombie.wall_hug_side = 1.0
    zombie.wall_hug_last_side_has_wall = False
    zombie.refresh_image()
    assert (zombie.facing_bin, 0) in zombie._dynamic_variant_image_cache

    zombie.wall_hug_side = 1.0
    zombie.wall_hug_last_side_has_wall = True
    zombie.refresh_image()
    assert (zombie.facing_bin, 1) in zombie._dynamic_variant_image_cache

    zombie.wall_hug_side = -1.0
    zombie.wall_hug_last_side_has_wall = True
    zombie.refresh_image()
    assert (zombie.facing_bin, 2) in zombie._dynamic_variant_image_cache


def test_lineformer_marker_cache_quantizes_target_to_16_bins() -> None:
    zombie = Zombie(100, 100, kind=ZombieKind.LINEFORMER)

    zombie.lineformer_target_pos = (zombie.x + 100.0, zombie.y)
    zombie.refresh_image()
    east_bin = zombie._lineformer_target_bin16()
    assert 0 <= east_bin < ANGLE_BINS
    assert (zombie.facing_bin, east_bin) in zombie._dynamic_variant_image_cache

    zombie.lineformer_target_pos = (zombie.x, zombie.y + 100.0)
    zombie.refresh_image()
    south_bin = zombie._lineformer_target_bin16()
    assert 0 <= south_bin < ANGLE_BINS
    assert (zombie.facing_bin, south_bin) in zombie._dynamic_variant_image_cache
    assert east_bin != south_bin
