import numpy as np
import pygame
import pygame.surfarray as pg_surfarray

from zombie_escape.level_constants import DEFAULT_CELL_SIZE
from zombie_escape.render.fog import (
    _FogProfile,
    _get_fog_overlay_surfaces,
    save_fog_cache_profile,
)
from zombie_escape.render_constants import build_render_assets


def _init_pygame() -> None:
    if not pygame.get_init():
        pygame.init()


def test_fog_cache_save_and_load_for_all_profiles(tmp_path, monkeypatch) -> None:
    _init_pygame()
    monkeypatch.setenv("ZOMBIE_ESCAPE_FOG_CACHE_DIR", str(tmp_path))
    assets = build_render_assets(DEFAULT_CELL_SIZE)

    for profile in _FogProfile:
        cache_path = save_fog_cache_profile(assets, profile)
        assert cache_path.exists()

        fog_data: dict[str, object] = {"hatch_patterns": {}, "overlays": {}}
        loaded = _get_fog_overlay_surfaces(fog_data, assets, profile)

        with np.load(cache_path) as data:
            hard_alpha = data["hard_alpha"]
            combined_alpha = data["combined_alpha"]
        loaded_hard_alpha = pg_surfarray.array_alpha(loaded["hard"]).T
        loaded_combined_alpha = pg_surfarray.array_alpha(loaded["combined"]).T

        assert np.array_equal(loaded_hard_alpha, hard_alpha)
        assert np.array_equal(loaded_combined_alpha, combined_alpha)
