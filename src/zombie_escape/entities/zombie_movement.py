from __future__ import annotations

import math
from typing import Iterable, TYPE_CHECKING

import pygame

from ..entities_constants import (
    ZombieKind,
    ZOMBIE_SOLITARY_EVAL_INTERVAL_FRAMES,
    ZOMBIE_LINEFORMER_FOLLOW_DISTANCE,
    ZOMBIE_LINEFORMER_FOLLOW_TOLERANCE,
    ZOMBIE_LINEFORMER_SPEED_MULTIPLIER,
    ZOMBIE_SIGHT_RANGE,
    ZOMBIE_SPEED,
    ZOMBIE_TRACKER_SIGHT_RANGE,
    ZOMBIE_WALL_HUG_LOST_WALL_MS,
    ZOMBIE_WALL_HUG_PROBE_ANGLE_DEG,
    ZOMBIE_WALL_HUG_PROBE_ANGLE_PERP_DEG,
    ZOMBIE_WALL_HUG_TARGET_GAP,
    ZOMBIE_WALL_HUG_TURN_STEP_DEG,
    ZOMBIE_WANDER_HEADING_PLAYER_RANGE,
)
from ..rng import get_rng
from .movement import _circle_rect_collision
from .tracker_scent import update_tracker_target_from_footprints

if TYPE_CHECKING:
    from ..models import Footprint, LevelLayout
    from . import Zombie

RNG = get_rng()


def _set_wander_heading_toward_player_if_close(
    zombie: "Zombie",
    player_center: tuple[float, float] | None,
) -> None:
    if player_center is None:
        return
    dx = player_center[0] - zombie.x
    dy = player_center[1] - zombie.y
    dist_sq = dx * dx + dy * dy
    threshold = ZOMBIE_WANDER_HEADING_PLAYER_RANGE
    if dist_sq > threshold * threshold or dist_sq <= 1e-6:
        return
    zombie.wander_angle = math.atan2(dy, dx)


def _enter_wander(zombie: "Zombie") -> None:
    if zombie.is_wandering:
        return
    zombie.is_wandering = True
    zombie.just_entered_wander = True


def _leave_wander(zombie: "Zombie") -> None:
    zombie.is_wandering = False
    zombie.just_entered_wander = False


def _zombie_lineformer_train_head_movement(
    zombie: "Zombie",
    cell_size: int,
    layout: "LevelLayout",
    player_center: tuple[float, float],
    nearby_zombies: Iterable["Zombie"],
    _footprints: list["Footprint"],
    *,
    now_ms: int,
) -> tuple[float, float]:
    target_pos = zombie.lineformer_target_pos
    if target_pos is None:
        _enter_wander(zombie)
        return _zombie_wander_movement(
            zombie,
            cell_size,
            layout,
            now_ms=now_ms,
            player_center=player_center,
        )
    _leave_wander(zombie)
    dx = target_pos[0] - zombie.x
    dy = target_pos[1] - zombie.y
    distance_sq = dx * dx + dy * dy
    target_id = zombie.lineformer_follow_target_id
    if target_id is not None:
        target_entity = next(
            (
                other
                for other in nearby_zombies
                if getattr(other, "lineformer_id", None) == target_id
            ),
            None,
        )
        if target_entity is not None:
            target_radius = float(
                getattr(
                    target_entity,
                    "collision_radius",
                    getattr(target_entity, "radius", zombie.collision_radius),
                )
            )
            min_distance = zombie.collision_radius + target_radius
            if distance_sq <= min_distance * min_distance:
                away_dx = zombie.x - float(getattr(target_entity, "x", target_pos[0]))
                away_dy = zombie.y - float(getattr(target_entity, "y", target_pos[1]))
                away_dist = math.hypot(away_dx, away_dy)
                if away_dist <= 1e-6:
                    angle = RNG.uniform(0.0, math.tau)
                    away_dx, away_dy = math.cos(angle), math.sin(angle)
                    away_dist = 1.0
                repel_speed = zombie.speed * ZOMBIE_LINEFORMER_SPEED_MULTIPLIER
                return (
                    (away_dx / away_dist) * repel_speed,
                    (away_dy / away_dist) * repel_speed,
                )
    follow_max = ZOMBIE_LINEFORMER_FOLLOW_DISTANCE + ZOMBIE_LINEFORMER_FOLLOW_TOLERANCE
    if distance_sq <= follow_max * follow_max:
        return 0.0, 0.0
    move_x, move_y = _zombie_move_toward(zombie, target_pos)
    return (
        move_x * ZOMBIE_LINEFORMER_SPEED_MULTIPLIER,
        move_y * ZOMBIE_LINEFORMER_SPEED_MULTIPLIER,
    )


