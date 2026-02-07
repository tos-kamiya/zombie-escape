from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

import pygame
import numpy as np  # type: ignore

from ..entities_constants import (
    ZOMBIE_DOG_LONG_AXIS_RATIO,
    ZOMBIE_DOG_SHORT_AXIS_RATIO,
    ZOMBIE_RADIUS,
)
from ..render_assets import (
    build_zombie_directional_surfaces,
    build_zombie_dog_directional_surfaces,
)
from ..screen_constants import FPS
from ..rng import get_rng

RNG = get_rng()


DECAY_EFFECT_DURATION_FRAMES = max(1, int(FPS))


@dataclass(frozen=True)
class DecayMask:
    width: int
    height: int
    positions: list[tuple[int, int]]


_DECAY_MASK: DecayMask | None = None


def _max_decay_surface_size() -> tuple[int, int]:
    zombie_surfaces = build_zombie_directional_surfaces(ZOMBIE_RADIUS, draw_hands=False)
    base_size = ZOMBIE_RADIUS * 2.0
    long_axis = base_size * ZOMBIE_DOG_LONG_AXIS_RATIO
    short_axis = base_size * ZOMBIE_DOG_SHORT_AXIS_RATIO
    dog_surfaces = build_zombie_dog_directional_surfaces(long_axis, short_axis)
    widths = [surf.get_width() for surf in zombie_surfaces + dog_surfaces]
    heights = [surf.get_height() for surf in zombie_surfaces + dog_surfaces]
    return max(widths), max(heights)


def _build_decay_mask() -> DecayMask:
    width, height = _max_decay_surface_size()
    positions = [(x, y) for y in range(height) for x in range(width)]
    RNG.shuffle(positions)
    return DecayMask(width=width, height=height, positions=positions)


def prepare_decay_mask() -> DecayMask:
    global _DECAY_MASK
    if _DECAY_MASK is None:
        _DECAY_MASK = _build_decay_mask()
    return _DECAY_MASK


def get_decay_mask() -> DecayMask:
    return prepare_decay_mask()


class DecayingEntityEffect:
    def __init__(
        self,
        image: pygame.Surface,
        center: tuple[int, int],
        *,
        duration_frames: int = DECAY_EFFECT_DURATION_FRAMES,
        mask: DecayMask | None = None,
    ) -> None:
        self.surface = image.copy()
        self.surface = self.surface.convert_alpha()
        self._apply_grayscale()
        self.rect = self.surface.get_rect(center=center)
        self.duration_frames = max(1, int(duration_frames))
        self.frames_elapsed = 0
        self.mask = mask or get_decay_mask()
        self.mask_index = 0
        self.pixel_carry = 0.0
        self.pixels_per_frame = len(self.mask.positions) / self.duration_frames

    def update(self, *, frames: int = 1) -> bool:
        if frames <= 0:
            return True
        for _ in range(frames):
            if self.frames_elapsed >= self.duration_frames:
                return False
            self.frames_elapsed += 1
            self.pixel_carry += self.pixels_per_frame
            remove_count = int(self.pixel_carry)
            if remove_count <= 0:
                continue
            self.pixel_carry -= remove_count
            self._erase_pixels(remove_count)
        return self.frames_elapsed < self.duration_frames

    def _erase_pixels(self, count: int) -> None:
        width, height = self.surface.get_size()
        for _ in range(count):
            if self.mask_index >= len(self.mask.positions):
                return
            x, y = self.mask.positions[self.mask_index]
            self.mask_index += 1
            if x >= width or y >= height:
                continue
            self.surface.set_at((x, y), (0, 0, 0, 0))

    def _apply_grayscale(self) -> None:
        rgb = pygame.surfarray.pixels3d(self.surface)
        alpha = pygame.surfarray.pixels_alpha(self.surface)
        gray = (0.299 * rgb[:, :, 0] + 0.587 * rgb[:, :, 1] + 0.114 * rgb[:, :, 2]).astype(
            np.uint8
        )
        rgb[:, :, 0] = gray
        rgb[:, :, 1] = gray
        rgb[:, :, 2] = gray
        del rgb, alpha


def update_decay_effects(effects: list[DecayingEntityEffect], *, frames: int = 1) -> None:
    if not effects:
        return
    alive: list[DecayingEntityEffect] = []
    for effect in effects:
        if effect.update(frames=frames):
            alive.append(effect)
    effects[:] = alive


def iter_decay_effects(effects: Iterable[DecayingEntityEffect]) -> Iterable[DecayingEntityEffect]:
    return effects
