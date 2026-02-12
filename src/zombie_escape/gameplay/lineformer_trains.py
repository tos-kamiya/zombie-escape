from __future__ import annotations

import math
from collections import deque
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from ..entities import Zombie
from ..entities.zombie_movement import _zombie_lineformer_train_head_movement
from ..entities_constants import (
    FAST_ZOMBIE_BASE_SPEED,
    PLAYER_SPEED,
    ZOMBIE_DECAY_DURATION_FRAMES,
    ZOMBIE_LINEFORMER_DISSOLVE_SPAWN_MS,
    ZOMBIE_LINEFORMER_JOIN_RADIUS,
    ZOMBIE_LINEFORMER_SPEED_MULTIPLIER,
    ZOMBIE_SPEED,
    ZombieKind,
)
from .constants import LAYER_ZOMBIES, MAX_ZOMBIES
from ..rng import get_rng

if TYPE_CHECKING:  # pragma: no cover - typing-only imports
    from ..models import GameData

RNG = get_rng()
_MARKER_HISTORY_SAMPLE_GAP = 10
_MARKER_HISTORY_RECORD_MANHATTAN_THRESHOLD = 2.0
_MARKER_DRAW_SHIFT_ALPHA = 0.45
_MARKER_DRAW_SHIFT_MAX = ZOMBIE_LINEFORMER_JOIN_RADIUS


@dataclass
class LineformerTrain:
    train_id: int
    head_id: int
    target_id: int | None = None
    marker_positions: list[tuple[float, float]] = field(default_factory=list)
    marker_angles: list[float] = field(default_factory=list)
    history: deque[tuple[float, float]] = field(default_factory=lambda: deque(maxlen=128))
    state: str = "active"  # active | dissolving
    next_dissolve_ms: int = 0


