from __future__ import annotations

from contextlib import contextmanager
from importlib import resources
from pathlib import Path
from typing import Iterator

import pygame

FONT_RESOURCE = "Silkscreen-Regular.ttf"
FONT_SCALE = 0.7


@contextmanager
def _font_path() -> Iterator[Path | None]:
    try:
        font = resources.files("zombie_escape").joinpath(
            "assets", "fonts", FONT_RESOURCE
        )
        with resources.as_file(font) as path:
            yield path
    except (FileNotFoundError, ModuleNotFoundError):
        yield None


def load_font(size: int) -> pygame.font.Font:
    scaled_size = max(1, round(size * FONT_SCALE))
    with _font_path() as path:
        if path is None:
            return pygame.font.Font(None, scaled_size)
        return pygame.font.Font(str(path), scaled_size)
