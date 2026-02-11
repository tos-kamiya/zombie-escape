from __future__ import annotations

import math
from typing import Iterable, TYPE_CHECKING

import pygame

from ..entities_constants import (
    ZOMBIE_SIGHT_RANGE,
    ZOMBIE_TRACKER_FAR_SCENT_RADIUS,
    ZOMBIE_TRACKER_NEWER_FOOTPRINT_MS,
    ZOMBIE_TRACKER_RELOCK_DELAY_MS,
    ZOMBIE_TRACKER_SCENT_RADIUS,
    ZOMBIE_TRACKER_SCENT_TOP_K,
    ZOMBIE_TRACKER_SIGHT_RANGE,
    ZOMBIE_WALL_HUG_LOST_WALL_MS,
    ZOMBIE_WALL_HUG_PROBE_ANGLE_DEG,
    ZOMBIE_WALL_HUG_PROBE_STEP,
    ZOMBIE_WALL_HUG_SENSOR_DISTANCE,
    ZOMBIE_WALL_HUG_TARGET_GAP,
)
from ..gameplay.constants import FOOTPRINT_STEP_DISTANCE
from ..rng import get_rng
from .movement import _circle_wall_collision

if TYPE_CHECKING:
    from ..models import Footprint, LevelLayout
    from . import Wall, Zombie

RNG = get_rng()


def _line_of_sight_clear(
    start: tuple[float, float],
    end: tuple[float, float],
    walls: list["Wall"],
) -> bool:
    min_x = min(start[0], end[0])
    min_y = min(start[1], end[1])
    max_x = max(start[0], end[0])
    max_y = max(start[1], end[1])
    check_rect = pygame.Rect(
        int(min_x),
        int(min_y),
        max(1, int(max_x - min_x)),
        max(1, int(max_y - min_y)),
    )
    start_point = (int(start[0]), int(start[1]))
    end_point = (int(end[0]), int(end[1]))
    for wall in walls:
        if not wall.rect.colliderect(check_rect):
            continue
        if wall.rect.clipline(start_point, end_point):
            return False
    return True


def _zombie_tracker_movement(
    zombie: "Zombie",
    walls: list["Wall"],
    cell_size: int,
    layout: "LevelLayout",
    player_center: tuple[float, float],
    nearby_zombies: Iterable["Zombie"],
    footprints: list["Footprint"],
    *,
    now_ms: int,
) -> tuple[float, float]:
    now = now_ms
    is_in_sight = zombie._update_mode(player_center, ZOMBIE_TRACKER_SIGHT_RANGE)
    if not is_in_sight:
        if zombie.tracker_force_wander:
            last_target_time = zombie.tracker_target_time
            if last_target_time is None:
                last_target_time = now
            zombie.tracker_relock_after_time = (
                last_target_time + ZOMBIE_TRACKER_RELOCK_DELAY_MS
            )
            zombie.tracker_target_pos = None
            return _zombie_wander_movement(
                zombie,
                walls,
                cell_size,
                layout,
                now_ms=now,
            )
        _zombie_update_tracker_target(zombie, footprints, walls, now_ms=now)
        if zombie.tracker_target_pos is not None:
            return _zombie_move_toward(zombie, zombie.tracker_target_pos)
        return _zombie_wander_movement(
            zombie,
            walls,
            cell_size,
            layout,
            now_ms=now,
        )
    return _zombie_move_toward(zombie, player_center)


def _zombie_wall_hug_wall_distance(
    zombie: "Zombie",
    walls: list["Wall"],
    angle: float,
    max_distance: float,
    *,
    step: float = ZOMBIE_WALL_HUG_PROBE_STEP,
) -> float:
    direction_x = math.cos(angle)
    direction_y = math.sin(angle)
    max_search = max_distance + 120
    candidates = [
        wall
        for wall in walls
        if abs(wall.rect.centerx - zombie.x) < max_search
        and abs(wall.rect.centery - zombie.y) < max_search
    ]
    if not candidates:
        return max_distance
    distance = step
    while distance <= max_distance:
        check_x = zombie.x + direction_x * distance
        check_y = zombie.y + direction_y * distance
        if any(
            _circle_wall_collision(
                (check_x, check_y), zombie.collision_radius, wall
            )
            for wall in candidates
        ):
            return distance
        distance += step
    return max_distance