def _zombie_tracker_movement(
    zombie: "Zombie",
    cell_size: int,
    layout: "LevelLayout",
    player_center: tuple[float, float],
    _nearby_zombies: Iterable["Zombie"],
    footprints: list["Footprint"],
    *,
    now_ms: int,
) -> tuple[float, float]:
    now = now_ms
    is_in_sight = zombie._update_mode(player_center, ZOMBIE_TRACKER_SIGHT_RANGE)
    if not is_in_sight:
        _zombie_update_tracker_target(
            zombie,
            footprints,
            layout,
            cell_size=cell_size,
            now_ms=now,
            player_center=player_center,
        )
        if zombie.tracker_target_pos is not None:
            _leave_wander(zombie)
            return _zombie_move_toward(zombie, zombie.tracker_target_pos)
        _enter_wander(zombie)
        return _zombie_wander_movement(
            zombie,
            cell_size,
            layout,
            now_ms=now,
            player_center=player_center,
        )
    _leave_wander(zombie)
    return _zombie_move_toward(zombie, player_center)


def _zombie_wall_hug_wall_distance(
    zombie: "Zombie",
    angle: float,
    max_distance: float,
    *,
    blocked_cells: set[tuple[int, int]],
    cell_size: int,
    grid_cols: int,
    grid_rows: int,
) -> float:
    """Approximate distance to nearest blocked cell along the ray."""
    if cell_size <= 0 or not blocked_cells:
        return max_distance

    direction_x = math.cos(angle)
    direction_y = math.sin(angle)
    radius = zombie.collision_radius

    def _hits_blocked(sample_dist: float) -> bool:
        sample_x = zombie.x + direction_x * sample_dist
        sample_y = zombie.y + direction_y * sample_dist
        min_cell_x = max(0, int((sample_x - radius) // cell_size))
        max_cell_x = min(grid_cols - 1, int((sample_x + radius) // cell_size))
        min_cell_y = max(0, int((sample_y - radius) // cell_size))
        max_cell_y = min(grid_rows - 1, int((sample_y + radius) // cell_size))
        for cy in range(min_cell_y, max_cell_y + 1):
            for cx in range(min_cell_x, max_cell_x + 1):
                if (cx, cy) not in blocked_cells:
                    continue
                rect = pygame.Rect(cx * cell_size, cy * cell_size, cell_size, cell_size)
                if _circle_rect_collision((sample_x, sample_y), radius, rect):
                    return True
        return False

    step = max(1.0, min(cell_size * 0.25, max_distance))
    prev_dist = 0.0
    scan_dist = 0.0
    while scan_dist <= max_distance:
        if _hits_blocked(scan_dist):
            lo, hi = prev_dist, scan_dist
            for _ in range(5):
                mid = (lo + hi) * 0.5
                if _hits_blocked(mid):
                    hi = mid
                else:
                    lo = mid
            return hi
        prev_dist = scan_dist
        scan_dist += step
    return max_distance


def _wall_hug_blocked_cells(layout: "LevelLayout") -> set[tuple[int, int]]:
    blocked = set(layout.wall_cells)
    blocked.update(layout.outer_wall_cells)
    blocked.update(layout.steel_beam_cells)
    blocked.update(layout.fire_floor_cells)
    blocked.update(layout.material_cells)
    return blocked


def _zombie_wall_hug_movement(
    zombie: "Zombie",
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

    # Speed-based scaling factors
    speed_ratio = zombie.speed / ZOMBIE_SPEED if ZOMBIE_SPEED > 0 else 1.0

    # Non-linear scaling for sensor distance based on cell size.
    dynamic_sensor_dist = cell_size * (0.4 + 0.005 * cell_size)
    dynamic_sensor_dist *= 0.8 + 0.2 * speed_ratio

    # Angles for Asymmetrical Probes
    # 1. Forward (0)
    # 2. Side Diagonal (default 55, scales with speed)
    # 3. Side Perpendicular (90)
    angle_side_deg = ZOMBIE_WALL_HUG_PROBE_ANGLE_DEG * (speed_ratio**-0.2)
    angle_perp_deg = ZOMBIE_WALL_HUG_PROBE_ANGLE_PERP_DEG

    probe_offset_side = math.radians(min(75.0, angle_side_deg))
    probe_offset_perp = math.radians(angle_perp_deg)

    sensor_distance = dynamic_sensor_dist + zombie.collision_radius
    target_gap_diagonal = ZOMBIE_WALL_HUG_TARGET_GAP / math.cos(probe_offset_side)
    blocked_cells = _wall_hug_blocked_cells(layout)

    if zombie.wall_hug_side == 0:
        # Initial side discovery (still symmetrical for the very first frame)
        left_angle = zombie.wall_hug_angle + probe_offset_side
        right_angle = zombie.wall_hug_angle - probe_offset_side
        left_dist = _zombie_wall_hug_wall_distance(
            zombie,
            left_angle,
            sensor_distance,
            blocked_cells=blocked_cells,
            cell_size=cell_size,
            grid_cols=layout.grid_cols,
            grid_rows=layout.grid_rows,
        )
        right_dist = _zombie_wall_hug_wall_distance(
            zombie,
            right_angle,
            sensor_distance,
            blocked_cells=blocked_cells,
            cell_size=cell_size,
            grid_cols=layout.grid_cols,
            grid_rows=layout.grid_rows,
        )
        forward_dist = _zombie_wall_hug_wall_distance(
            zombie,
            zombie.wall_hug_angle,
            sensor_distance,
            blocked_cells=blocked_cells,
            cell_size=cell_size,
            grid_cols=layout.grid_cols,
            grid_rows=layout.grid_rows,
        )

        if (
            left_dist < sensor_distance
            or right_dist < sensor_distance
            or forward_dist < sensor_distance
        ):
            if left_dist <= right_dist:
                zombie.wall_hug_side = 1.0
            else:
                zombie.wall_hug_side = -1.0
            zombie.wall_hug_last_wall_time = now
        else:
            if is_in_sight:
                _leave_wander(zombie)
                return _zombie_move_toward(zombie, player_center)
            _enter_wander(zombie)
            return _zombie_wander_movement(zombie, cell_size, layout, now_ms=now_ms)

    # Asymmetrical Probing while following
    side_angle = zombie.wall_hug_angle + zombie.wall_hug_side * probe_offset_side
    perp_angle = zombie.wall_hug_angle + zombie.wall_hug_side * probe_offset_perp

    side_dist = _zombie_wall_hug_wall_distance(
        zombie,
        side_angle,
        sensor_distance,
        blocked_cells=blocked_cells,
        cell_size=cell_size,
        grid_cols=layout.grid_cols,
        grid_rows=layout.grid_rows,
    )
    perp_dist = _zombie_wall_hug_wall_distance(
        zombie,
        perp_angle,
        sensor_distance,
        blocked_cells=blocked_cells,
        cell_size=cell_size,
        grid_cols=layout.grid_cols,
        grid_rows=layout.grid_rows,
    )
    forward_dist = _zombie_wall_hug_wall_distance(
        zombie,
        zombie.wall_hug_angle,
        sensor_distance,
        blocked_cells=blocked_cells,
        cell_size=cell_size,
        grid_cols=layout.grid_cols,
        grid_rows=layout.grid_rows,
    )

    side_has_wall = side_dist < sensor_distance
    perp_has_wall = perp_dist < sensor_distance
    forward_has_wall = forward_dist < sensor_distance

    wall_recent = (
        zombie.wall_hug_last_wall_time is not None
        and now - zombie.wall_hug_last_wall_time <= ZOMBIE_WALL_HUG_LOST_WALL_MS
    )
    if is_in_sight:
        _leave_wander(zombie)
        return _zombie_move_toward(zombie, player_center)

    turn_step = math.radians(ZOMBIE_WALL_HUG_TURN_STEP_DEG * speed_ratio)

    if side_has_wall or perp_has_wall or forward_has_wall:
        zombie.wall_hug_last_wall_time = now

    # Steering Logic
    if perp_has_wall:
        # Obstacle is definitely there. Use diagonal for distance tracking.
        zombie.wall_hug_last_side_has_wall = True
        gap_error = target_gap_diagonal - side_dist
        if abs(gap_error) > 0.1:
            ratio = min(1.0, abs(gap_error) / target_gap_diagonal)
            turn = turn_step * ratio
            if gap_error > 0:
                zombie.wall_hug_angle -= zombie.wall_hug_side * turn
            else:
                zombie.wall_hug_angle += zombie.wall_hug_side * turn

        if forward_dist < ZOMBIE_WALL_HUG_TARGET_GAP:
            # Obstacle ahead! Turn sharply.
            zombie.wall_hug_angle -= zombie.wall_hug_side * (turn_step * 2.0)
    else:
        # PERPENDICULAR PROBE LOST WALL!
        # This means we either hit an outer corner or a GAP.
        zombie.wall_hug_last_side_has_wall = False
        if forward_has_wall:
            # Dead end? Turn away from forward wall.
            zombie.wall_hug_angle -= zombie.wall_hug_side * turn_step
        elif wall_recent:
            # Just lost it - turn sharply into the potential gap.
            zombie.wall_hug_angle += zombie.wall_hug_side * (turn_step * 1.2)
        else:
            # Completely lost - wander.
            zombie.wall_hug_angle += zombie.wall_hug_side * (math.pi / 2.0)
            zombie.wall_hug_side = 0.0
    zombie.wall_hug_angle %= math.tau

    move_x = math.cos(zombie.wall_hug_angle) * zombie.speed
    move_y = math.sin(zombie.wall_hug_angle) * zombie.speed
    _leave_wander(zombie)
    return move_x, move_y


def _zombie_normal_movement(
    zombie: "Zombie",
    cell_size: int,
    layout: "LevelLayout",
    player_center: tuple[float, float],
    _nearby_zombies: Iterable["Zombie"],
    _footprints: list["Footprint"],
    now_ms: int,
) -> tuple[float, float]:
    is_in_sight = zombie._update_mode(player_center, ZOMBIE_SIGHT_RANGE)
    if not is_in_sight:
        _enter_wander(zombie)
        return _zombie_wander_movement(
            zombie,
            cell_size,
            layout,
            now_ms=now_ms,
            player_center=player_center,
        )
    _leave_wander(zombie)
    return _zombie_move_toward(zombie, player_center)


def _zombie_solitary_movement(
    zombie: "Zombie",
    cell_size: int,
    _layout: "LevelLayout",
    player_center: tuple[float, float],
    nearby_zombies: Iterable["Zombie"],
    _footprints: list["Footprint"],
    *,
    now_ms: int,
) -> tuple[float, float]:
    del now_ms
    if cell_size <= 0:
        return 0.0, 0.0
    zombie_weight = 3
    player_weight = 1
    if zombie.solitary_eval_frame_counter <= 0:
        zombie.solitary_eval_frame_counter = ZOMBIE_SOLITARY_EVAL_INTERVAL_FRAMES

        self_cell_x = int(zombie.x // cell_size)
        self_cell_y = int(zombie.y // cell_size)
        up_count = 0
        down_count = 0
        left_count = 0
        right_count = 0

        for other in nearby_zombies:
            if other is zombie or not other.alive():
                continue
            if bool(getattr(other, "is_trapped", False)):
                continue
            if getattr(other, "kind", None) == ZombieKind.DOG:
                continue
            other_cell_x = int(other.x // cell_size)
            other_cell_y = int(other.y // cell_size)
            dx = other_cell_x - self_cell_x
            dy = other_cell_y - self_cell_y
            if abs(dx) > 1 or abs(dy) > 1:
                continue
            if dy == -1 and abs(dx) <= 1:
                up_count += zombie_weight
            if dy == 1 and abs(dx) <= 1:
                down_count += zombie_weight
            if dx == -1 and abs(dy) <= 1:
                left_count += zombie_weight
            if dx == 1 and abs(dy) <= 1:
                right_count += zombie_weight
        player_cell_x = int(player_center[0] // cell_size)
        player_cell_y = int(player_center[1] // cell_size)
        player_dx = player_cell_x - self_cell_x
        player_dy = player_cell_y - self_cell_y
        if abs(player_dx) <= 1 and abs(player_dy) <= 1:
            if player_dy == -1 and abs(player_dx) <= 1:
                up_count += player_weight
            if player_dy == 1 and abs(player_dx) <= 1:
                down_count += player_weight
            if player_dx == -1 and abs(player_dy) <= 1:
                left_count += player_weight
            if player_dx == 1 and abs(player_dy) <= 1:
                right_count += player_weight

        dir_x = 0
        dir_y = 0
        if up_count < down_count:
            dir_y = -1
        elif down_count < up_count:
            dir_y = 1
        if left_count < right_count:
            dir_x = -1
        elif right_count < left_count:
            dir_x = 1

        proposed_move: tuple[int, int] | None
        if dir_x == 0 and dir_y == 0:
            proposed_move = None
        else:
            proposed_move = (dir_x, dir_y)
        prev_move = zombie.solitary_previous_move
        if (
            proposed_move is not None
            and prev_move is not None
            and proposed_move == (-prev_move[0], -prev_move[1])
        ):
            proposed_move = None
        zombie.solitary_committed_move = proposed_move
        if proposed_move is not None:
            zombie.solitary_previous_move = proposed_move

    zombie.solitary_eval_frame_counter -= 1
    if zombie.solitary_committed_move is None:
        return 0.0, 0.0
    step_speed = zombie.speed * 2.2
    move_x = float(zombie.solitary_committed_move[0]) * step_speed
    move_y = float(zombie.solitary_committed_move[1]) * step_speed
    if move_x != 0.0 and move_y != 0.0:
        norm = math.sqrt(2.0)
        move_x /= norm
        move_y /= norm
    return move_x, move_y


def _zombie_update_tracker_target(
    zombie: "Zombie",
    footprints: list["Footprint"],
    layout: "LevelLayout",
    *,
    cell_size: int,
    now_ms: int,
    player_center: tuple[float, float] | None = None,
) -> None:
    _ = player_center
    update_tracker_target_from_footprints(
        zombie.tracker_state,
        origin=(zombie.x, zombie.y),
        footprints=footprints,
        layout=layout,
        cell_size=cell_size,
        now_ms=now_ms,
    )


def _zombie_wander_movement(
    zombie: "Zombie",
    cell_size: int,
    layout: "LevelLayout",
    *,
    now_ms: int,
    player_center: tuple[float, float] | None = None,
) -> None:
    grid_cols = layout.grid_cols
    grid_rows = layout.grid_rows
    outer_wall_cells = layout.outer_wall_cells
    pitfall_cells = layout.pitfall_cells
    fire_floor_cells = layout.fire_floor_cells
    now = now_ms
    changed_angle = False
    if zombie.just_entered_wander:
        _set_wander_heading_toward_player_if_close(zombie, player_center)
        zombie.just_entered_wander = False
        zombie.last_wander_change_time = now
    elif now - zombie.last_wander_change_time > zombie.wander_change_interval:
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

    def _base_move() -> tuple[float, float]:
        return (
            math.cos(zombie.wander_angle) * zombie.speed,
            math.sin(zombie.wander_angle) * zombie.speed,
        )

    move_x, move_y = _base_move()
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
                move_x, move_y = _base_move()
                avoid_x, avoid_y = zombie._avoid_pitfalls(pitfall_cells, cell_size)
                move_x += avoid_x
                move_y += avoid_y
                next_x = zombie.x + move_x
                next_y = zombie.y + move_y
                next_cell = (int(next_x // cell_size), int(next_y // cell_size))
                if next_cell in pitfall_cells:
                    return 0.0, 0.0
    if fire_floor_cells and cell_size > 0:
        next_x = zombie.x + move_x
        next_y = zombie.y + move_y
        next_cell = (int(next_x // cell_size), int(next_y // cell_size))
        if next_cell in fire_floor_cells:
            zombie.wander_angle = (zombie.wander_angle + math.pi) % math.tau
            move_x, move_y = _base_move()
            if pitfall_cells is not None:
                avoid_x, avoid_y = zombie._avoid_pitfalls(pitfall_cells, cell_size)
                move_x += avoid_x
                move_y += avoid_y
            next_x = zombie.x + move_x
            next_y = zombie.y + move_y
            next_cell = (int(next_x // cell_size), int(next_y // cell_size))
            if next_cell in fire_floor_cells:
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
