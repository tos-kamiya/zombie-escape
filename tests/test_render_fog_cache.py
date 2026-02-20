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
        cache_paths = save_fog_cache_profile(assets, profile)
        assert len(cache_paths) == 2
        for cache_path in cache_paths:
            assert cache_path.exists()
            assert cache_path.suffix == ".png"
            assert ".v1.png" in cache_path.name

        fog_data: dict[str, object] = {"hatch_patterns": {}, "overlays": {}}
        loaded = _get_fog_overlay_surfaces(fog_data, assets, profile)

        hard_path = next(path for path in cache_paths if "_hard." in path.name)
        combined_path = next(path for path in cache_paths if "_combined." in path.name)
        hard_alpha = pg_surfarray.array_alpha(pygame.image.load(str(hard_path))).T
        combined_alpha = pg_surfarray.array_alpha(pygame.image.load(str(combined_path))).T
        loaded_hard_alpha = pg_surfarray.array_alpha(loaded["hard"]).T
        loaded_combined_alpha = pg_surfarray.array_alpha(loaded["combined"]).T

        assert np.array_equal(loaded_hard_alpha, hard_alpha)
        assert np.array_equal(loaded_combined_alpha, combined_alpha)