def _zombie_wall_hug_movement(
    zombie: "Zombie",
    walls: list["Wall"],
    cell_size: int,
    layout: "LevelLayout",
    player_center: tuple[float, float],
    _nearby_zombies: Iterable["Zombie"],
    _footprints: list["Footprint"],
    now_ms: int,
) -> tuple[float, float]:
    now = now_ms
    is_in_sight = zombie._update_mode(player_center, ZOMBIE_TRACKER_SIGHT_RANGE)
    if zombie.wall_hug_angle is None:
        zombie.wall_hug_angle = zombie.wander_angle
    if zombie.wall_hug_side == 0:
        sensor_distance = ZOMBIE_WALL_HUG_SENSOR_DISTANCE + zombie.collision_radius
        forward_angle = zombie.wall_hug_angle
        probe_offset = math.radians(ZOMBIE_WALL_HUG_PROBE_ANGLE_DEG)
        left_angle = forward_angle + probe_offset
        right_angle = forward_angle - probe_offset
        left_dist = _zombie_wall_hug_wall_distance(
            zombie, walls, left_angle, sensor_distance
        )
        right_dist = _zombie_wall_hug_wall_distance(
            zombie, walls, right_angle, sensor_distance
        )
        forward_dist = _zombie_wall_hug_wall_distance(
            zombie, walls, forward_angle, sensor_distance
        )
        left_wall = left_dist < sensor_distance
        right_wall = right_dist < sensor_distance
        forward_wall = forward_dist < sensor_distance
        if left_wall or right_wall or forward_wall:
            if left_wall and not right_wall:
                zombie.wall_hug_side = 1.0
            elif right_wall and not left_wall:
                zombie.wall_hug_side = -1.0
            elif left_wall and right_wall:
                zombie.wall_hug_side = 1.0 if left_dist <= right_dist else -1.0
            else:
                zombie.wall_hug_side = RNG.choice([-1.0, 1.0])
            zombie.wall_hug_last_wall_time = now
            zombie.wall_hug_last_side_has_wall = left_wall or right_wall
        else:
            if is_in_sight:
                return _zombie_move_toward(zombie, player_center)
            return _zombie_wander_movement(
                zombie,
                walls,
                cell_size,
                layout,
                now_ms=now_ms,
            )

    sensor_distance = ZOMBIE_WALL_HUG_SENSOR_DISTANCE + zombie.collision_radius
    probe_offset = math.radians(ZOMBIE_WALL_HUG_PROBE_ANGLE_DEG)
    side_angle = zombie.wall_hug_angle + zombie.wall_hug_side * probe_offset
    side_dist = _zombie_wall_hug_wall_distance(
        zombie, walls, side_angle, sensor_distance
    )
    forward_dist = _zombie_wall_hug_wall_distance(
        zombie, walls, zombie.wall_hug_angle, sensor_distance
    )
    side_has_wall = side_dist < sensor_distance
    forward_has_wall = forward_dist < sensor_distance
    wall_recent = (
        zombie.wall_hug_last_wall_time is not None
        and now - zombie.wall_hug_last_wall_time <= ZOMBIE_WALL_HUG_LOST_WALL_MS
    )
    if is_in_sight:
        return _zombie_move_toward(zombie, player_center)

    turn_step = math.radians(5)
    if side_has_wall or forward_has_wall:
        zombie.wall_hug_last_wall_time = now
    if side_has_wall:
        zombie.wall_hug_last_side_has_wall = True
        gap_error = ZOMBIE_WALL_HUG_TARGET_GAP - side_dist
        if abs(gap_error) > 0.1:
            ratio = min(1.0, abs(gap_error) / ZOMBIE_WALL_HUG_TARGET_GAP)
            turn = turn_step * ratio
            if gap_error > 0:
                zombie.wall_hug_angle -= zombie.wall_hug_side * turn
            else:
                zombie.wall_hug_angle += zombie.wall_hug_side * turn
        if forward_dist < ZOMBIE_WALL_HUG_TARGET_GAP:
            zombie.wall_hug_angle -= zombie.wall_hug_side * (turn_step * 1.5)
    else:
        zombie.wall_hug_last_side_has_wall = False
        if forward_has_wall:
            zombie.wall_hug_angle -= zombie.wall_hug_side * turn_step
        elif wall_recent:
            zombie.wall_hug_angle += zombie.wall_hug_side * (turn_step * 0.75)
        else:
            zombie.wall_hug_angle += zombie.wall_hug_side * (math.pi / 2.0)
            zombie.wall_hug_side = 0.0
    zombie.wall_hug_angle %= math.tau

    move_x = math.cos(zombie.wall_hug_angle) * zombie.speed
    move_y = math.sin(zombie.wall_hug_angle) * zombie.speed
    return move_x, move_y


