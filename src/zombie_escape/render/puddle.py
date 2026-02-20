from __future__ import annotations

import math
from typing import Sequence

import pygame
from pygame import surface

from ..render_constants import PUDDLE_TILE_COLOR


def get_puddle_wave_color(
    *, alpha: int | None = 140
) -> tuple[int, int, int] | tuple[int, int, int, int]:
    base_color = PUDDLE_TILE_COLOR
    if alpha is None:
        return base_color
    return (*base_color, alpha)


def get_puddle_phase(elapsed_ms: int, x: int, y: int, *, cycle_ms: int = 360) -> int:
    phase_offset = (x + y) % 12
    return (elapsed_ms // max(1, cycle_ms)) + phase_offset


MoonlightReflectionSpec = tuple[float, float, float, float, float, float]

PUDDLE_MOONLIGHT_ALPHA = 210
PUDDLE_MOONLIGHT_CYCLE_MS = 360


MOONLIGHT_REFLECTION_SPECS: tuple[MoonlightReflectionSpec, ...] = (
    # cx, cy, base_radius_ratio, pulse_ratio, phase_offset_radians, brightness_ratio
    (0.18, 0.212, 0.2249, 0.0767, 4.5993, 0.8336),
    (0.356, 0.286, 0.248, 0.0655, 1.3572, 0.7928),
    (0.652, 0.612, 0.1974, 0.0572, 1.6588, 0.776),
    (0.914, 0.728, 0.4955, 0.05, 4.1595, 0.8216),
)


def draw_puddle_rings(
    target: surface.Surface,
    *,
    rect: pygame.Rect,
    phase: int,
    color: tuple[int, int, int] | tuple[int, int, int, int],
    width: int = 3,
    reflection_specs: Sequence[MoonlightReflectionSpec] | None = None,
) -> None:
    phase_i = int(phase) % 12
    base_w = rect.width
    base_h = rect.height
    rgb = color[:3]
    base_alpha = int(color[3]) if len(color) > 3 else 140
    overlay = pygame.Surface((base_w, base_h), pygame.SRCALPHA)
    base_radius_px = min(base_w, base_h)
    specs = reflection_specs if reflection_specs is not None else MOONLIGHT_REFLECTION_SPECS

    # 12-phase loop value in [0, 1).
    phase_t = phase_i / 12.0
    ring_width = max(1, int(width))

    for (cx, cy, radius_ratio, pulse_ratio, phase_offset, brightness_ratio) in specs:
        center = (int(base_w * cx), int(base_h * cy))
        phase_shift = (phase_offset / math.tau) % 1.0
        start_r = max(3.0, base_radius_px * max(0.05, radius_ratio * 0.28))
        expand_r = base_radius_px * max(0.10, pulse_ratio * 3.2 + radius_ratio * 0.58)
        strength = max(0.18, min(1.0, brightness_ratio))

        # Two staggered ripple rings per source.
        for ring_idx in range(2):
            progress = (phase_t + phase_shift + ring_idx * 0.5) % 1.0
            radius = int(start_r + expand_r * progress)
            alpha = int(base_alpha * strength * (1.0 - progress) * 0.40)
            alpha = max(0, min(220, alpha))
            if radius <= 0 or alpha <= 0:
                continue
            blob = pygame.Surface((base_w, base_h), pygame.SRCALPHA)
            pygame.draw.circle(blob, (*rgb, alpha), center, radius, ring_width)
            overlay.blit(blob, (0, 0), special_flags=pygame.BLEND_RGBA_ADD)

    target.blit(overlay, rect.topleft)
