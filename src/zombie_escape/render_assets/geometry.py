from __future__ import annotations

import math


def build_beveled_polygon(
    width: int,
    height: int,
    depth: int,
    bevels: tuple[bool, bool, bool, bool],
) -> list[tuple[int, int]]:
    d = max(0, min(depth, width // 2, height // 2))
    if d == 0 or not any(bevels):
        return [(0, 0), (width, 0), (width, height), (0, height)]

    segments = 4
    tl, tr, br, bl = bevels
    points: list[tuple[int, int]] = []

    def _add_point(x: float, y: float) -> None:
        point = (int(round(x)), int(round(y)))
        if not points or points[-1] != point:
            points.append(point)

    def _add_arc(
        center_x: float,
        center_y: float,
        radius: float,
        start_deg: float,
        end_deg: float,
        *,
        skip_first: bool = False,
        skip_last: bool = False,
    ) -> None:
        for i in range(segments + 1):
            if skip_first and i == 0:
                continue
            if skip_last and i == segments:
                continue
            t = i / segments
            angle = math.radians(start_deg + (end_deg - start_deg) * t)
            _add_point(
                center_x + radius * math.cos(angle),
                center_y + radius * math.sin(angle),
            )

    _add_point(d if tl else 0, 0)
    if tr:
        _add_point(width - d, 0)
        _add_arc(width - d, d, d, -90, 0, skip_first=True)
    else:
        _add_point(width, 0)
    if br:
        _add_point(width, height - d)
        _add_arc(width - d, height - d, d, 0, 90, skip_first=True)
    else:
        _add_point(width, height)
    if bl:
        _add_point(d, height)
        _add_arc(d, height - d, d, 90, 180, skip_first=True)
    else:
        _add_point(0, height)
    if tl:
        _add_point(0, d)
        _add_arc(d, d, d, 180, 270, skip_first=True, skip_last=True)
    return points