def _zombie_normal_movement(
    zombie: "Zombie",
    walls: list["Wall"],
    cell_size: int,
    layout: "LevelLayout",
    player_center: tuple[float, float],
    _nearby_zombies: Iterable["Zombie"],
    _footprints: list["Footprint"],
    now_ms: int,
) -> tuple[float, float]:
    is_in_sight = zombie._update_mode(player_center, ZOMBIE_SIGHT_RANGE)
    if not is_in_sight:
        return _zombie_wander_movement(
            zombie,
            walls,
            cell_size,
            layout,
            now_ms=now_ms,
        )
    return _zombie_move_toward(zombie, player_center)


def _zombie_update_tracker_target(
    zombie: "Zombie",
    footprints: list["Footprint"],
    walls: list["Wall"],
    *,
    now_ms: int,
) -> None:
    # footprints are ordered oldest -> newest by time.
    now = now_ms
    if now - zombie.tracker_last_scan_time < zombie.tracker_scan_interval_ms:
        return
    zombie.tracker_last_scan_time = now
    if not footprints:
        zombie.tracker_target_pos = None
        return
    last_target_time = zombie.tracker_target_time
    far_radius_sq = ZOMBIE_TRACKER_FAR_SCENT_RADIUS * ZOMBIE_TRACKER_FAR_SCENT_RADIUS
    relock_after = zombie.tracker_relock_after_time
    far_candidates: list[tuple[float, Footprint]] = []
    for fp in footprints:
        dx = fp.pos[0] - zombie.x
        dy = fp.pos[1] - zombie.y
        d2 = dx * dx + dy * dy
        if d2 <= far_radius_sq:
            far_candidates.append((d2, fp))
    if not far_candidates:
        return
    latest_fp_time = far_candidates[-1][1].time
    use_far_scan = last_target_time is None or (
        latest_fp_time is not None
        and latest_fp_time - last_target_time >= ZOMBIE_TRACKER_NEWER_FOOTPRINT_MS
    )
    scan_radius = (
        ZOMBIE_TRACKER_FAR_SCENT_RADIUS if use_far_scan else ZOMBIE_TRACKER_SCENT_RADIUS
    )
    scent_radius_sq = scan_radius * scan_radius
    min_target_dist_sq = (FOOTPRINT_STEP_DISTANCE * 0.5) ** 2

    newer: list[Footprint] = []
    for d2, fp in far_candidates:
        pos = fp.pos
        fp_time = fp.time
        if relock_after is not None and fp_time < relock_after:
            continue
        if d2 <= min_target_dist_sq:
            continue
        if d2 <= scent_radius_sq:
            if last_target_time is None or fp_time > last_target_time:
                newer.append(fp)

    if not newer:
        return

    newer.sort(key=lambda fp: fp.time)

    if use_far_scan or last_target_time is None:
        candidates = list(reversed(newer))[:ZOMBIE_TRACKER_SCENT_TOP_K]
    else:
        newer_threshold = last_target_time + ZOMBIE_TRACKER_NEWER_FOOTPRINT_MS
        very_new = [fp for fp in newer if fp.time >= newer_threshold]
        if very_new:
            candidates = list(reversed(very_new))[:ZOMBIE_TRACKER_SCENT_TOP_K]
        else:
            candidates = newer[:ZOMBIE_TRACKER_SCENT_TOP_K]

    for fp in candidates:
        pos = fp.pos
        fp_time = fp.time
        if _line_of_sight_clear((zombie.x, zombie.y), pos, walls):
            zombie.tracker_target_pos = pos
            zombie.tracker_target_time = fp_time
            if relock_after is not None and fp_time >= relock_after:
                zombie.tracker_relock_after_time = None
            return

    if (
        zombie.tracker_target_pos is not None
        and (zombie.x - zombie.tracker_target_pos[0]) ** 2
        + (zombie.y - zombie.tracker_target_pos[1]) ** 2
        > min_target_dist_sq
    ):
        return

    if last_target_time is None:
        return

    next_fp = newer[0]
    zombie.tracker_target_pos = next_fp.pos
    zombie.tracker_target_time = next_fp.time
    if relock_after is not None and next_fp.time >= relock_after:
        zombie.tracker_relock_after_time = None
    return


