from __future__ import annotations

import math

from ..render_constants import ANGLE_BINS

ANGLE_STEP = math.tau / ANGLE_BINS


def brighten_color(
    color: tuple[int, int, int], *, factor: float = 1.125
) -> tuple[int, int, int]:
    return tuple(min(255, int(c * factor + 0.5)) for c in color)


def scale_color(color: tuple[int, int, int], *, ratio: float) -> tuple[int, int, int]:
    return tuple(max(0, min(255, int(c * ratio + 0.5))) for c in color)


def angle_bin_from_vector(
    dx: float, dy: float, *, bins: int = ANGLE_BINS
) -> int | None:
    if dx == 0 and dy == 0:
        return None
    angle = math.atan2(dy, dx)
    if angle < 0:
        angle += math.tau
    step = math.tau / bins
    return int(round(angle / step)) % bins
