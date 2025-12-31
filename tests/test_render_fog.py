import pytest

from zombie_escape import render
from zombie_escape.constants import (
    FLASHLIGHT_FOG_SCALE_STEP,
    FOG_RADIUS_SCALE,
    RENDER_ASSETS,
)


def test_get_fog_scale_base_is_reduced():
    scale = render.get_fog_scale(RENDER_ASSETS, None, flashlight_count=0)
    expected = FOG_RADIUS_SCALE
    assert scale == pytest.approx(expected)


def test_get_fog_scale_single_flashlight_restores_default_radius():
    scale = render.get_fog_scale(RENDER_ASSETS, None, flashlight_count=1)
    expected = FOG_RADIUS_SCALE + FLASHLIGHT_FOG_SCALE_STEP
    assert scale == pytest.approx(expected)


def test_get_fog_scale_multiple_flashlights_apply_bonus():
    scale = render.get_fog_scale(RENDER_ASSETS, None, flashlight_count=2)
    expected = FOG_RADIUS_SCALE + FLASHLIGHT_FOG_SCALE_STEP * 2
    assert scale == pytest.approx(expected)