def _zombie_wander_movement(
    zombie: "Zombie",
    walls: list["Wall"],
    cell_size: int,
    layout: "LevelLayout",
    *,
    now_ms: int,
) -> tuple[float, float]:
    grid_cols = layout.grid_cols
    grid_rows = layout.grid_rows
    outer_wall_cells = layout.outer_wall_cells
    pitfall_cells = layout.pitfall_cells
    now = now_ms
    changed_angle = False
    if now - zombie.last_wander_change_time > zombie.wander_change_interval:
        zombie.wander_angle = RNG.uniform(0, math.tau)
        zombie.last_wander_change_time = now
        jitter = RNG.randint(-500, 500)
        zombie.wander_change_interval = max(0, zombie.wander_interval_ms + jitter)
        changed_angle = True

    cell_x = int(zombie.x // cell_size)
    cell_y = int(zombie.y // cell_size)
    at_x_edge = cell_x in (0, grid_cols - 1)
    at_y_edge = cell_y in (0, grid_rows - 1)
    if changed_angle and (at_x_edge or at_y_edge):
        cos_angle = math.cos(zombie.wander_angle)
        sin_angle = math.sin(zombie.wander_angle)
        outward = (
            (cell_x == 0 and cos_angle < 0)
            or (cell_x == grid_cols - 1 and cos_angle > 0)
            or (cell_y == 0 and sin_angle < 0)
            or (cell_y == grid_rows - 1 and sin_angle > 0)
        )
        if outward:
            if RNG.random() < 0.5:
                zombie.wander_angle = (zombie.wander_angle + math.pi) % math.tau

    if at_x_edge or at_y_edge:
        if outer_wall_cells is not None:
            if at_x_edge:
                inward_cell = (1, cell_y) if cell_x == 0 else (grid_cols - 2, cell_y)
                if inward_cell not in outer_wall_cells:
                    target_x = (inward_cell[0] + 0.5) * cell_size
                    target_y = (inward_cell[1] + 0.5) * cell_size
                    return _zombie_move_toward(zombie, (target_x, target_y))
            if at_y_edge:
                inward_cell = (cell_x, 1) if cell_y == 0 else (cell_x, grid_rows - 2)
                if inward_cell not in outer_wall_cells:
                    target_x = (inward_cell[0] + 0.5) * cell_size
                    target_y = (inward_cell[1] + 0.5) * cell_size
                    return _zombie_move_toward(zombie, (target_x, target_y))
        else:

            def path_clear(next_x: float, next_y: float) -> bool:
                nearby_walls = [
                    wall
                    for wall in walls
                    if abs(wall.rect.centerx - next_x) < 120
                    and abs(wall.rect.centery - next_y) < 120
                ]
                return not any(
                    _circle_wall_collision(
                        (next_x, next_y), zombie.collision_radius, wall
                    )
                    for wall in nearby_walls
                )

            if at_x_edge:
                inward_dx = zombie.speed if cell_x == 0 else -zombie.speed
                if path_clear(zombie.x + inward_dx, zombie.y):
                    return inward_dx, 0.0
            if at_y_edge:
                inward_dy = zombie.speed if cell_y == 0 else -zombie.speed
                if path_clear(zombie.x, zombie.y + inward_dy):
                    return 0.0, inward_dy

    move_x = math.cos(zombie.wander_angle) * zombie.speed
    move_y = math.sin(zombie.wander_angle) * zombie.speed
    if pitfall_cells is not None:
        avoid_x, avoid_y = zombie._avoid_pitfalls(pitfall_cells, cell_size)
        move_x += avoid_x
        move_y += avoid_y
        if cell_size > 0:
            next_x = zombie.x + move_x
            next_y = zombie.y + move_y
            next_cell = (int(next_x // cell_size), int(next_y // cell_size))
            if next_cell in pitfall_cells:
                zombie.wander_angle = (zombie.wander_angle + math.pi) % math.tau
                move_x = math.cos(zombie.wander_angle) * zombie.speed
                move_y = math.sin(zombie.wander_angle) * zombie.speed
                avoid_x, avoid_y = zombie._avoid_pitfalls(pitfall_cells, cell_size)
                move_x += avoid_x
                move_y += avoid_y
                next_x = zombie.x + move_x
                next_y = zombie.y + move_y
                next_cell = (int(next_x // cell_size), int(next_y // cell_size))
                if next_cell in pitfall_cells:
                    return 0.0, 0.0
    return move_x, move_y


def _zombie_move_toward(
    zombie: "Zombie", target: tuple[float, float]
) -> tuple[float, float]:
    dx = target[0] - zombie.x
    dy = target[1] - zombie.y
    dist = math.hypot(dx, dy)
    if dist <= 0:
        return 0.0, 0.0
    return (dx / dist) * zombie.speed, (dy / dist) * zombie.speed
