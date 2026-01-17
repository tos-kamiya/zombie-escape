import pytest

from zombie_escape import render
from zombie_escape.level_constants import TILE_SIZE
from zombie_escape.render_constants import (
    FLASHLIGHT_FOG_SCALE_STEP,
    FOG_RADIUS_SCALE,
    build_render_assets,
)


def test_get_fog_scale_base_is_reduced():
    render_assets = build_render_assets(TILE_SIZE)
    scale = render.get_fog_scale(render_assets, None, flashlight_count=0)
    expected = FOG_RADIUS_SCALE
    assert scale == pytest.approx(expected)


def test_get_fog_scale_single_flashlight_restores_default_radius():
    render_assets = build_render_assets(TILE_SIZE)
    scale = render.get_fog_scale(render_assets, None, flashlight_count=1)
    expected = FOG_RADIUS_SCALE + FLASHLIGHT_FOG_SCALE_STEP
    assert scale == pytest.approx(expected)


def test_get_fog_scale_multiple_flashlights_apply_bonus():
    render_assets = build_render_assets(TILE_SIZE)
    scale = render.get_fog_scale(render_assets, None, flashlight_count=2)
    expected = FOG_RADIUS_SCALE + FLASHLIGHT_FOG_SCALE_STEP * 2
    assert scale == pytest.approx(expected)
