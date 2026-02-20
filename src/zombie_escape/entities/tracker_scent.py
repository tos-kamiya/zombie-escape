from __future__ import annotations

import math
from dataclasses import dataclass
from typing import TYPE_CHECKING

from ..entities_constants import (
    ZOMBIE_TRACKER_FAR_SCENT_RADIUS,
    ZOMBIE_TRACKER_LOST_TIMEOUT_MS,
    ZOMBIE_TRACKER_NEWER_FOOTPRINT_MS,
    ZOMBIE_TRACKER_SCAN_INTERVAL_MS,
    ZOMBIE_TRACKER_SCENT_RADIUS,
    ZOMBIE_TRACKER_SCENT_TOP_K,
)
from ..gameplay.constants import FOOTPRINT_STEP_DISTANCE

if TYPE_CHECKING:
    from ..models import Footprint, LevelLayout


@dataclass(slots=True)
class TrackerScentState:
    target_pos: tuple[float, float] | None = None
    target_time: int | None = None
    last_scan_time: int = 0
    scan_interval_ms: int = ZOMBIE_TRACKER_SCAN_INTERVAL_MS
    lost_timeout_ms: int = ZOMBIE_TRACKER_LOST_TIMEOUT_MS
    last_progress_ms: int | None = None
    ignore_before_or_at_time: int | None = None
    relock_after_time: int | None = None


def update_tracker_target_from_footprints(
    tracker_state: TrackerScentState,
    *,
    origin: tuple[float, float],
    footprints: list["Footprint"],
    layout: "LevelLayout",
    cell_size: int,
    now_ms: int,
) -> None:
    # footprints are ordered oldest -> newest by time.
    def _mark_tracker_lost(boundary_time: int | None) -> None:
        if boundary_time is not None:
            current_boundary = tracker_state.ignore_before_or_at_time
            if current_boundary is None or boundary_time > current_boundary:
                tracker_state.ignore_before_or_at_time = boundary_time
        tracker_state.target_pos = None
        tracker_state.target_time = None
        tracker_state.last_progress_ms = None

    relock_after = tracker_state.relock_after_time

    def _is_eligible_time(fp_time: int) -> bool:
        ignore_before_or_at = tracker_state.ignore_before_or_at_time
        if ignore_before_or_at is not None and fp_time <= ignore_before_or_at:
            return False
        if relock_after is not None and fp_time < relock_after:
            return False
        return True

    now = now_ms
    if now - tracker_state.last_scan_time < tracker_state.scan_interval_ms:
        return
    tracker_state.last_scan_time = now
    last_target_time = tracker_state.target_time
    if last_target_time is not None and tracker_state.last_progress_ms is None:
        tracker_state.last_progress_ms = now

    has_newer_footprint = False
    if last_target_time is not None:
        has_newer_footprint = any(
            fp.time > last_target_time and _is_eligible_time(fp.time) for fp in footprints
        )
        if has_newer_footprint:
            tracker_state.last_progress_ms = now
        else:
            last_progress_ms = tracker_state.last_progress_ms
            if last_progress_ms is not None and (
                now - last_progress_ms >= tracker_state.lost_timeout_ms
            ):
                _mark_tracker_lost(last_target_time)
                return

    if not footprints:
        return

    far_radius_sq = ZOMBIE_TRACKER_FAR_SCENT_RADIUS * ZOMBIE_TRACKER_FAR_SCENT_RADIUS
    far_candidates: list[tuple[float, Footprint]] = []
    for fp in footprints:
        if not _is_eligible_time(fp.time):
            continue
        dx = fp.pos[0] - origin[0]
        dy = fp.pos[1] - origin[1]
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

    blocked_cells = tracker_blocked_cells(layout)
    for fp in candidates:
        pos = fp.pos
        fp_time = fp.time
        if line_of_sight_clear_cells(
            origin,
            pos,
            blocked_cells=blocked_cells,
            cell_size=cell_size,
            grid_cols=layout.grid_cols,
            grid_rows=layout.grid_rows,
        ):
            old_target_time = tracker_state.target_time
            tracker_state.target_pos = pos
            tracker_state.target_time = fp_time
            if old_target_time is None or fp_time > old_target_time:
                tracker_state.last_progress_ms = now
            if relock_after is not None and fp_time >= relock_after:
                tracker_state.relock_after_time = None
            return

    if (
        tracker_state.target_pos is not None
        and (origin[0] - tracker_state.target_pos[0]) ** 2
        + (origin[1] - tracker_state.target_pos[1]) ** 2
        > min_target_dist_sq
    ):
        return

    if last_target_time is None:
        return

    next_fp = newer[0]
    old_target_time = tracker_state.target_time
    tracker_state.target_pos = next_fp.pos
    tracker_state.target_time = next_fp.time
    if old_target_time is None or next_fp.time > old_target_time:
        tracker_state.last_progress_ms = now
    if relock_after is not None and next_fp.time >= relock_after:
        tracker_state.relock_after_time = None


def line_of_sight_clear_cells(
    start: tuple[float, float],
    end: tuple[float, float],
    *,
    blocked_cells: set[tuple[int, int]],
    cell_size: int,
    grid_cols: int,
    grid_rows: int,
) -> bool:
    if cell_size <= 0 or not blocked_cells:
        return True
    dx = end[0] - start[0]
    dy = end[1] - start[1]
    dist = math.hypot(dx, dy)
    if dist <= 1e-6:
        return True
    step = max(1.0, min(cell_size * 0.5, dist))
    samples = max(1, int(math.ceil(dist / step)))
    for i in range(samples + 1):
        t = i / samples
        x = start[0] + dx * t
        y = start[1] + dy * t
        cx = int(x // cell_size)
        cy = int(y // cell_size)
        if cx < 0 or cy < 0 or cx >= grid_cols or cy >= grid_rows:
            continue
        if (cx, cy) in blocked_cells:
            return False
    return True


def tracker_blocked_cells(layout: "LevelLayout") -> set[tuple[int, int]]:
    blocked = set(layout.wall_cells)
    blocked.update(layout.outer_wall_cells)
    blocked.update(layout.steel_beam_cells)
    return blocked

