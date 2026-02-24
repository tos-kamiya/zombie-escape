import pytest

pytest.importorskip("pygame")

from zombie_escape.render.world_tiles import _fire_brightness_for_flashlights


def test_fire_brightness_darkens_with_more_flashlights() -> None:
    no_flashlight = _fire_brightness_for_flashlights(0)
    one_flashlight = _fire_brightness_for_flashlights(1)
    two_flashlights = _fire_brightness_for_flashlights(2)
    many_flashlights = _fire_brightness_for_flashlights(8)

    assert no_flashlight > one_flashlight > two_flashlights > many_flashlights
    assert many_flashlights >= 0.5
