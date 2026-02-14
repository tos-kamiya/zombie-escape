from __future__ import annotations

from collections.abc import Iterable
from enum import IntFlag
from typing import TYPE_CHECKING

import pygame

if TYPE_CHECKING:  # pragma: no cover - typing-only imports
    pass


SPATIAL_INDEX_CELL_SIZE = 32


class SpatialKind(IntFlag):
    NONE = 0
    PLAYER = 1 << 0
    CAR = 1 << 1
    ZOMBIE = 1 << 2
    ZOMBIE_DOG = 1 << 3
    TRAPPED_ZOMBIE = 1 << 4
    SURVIVOR = 1 << 5
    PATROL_BOT = 1 << 6
    ALL = PLAYER | CAR | ZOMBIE | ZOMBIE_DOG | TRAPPED_ZOMBIE | SURVIVOR | PATROL_BOT


def _entity_center(entity: pygame.sprite.Sprite) -> tuple[float, float]:
    rect = getattr(entity, "rect", None)
    if rect is not None:
        return float(rect.centerx), float(rect.centery)
    x = getattr(entity, "x", 0.0)
    y = getattr(entity, "y", 0.0)
    return float(x), float(y)


def kind_for_entity(entity: pygame.sprite.Sprite) -> SpatialKind:
    from ..entities import Car, PatrolBot, Player, Survivor, Zombie, ZombieDog, TrappedZombie

    if isinstance(entity, Player):
        return SpatialKind.PLAYER
    if isinstance(entity, Car):
        return SpatialKind.CAR
    if isinstance(entity, ZombieDog):
        return SpatialKind.ZOMBIE_DOG
    if isinstance(entity, Zombie):
        return SpatialKind.ZOMBIE
    if isinstance(entity, TrappedZombie):
        return SpatialKind.TRAPPED_ZOMBIE
    if isinstance(entity, Survivor):
        return SpatialKind.SURVIVOR
    if isinstance(entity, PatrolBot):
        return SpatialKind.PATROL_BOT
    return SpatialKind.NONE


class SpatialIndex:
    def __init__(self, cell_size: int = SPATIAL_INDEX_CELL_SIZE) -> None:
        self.cell_size = max(1, int(cell_size))
        self._cells: dict[tuple[int, int], list[tuple[pygame.sprite.Sprite, SpatialKind]]] = {}

    def clear(self) -> None:
        self._cells.clear()

    def rebuild(self, entities: Iterable[pygame.sprite.Sprite]) -> None:
        self.clear()
        for entity in entities:
            if not getattr(entity, "alive", lambda: True)():
                continue
            kind = kind_for_entity(entity)
            if kind == SpatialKind.NONE:
                continue
            self.insert(entity, kind)

    def insert(self, entity: pygame.sprite.Sprite, kind: SpatialKind) -> None:
        x, y = _entity_center(entity)
        cell = (int(x // self.cell_size), int(y // self.cell_size))
        self._cells.setdefault(cell, []).append((entity, kind))

    def query_radius(
        self,
        center: tuple[float, float],
        radius: float,
        *,
        kinds: SpatialKind = SpatialKind.ALL,
    ) -> list[pygame.sprite.Sprite]:
        if kinds == SpatialKind.NONE:
            return []
        radius = max(0.0, float(radius))
        if radius <= 0:
            return []
        cx, cy = center
        min_x = int((cx - radius) // self.cell_size)
        max_x = int((cx + radius) // self.cell_size)
        min_y = int((cy - radius) // self.cell_size)
        max_y = int((cy + radius) // self.cell_size)
        radius_sq = radius * radius
        results: list[pygame.sprite.Sprite] = []
        seen: set[int] = set()
        for cell_y in range(min_y, max_y + 1):
            for cell_x in range(min_x, max_x + 1):
                bucket = self._cells.get((cell_x, cell_y))
                if not bucket:
                    continue
                for entity, kind in bucket:
                    if kind & kinds == 0:
                        continue
                    ent_id = id(entity)
                    if ent_id in seen:
                        continue
                    ex, ey = _entity_center(entity)
                    dx = ex - cx
                    dy = ey - cy
                    if dx * dx + dy * dy <= radius_sq:
                        results.append(entity)
                        seen.add(ent_id)
        return results

    def query_aabb(
        self,
        rect: pygame.Rect,
        *,
        kinds: SpatialKind = SpatialKind.ALL,
    ) -> list[pygame.sprite.Sprite]:
        if kinds == SpatialKind.NONE:
            return []
        min_x = int(rect.left // self.cell_size)
        max_x = int(rect.right // self.cell_size)
        min_y = int(rect.top // self.cell_size)
        max_y = int(rect.bottom // self.cell_size)
        results: list[pygame.sprite.Sprite] = []
        seen: set[int] = set()
        for cell_y in range(min_y, max_y + 1):
            for cell_x in range(min_x, max_x + 1):
                bucket = self._cells.get((cell_x, cell_y))
                if not bucket:
                    continue
                for entity, kind in bucket:
                    if kind & kinds == 0:
                        continue
                    ent_id = id(entity)
                    if ent_id in seen:
                        continue
                    ent_rect = getattr(entity, "rect", None)
                    if ent_rect is None or rect.colliderect(ent_rect):
                        results.append(entity)
                        seen.add(ent_id)
        return results
