from __future__ import annotations

import math
from typing import Iterable, Sequence, TYPE_CHECKING

import pygame
from pygame import rect

if TYPE_CHECKING:
    from . import Wall


def _can_humanoid_jump(
    x: float,
    y: float,
    dx: float,
    dy: float,
    jump_range: float,
    cell_size: int,
    walkable_cells: Iterable[tuple[int, int]],
) -> bool:
    """Accurately check if a jump is possible in the given movement direction."""
    move_len = math.hypot(dx, dy)
    if move_len <= 0:
        return False
    look_ahead_x = x + (dx / move_len) * jump_range
    look_ahead_y = y + (dy / move_len) * jump_range
    lax, lay = int(look_ahead_x // cell_size), int(look_ahead_y // cell_size)
    return (lax, lay) in walkable_cells


def _get_jump_scale(elapsed_ms: int, duration_ms: int, scale_max: float) -> float:
    """Calculate the parabolic scale factor for a jump."""
    t = max(0.0, min(1.0, elapsed_ms / duration_ms))
    return 1.0 + scale_max * (4 * t * (1 - t))


def _circle_rect_collision(
    center: tuple[float, float], radius: float, rect_obj: rect.Rect
) -> bool:
    """Return True if a circle overlaps the provided rectangle."""
    closest_x = max(rect_obj.left, min(center[0], rect_obj.right))
    closest_y = max(rect_obj.top, min(center[1], rect_obj.bottom))
    dx = center[0] - closest_x
    dy = center[1] - closest_y
    return dx * dx + dy * dy <= radius * radius


def _point_in_polygon(
    point: tuple[float, float], polygon: Sequence[tuple[float, float]]
) -> bool:
    x, y = point
    inside = False
    j = len(polygon) - 1
    for i, (px, py) in enumerate(polygon):
        qx, qy = polygon[j]
        if ((py > y) != (qy > y)) and (x < (qx - px) * (y - py) / (qy - py) + px):
            inside = not inside
        j = i
    return inside


def _segments_intersect(
    a1: tuple[float, float],
    a2: tuple[float, float],
    b1: tuple[float, float],
    b2: tuple[float, float],
) -> bool:
    def orient(
        p: tuple[float, float], q: tuple[float, float], r: tuple[float, float]
    ) -> float:
        return (q[1] - p[1]) * (r[0] - q[0]) - (q[0] - p[0]) * (r[1] - q[1])

    def on_segment(
        p: tuple[float, float], q: tuple[float, float], r: tuple[float, float]
    ) -> bool:
        return min(p[0], r[0]) <= q[0] <= max(p[0], r[0]) and min(p[1], r[1]) <= q[
            1
        ] <= max(p[1], r[1])

    o1 = orient(a1, a2, b1)
    o2 = orient(a1, a2, b2)
    o3 = orient(b1, b2, a1)
    o4 = orient(b1, b2, a2)

    if (o1 > 0) != (o2 > 0) and (o3 > 0) != (o4 > 0):
        return True
    if o1 == 0 and on_segment(a1, b1, a2):
        return True
    if o2 == 0 and on_segment(a1, b2, a2):
        return True
    if o3 == 0 and on_segment(b1, a1, b2):
        return True
    if o4 == 0 and on_segment(b1, a2, b2):
        return True
    return False


def _point_segment_distance_sq(
    point: tuple[float, float],
    seg_a: tuple[float, float],
    seg_b: tuple[float, float],
) -> float:
    px, py = point
    ax, ay = seg_a
    bx, by = seg_b
    dx = bx - ax
    dy = by - ay
    if dx == 0 and dy == 0:
        return (px - ax) ** 2 + (py - ay) ** 2
    t = ((px - ax) * dx + (py - ay) * dy) / (dx * dx + dy * dy)
    t = max(0.0, min(1.0, t))
    nearest_x = ax + t * dx
    nearest_y = ay + t * dy
    return (px - nearest_x) ** 2 + (py - nearest_y) ** 2


def _rect_polygon_collision(
    rect_obj: rect.Rect, polygon: Sequence[tuple[float, float]]
) -> bool:
    min_x = min(p[0] for p in polygon)
    max_x = max(p[0] for p in polygon)
    min_y = min(p[1] for p in polygon)
    max_y = max(p[1] for p in polygon)
    if not rect_obj.colliderect(
        pygame.Rect(min_x, min_y, max_x - min_x, max_y - min_y)
    ):
        return False

    rect_points = [
        (rect_obj.left, rect_obj.top),
        (rect_obj.right, rect_obj.top),
        (rect_obj.right, rect_obj.bottom),
        (rect_obj.left, rect_obj.bottom),
    ]
    if any(_point_in_polygon(p, polygon) for p in rect_points):
        return True
    if any(rect_obj.collidepoint(p) for p in polygon):
        return True

    rect_edges = [
        (rect_points[0], rect_points[1]),
        (rect_points[1], rect_points[2]),
        (rect_points[2], rect_points[3]),
        (rect_points[3], rect_points[0]),
    ]
    poly_edges = [
        (polygon[i], polygon[(i + 1) % len(polygon)]) for i in range(len(polygon))
    ]
    for edge_a in rect_edges:
        for edge_b in poly_edges:
            if _segments_intersect(edge_a[0], edge_a[1], edge_b[0], edge_b[1]):
                return True
    return False


def _circle_polygon_collision(
    center: tuple[float, float],
    radius: float,
    polygon: Sequence[tuple[float, float]],
) -> bool:
    if _point_in_polygon(center, polygon):
        return True
    radius_sq = radius * radius
    for i in range(len(polygon)):
        a = polygon[i]
        b = polygon[(i + 1) % len(polygon)]
        if _point_segment_distance_sq(center, a, b) <= radius_sq:
            return True
    return False


def _circle_wall_collision(
    center: tuple[float, float],
    radius: float,
    wall: "Wall",
) -> bool:
    if hasattr(wall, "_collides_circle"):
        return wall._collides_circle(center, radius)
    return _circle_rect_collision(center, radius, wall.rect)


def _zombie_update_tracker_target(
    zombie,
    footprints,
    walls,
) -> None:
    """Compatibility shim for tests; implementation lives in zombie_movement."""
    from .zombie_movement import _zombie_update_tracker_target as _impl

    _impl(zombie, footprints, walls)


def _zombie_wall_hug_movement(
    zombie,
    player_center,
    walls,
    nearby_zombies,
    footprints,
    cell_size,
    layout,
):
    """Compatibility shim for tests; implementation lives in zombie_movement."""
    from .zombie_movement import _zombie_wall_hug_movement as _impl

    return _impl(
        zombie,
        player_center,
        walls,
        nearby_zombies,
        footprints,
        cell_size,
        layout,
    )
