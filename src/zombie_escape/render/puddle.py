from __future__ import annotations

import pygame
from pygame import surface

from ..render_constants import PUDDLE_TILE_COLOR


def get_puddle_wave_color(*, alpha: int | None = 140) -> tuple[int, int, int] | tuple[int, int, int, int]:
    base_color = (
        min(255, PUDDLE_TILE_COLOR[0] + 40),
        min(255, PUDDLE_TILE_COLOR[1] + 40),
        min(255, PUDDLE_TILE_COLOR[2] + 40),
    )
    if alpha is None:
        return base_color
    return (*base_color, alpha)


def get_puddle_phase(elapsed_ms: int, x: int, y: int, *, cycle_ms: int = 400) -> int:
    phase_offset = (x + y) % 4
    return (elapsed_ms // max(1, cycle_ms)) + phase_offset


def draw_puddle_rings(
    target: surface.Surface,
    *,
    rect: pygame.Rect,
    phase: int,
    color: tuple[int, int, int] | tuple[int, int, int, int],
    width: int = 1,
) -> None:
    wave_phase = int(phase) % 4
    base_wave_rect = rect.inflate(
        -int(rect.width * 0.3) - wave_phase,
        -int(rect.height * 0.4) - wave_phase,
    )
    for ring_idx in range(2):
        wave_offset = wave_phase + ring_idx * 2
        wave_rect = rect.inflate(
            -int(rect.width * 0.3) - wave_offset,
            -int(rect.height * 0.5) - wave_offset,
        )
        if wave_rect.width <= 0 or wave_rect.height <= 0:
            continue
        pygame.draw.ellipse(
            target,
            color,
            wave_rect,
            width=width,
        )

    border_rect = base_wave_rect.inflate(
        int(rect.width * 0.68),
        int(rect.height * 0.68),
    )
    if border_rect.width > 0 and border_rect.height > 0:
        pygame.draw.ellipse(
            target,
            color,
            border_rect,
            width=width,
        )
