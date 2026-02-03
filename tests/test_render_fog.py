import pytest

from zombie_escape import render
from zombie_escape.level_constants import DEFAULT_CELL_SIZE
from zombie_escape.render_constants import (
    FLASHLIGHT_FOG_SCALE_ONE,
    FLASHLIGHT_FOG_SCALE_TWO,
    FOG_RADIUS_SCALE,
    build_render_assets,
)


def test_get_fog_scale_base_is_reduced():
    render_assets = build_render_assets(DEFAULT_CELL_SIZE)
    scale = render._get_fog_scale(render_assets, flashlight_count=0)
    expected = FOG_RADIUS_SCALE
    assert scale == pytest.approx(expected)


def test_get_fog_scale_single_flashlight_restores_default_radius():
    render_assets = build_render_assets(DEFAULT_CELL_SIZE)
    scale = render._get_fog_scale(render_assets, flashlight_count=1)
    expected = FLASHLIGHT_FOG_SCALE_ONE
    assert scale == pytest.approx(expected)


def test_get_fog_scale_multiple_flashlights_apply_bonus():
    render_assets = build_render_assets(DEFAULT_CELL_SIZE)
    scale = render._get_fog_scale(render_assets, flashlight_count=2)
    expected = FLASHLIGHT_FOG_SCALE_TWO
    assert scale == pytest.approx(expected)