class LineformerTrainManager:
    def __init__(self) -> None:
        self._next_train_id = 1
        self.trains: dict[int, LineformerTrain] = {}
        self.target_to_train: dict[int, int] = {}

    def _iter_non_lineformer_targets(
        self,
        zombie_group,
    ) -> list[Zombie]:
        return [
            zombie
            for zombie in zombie_group
            if isinstance(zombie, Zombie)
            and zombie.alive()
            and zombie.kind != ZombieKind.LINEFORMER
        ]

    def _find_nearest_target(
        self,
        pos: tuple[float, float],
        targets: list[Zombie],
        *,
        excluded_target_ids: set[int] | None = None,
    ) -> Zombie | None:
        best: Zombie | None = None
        best_dist_sq = ZOMBIE_LINEFORMER_JOIN_RADIUS * ZOMBIE_LINEFORMER_JOIN_RADIUS
        px, py = pos
        excluded = excluded_target_ids or set()
        for target in targets:
            if target.lineformer_id in excluded:
                continue
            dx = target.x - px
            dy = target.y - py
            dist_sq = dx * dx + dy * dy
            if dist_sq <= best_dist_sq:
                best = target
                best_dist_sq = dist_sq
        return best

    def _rebuild_target_index(self) -> None:
        self.target_to_train.clear()
        for train in self.trains.values():
            if train.state != "active":
                continue
            if train.target_id is None:
                continue
            self.target_to_train[train.target_id] = train.train_id

    def resolve_spawn_target(
        self,
        zombie_group,
        start_pos: tuple[float, float],
    ) -> tuple[int | None, int | None]:
        self._rebuild_target_index()
        targets = self._iter_non_lineformer_targets(zombie_group)
        target = self._find_nearest_target(start_pos, targets)
        if target is None:
            return None, None
        target_id = target.lineformer_id
        train_id = self.target_to_train.get(target_id)
        if train_id is not None:
            return train_id, None
        return None, target_id

    def _ensure_history_capacity(self, train: LineformerTrain, *, sample_step: int | None = None) -> None:
        marker_count = max(0, len(train.marker_positions))
        step = _MARKER_HISTORY_SAMPLE_GAP if sample_step is None else max(1, sample_step)
        required = max(64, (marker_count + 2) * step + 8)
        if train.history.maxlen is not None and train.history.maxlen >= required:
            return
        train.history = deque(train.history, maxlen=required)

    def append_marker(self, train_id: int, pos: tuple[float, float]) -> bool:
        train = self.trains.get(train_id)
        if train is None:
            return False
        x, y = float(pos[0]), float(pos[1])
        train.marker_positions.append((x, y))
        train.marker_angles.append(0.0)
        self._ensure_history_capacity(train)
        return True

    def get_train_head(self, train_id: int, zombie_group) -> Zombie | None:
        train = self.trains.get(train_id)
        if train is None:
            return None
        for zombie in zombie_group:
            if (
                isinstance(zombie, Zombie)
                and zombie.alive()
                and zombie.lineformer_id == train.head_id
            ):
                return zombie
        return None

    def create_train_for_head(
        self,
        head: Zombie,
        *,
        target_id: int | None,
        now_ms: int,
    ) -> int:
        train_id = self._next_train_id
        self._next_train_id += 1
        train = LineformerTrain(
            train_id=train_id,
            head_id=head.lineformer_id,
            target_id=target_id,
        )
        train.history.append((head.x, head.y))
        self.trains[train_id] = train
        setattr(head, "lineformer_train_id", train_id)
        head.lineformer_follow_target_id = target_id
        head.lineformer_last_target_seen_ms = now_ms if target_id is not None else None
        return train_id

    def _start_dissolving(self, train: LineformerTrain, *, now_ms: int) -> None:
        train.state = "dissolving"
        train.next_dissolve_ms = now_ms
        train.target_id = None

    def _spawn_lineformer_head(
        self,
        game_data: "GameData",
        *,
        pos: tuple[float, float],
        config: dict,
    ) -> Zombie:
        stage = game_data.stage
        fast_conf = config.get("fast_zombies", {})
        fast_enabled = fast_conf.get("enabled", True)
        if fast_enabled:
            base_speed = RNG.uniform(ZOMBIE_SPEED, FAST_ZOMBIE_BASE_SPEED)
        else:
            base_speed = ZOMBIE_SPEED
        base_speed *= ZOMBIE_LINEFORMER_SPEED_MULTIPLIER
        base_speed = min(base_speed, PLAYER_SPEED - 0.05)
        decay_duration_frames = max(
            1.0,
            float(stage.zombie_decay_duration_frames)
            if stage is not None
            else float(ZOMBIE_DECAY_DURATION_FRAMES),
        )
        return Zombie(
            x=float(pos[0]),
            y=float(pos[1]),
            speed=base_speed,
            kind=ZombieKind.LINEFORMER,
            movement_strategy=_zombie_lineformer_train_head_movement,
            decay_duration_frames=decay_duration_frames,
        )

    def _promote_one_marker(
        self,
        train: LineformerTrain,
        *,
        game_data: "GameData",
        config: dict,
        now_ms: int,
    ) -> None:
        if not train.marker_positions:
            self.trains.pop(train.train_id, None)
            return
        if len(game_data.groups.zombie_group) >= MAX_ZOMBIES:
            train.next_dissolve_ms = now_ms + ZOMBIE_LINEFORMER_DISSOLVE_SPAWN_MS
            return
        pos = train.marker_positions.pop(0)
        if train.marker_angles:
            train.marker_angles.pop(0)
        new_head = self._spawn_lineformer_head(game_data, pos=pos, config=config)
        game_data.groups.zombie_group.add(new_head)
        game_data.groups.all_sprites.add(new_head, layer=LAYER_ZOMBIES)
        self.create_train_for_head(new_head, target_id=None, now_ms=now_ms)
        train.next_dissolve_ms = now_ms + ZOMBIE_LINEFORMER_DISSOLVE_SPAWN_MS
        if not train.marker_positions:
            self.trains.pop(train.train_id, None)

    def _merge_train_into(
        self,
        src_train: LineformerTrain,
        dst_train: LineformerTrain,
        *,
        heads: dict[int, Zombie],
    ) -> None:
        if src_train.train_id == dst_train.train_id:
            return
        src_head = heads.get(src_train.head_id)
        if src_head is not None and src_head.alive():
            dst_train.marker_positions.append((src_head.x, src_head.y))
            dst_train.marker_angles.append(0.0)
            src_head.kill()
        if src_train.marker_positions:
            dst_train.marker_positions.extend(src_train.marker_positions)
            dst_train.marker_angles.extend(
                [0.0 for _ in range(len(src_train.marker_positions))]
            )
        self._ensure_history_capacity(dst_train)
        self.trains.pop(src_train.train_id, None)

    def _train_length(self, train: LineformerTrain) -> int:
        return 1 + len(train.marker_positions)

    def _train_tail_position(
        self,
        train: LineformerTrain,
        *,
        heads: dict[int, Zombie],
    ) -> tuple[float, float] | None:
        if train.marker_positions:
            return train.marker_positions[-1]
        head = heads.get(train.head_id)
        if head is None:
            return None
        return (head.x, head.y)

    def pre_update(self, game_data: "GameData", *, config: dict, now_ms: int) -> None:
        zombie_group = game_data.groups.zombie_group
        targets = self._iter_non_lineformer_targets(zombie_group)
        target_by_id = {z.lineformer_id: z for z in targets}
        heads = {
            z.lineformer_id: z
            for z in zombie_group
            if isinstance(z, Zombie)
            and z.alive()
            and z.kind == ZombieKind.LINEFORMER
            and getattr(z, "lineformer_train_id", None) is not None
        }
        self._rebuild_target_index()

        for train in list(self.trains.values()):
            if train.train_id not in self.trains:
                continue
            head = heads.get(train.head_id)
            if head is None:
                self._start_dissolving(train, now_ms=now_ms)
            elif train.state == "active":
                is_sole_train = self._train_length(train) == 1
                target = target_by_id.get(train.target_id) if train.target_id is not None else None
                if target is None:
                    reserved_targets = {
                        target_id
                        for target_id, owner_train_id in self.target_to_train.items()
                        if owner_train_id != train.train_id
                    }
                    if is_sole_train:
                        target = self._find_nearest_target(
                            (head.x, head.y),
                            targets,
                            excluded_target_ids=reserved_targets,
                        )
                        # Fallback for merge behavior:
                        # a lone train may temporarily lock onto a reserved target so it
                        # can merge when it reaches the other train's tail.
                        if target is None:
                            target = self._find_nearest_target((head.x, head.y), targets)
                    else:
                        target = self._find_nearest_target((head.x, head.y), targets)
                    train.target_id = target.lineformer_id if target is not None else None
                head.lineformer_follow_target_id = train.target_id
                if target is not None:
                    owner_train_id = self.target_to_train.get(target.lineformer_id)
                    if owner_train_id is not None and owner_train_id != train.train_id:
                        dst_train = self.trains.get(owner_train_id)
                        if dst_train is not None and dst_train.state == "active":
                            # Merge only when this train is a lone head and close to the
                            # destination train's tail to avoid visible teleport jumps.
                            if self._train_length(train) == 1:
                                tail_pos = self._train_tail_position(dst_train, heads=heads)
                                if tail_pos is not None:
                                    dx = tail_pos[0] - head.x
                                    dy = tail_pos[1] - head.y
                                    if dx * dx + dy * dy <= (
                                        ZOMBIE_LINEFORMER_JOIN_RADIUS
                                        * ZOMBIE_LINEFORMER_JOIN_RADIUS
                                    ):
                                        self._merge_train_into(train, dst_train, heads=heads)
                                        continue
                        train.target_id = None
                        head.lineformer_follow_target_id = None
                        head.lineformer_target_pos = None
                        head.lineformer_last_target_seen_ms = None
                        if train.marker_positions:
                            self._start_dissolving(train, now_ms=now_ms)
                        continue
                    head.lineformer_target_pos = (target.x, target.y)
                    head.lineformer_last_target_seen_ms = now_ms
                else:
                    head.lineformer_target_pos = None
                    head.lineformer_last_target_seen_ms = None
                    if train.marker_positions:
                        self._start_dissolving(train, now_ms=now_ms)
            if train.state == "dissolving" and now_ms >= train.next_dissolve_ms:
                self._promote_one_marker(train, game_data=game_data, config=config, now_ms=now_ms)
        self._rebuild_target_index()

    def post_update(self, zombie_group) -> None:
        heads = {
            z.lineformer_id: z
            for z in zombie_group
            if isinstance(z, Zombie)
            and z.alive()
            and z.kind == ZombieKind.LINEFORMER
            and getattr(z, "lineformer_train_id", None) is not None
        }
        for train in list(self.trains.values()):
            if train.state != "active":
                continue
            head = heads.get(train.head_id)
            if head is None:
                continue
            sample_step = _MARKER_HISTORY_SAMPLE_GAP
            current_pos = (head.x, head.y)
            if not train.history:
                train.history.append(current_pos)
            else:
                last_x, last_y = train.history[-1]
                manhattan = abs(current_pos[0] - last_x) + abs(current_pos[1] - last_y)
                if manhattan > _MARKER_HISTORY_RECORD_MANHATTAN_THRESHOLD:
                    train.history.append(current_pos)
            self._ensure_history_capacity(train, sample_step=sample_step)
            if not train.marker_positions:
                continue
            history_list = list(train.history)
            if not history_list:
                history_list = [(head.x, head.y)]
            newest_idx = len(history_list) - 1
            for idx in range(len(train.marker_positions)):
                sample_index = max(0, newest_idx - (idx + 1) * sample_step)
                marker_pos = history_list[sample_index]
                train.marker_positions[idx] = marker_pos
                lead_pos = (head.x, head.y) if idx == 0 else train.marker_positions[idx - 1]
                dx = lead_pos[0] - marker_pos[0]
                dy = lead_pos[1] - marker_pos[1]
                if dx == 0 and dy == 0:
                    angle = 0.0
                else:
                    angle = math.atan2(dy, dx)
                if idx < len(train.marker_angles):
                    train.marker_angles[idx] = angle
                else:
                    train.marker_angles.append(angle)

    def iter_marker_draw_data(self, zombie_group) -> list[tuple[float, float, float]]:
        draw_data: list[tuple[float, float, float]] = []
        heads = {
            z.lineformer_id: z
            for z in zombie_group
            if isinstance(z, Zombie)
            and z.alive()
            and z.kind == ZombieKind.LINEFORMER
            and getattr(z, "lineformer_train_id", None) is not None
        }
        for train in self.trains.values():
            shift_x = 0.0
            shift_y = 0.0
            if train.marker_positions:
                head = heads.get(train.head_id)
                if head is not None:
                    base_x, base_y = train.marker_positions[0]
                    shift_x = (head.x - base_x) * _MARKER_DRAW_SHIFT_ALPHA
                    shift_y = (head.y - base_y) * _MARKER_DRAW_SHIFT_ALPHA
                    shift_dist = math.hypot(shift_x, shift_y)
                    if shift_dist > _MARKER_DRAW_SHIFT_MAX and shift_dist > 0:
                        scale = _MARKER_DRAW_SHIFT_MAX / shift_dist
                        shift_x *= scale
                        shift_y *= scale
            for idx, marker_pos in enumerate(train.marker_positions):
                angle = train.marker_angles[idx] if idx < len(train.marker_angles) else 0.0
                draw_data.append((marker_pos[0] + shift_x, marker_pos[1] + shift_y, angle))
        return draw_data

    def total_marker_count(self) -> int:
        return sum(len(train.marker_positions) for train in self.trains.values())

    def any_marker_collides_circle(
        self,
        *,
        center: tuple[float, float],
        radius: float,
    ) -> bool:
        radius_sq = radius * radius
        cx, cy = center
        for train in self.trains.values():
            for mx, my in train.marker_positions:
                dx = mx - cx
                dy = my - cy
                if dx * dx + dy * dy <= radius_sq:
                    return True
        return False

    def pop_markers_colliding_circle(
        self,
        *,
        center: tuple[float, float],
        radius: float,
    ) -> int:
        removed = 0
        radius_sq = radius * radius
        cx, cy = center
        for train in self.trains.values():
            if not train.marker_positions:
                continue
            survivors_pos: list[tuple[float, float]] = []
            survivors_angles: list[float] = []
            for idx, (mx, my) in enumerate(train.marker_positions):
                dx = mx - cx
                dy = my - cy
                if dx * dx + dy * dy <= radius_sq:
                    removed += 1
                    continue
                survivors_pos.append((mx, my))
                angle = train.marker_angles[idx] if idx < len(train.marker_angles) else 0.0
                survivors_angles.append(angle)
            train.marker_positions = survivors_pos
            train.marker_angles = survivors_angles
        return removed
