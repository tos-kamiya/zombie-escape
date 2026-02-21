from __future__ import annotations

import math
from typing import TYPE_CHECKING

import pygame

try:
    from typing import Self
except ImportError:  # pragma: no cover - Python 3.10 fallback
    from typing_extensions import Self

from ..colors import BLACK, WHITE
from ..entities_constants import (
    TRANSPORT_BOT_ACTIVATION_RADIUS,
    TRANSPORT_BOT_COLLISION_RADIUS,
    TRANSPORT_BOT_DOOR_CLOSE_MS,
    TRANSPORT_BOT_END_WAIT_MS,
    TRANSPORT_BOT_HEIGHT,
    TRANSPORT_BOT_SPEED,
    TRANSPORT_BOT_WIDTH,
)
from .movement import _circle_wall_collision
from .survivor import Survivor

if TYPE_CHECKING:  # pragma: no cover - typing-only imports
    from .player import Player


class TransportBot(pygame.sprite.Sprite):
    def __init__(
        self: Self,
        path_points: list[tuple[int, int]],
        *,
        speed: float = TRANSPORT_BOT_SPEED,
        activation_radius: float = TRANSPORT_BOT_ACTIVATION_RADIUS,
        end_wait_ms: int = TRANSPORT_BOT_END_WAIT_MS,
        door_close_ms: int = TRANSPORT_BOT_DOOR_CLOSE_MS,
    ) -> None:
        super().__init__()
        assert len(path_points) >= 2, "TransportBot path requires at least 2 points"
        self.path_points: list[tuple[float, float]] = [
            (float(x), float(y)) for x, y in path_points
        ]
        start_x, start_y = self.path_points[0]
        self.image = pygame.Surface((TRANSPORT_BOT_WIDTH, TRANSPORT_BOT_HEIGHT))
        self.image.fill(WHITE)
        pygame.draw.rect(self.image, BLACK, self.image.get_rect(), width=1)
        self.rect = self.image.get_rect(center=(int(start_x), int(start_y)))
        self.x = float(self.rect.centerx)
        self.y = float(self.rect.centery)
        self.collision_radius = float(TRANSPORT_BOT_COLLISION_RADIUS)
        self.shadow_radius = max(1, int(self.collision_radius * 1.2))
        self.shadow_offset_scale = 1.0 / 3.0
        self.speed = max(0.1, float(speed))
        self.activation_radius = max(1.0, float(activation_radius))
        self.end_wait_ms = max(0, int(end_wait_ms))
        self.door_close_ms = max(0, int(door_close_ms))

        self._direction = 1  # +1 forward, -1 backward along path indices
        self._target_index = 1
        self._moving = False
        self._wait_until_ms = 0
        self._close_until_ms = 0
        self.passenger: pygame.sprite.Sprite | None = None

    @property
    def moving(self: Self) -> bool:
        return self._moving

    def _is_endpoint(self: Self, idx: int) -> bool:
        last = len(self.path_points) - 1
        return idx <= 0 or idx >= last

    def _reverse_direction(self: Self) -> None:
        last = len(self.path_points) - 1
        if self._direction > 0:
            self._target_index = max(0, self._target_index - 1)
            self._direction = -1
        else:
            self._target_index = min(last, self._target_index + 1)
            self._direction = 1

    def _begin_boarding(self: Self, entity: pygame.sprite.Sprite, *, now_ms: int) -> None:
        self.passenger = entity
        if hasattr(entity, "mounted_vehicle"):
            entity.mounted_vehicle = self
        self._moving = False
        self._close_until_ms = now_ms + self.door_close_ms

    def _disembark_passenger(
        self: Self,
        *,
        all_sprites: pygame.sprite.LayeredUpdates,
        survivor_group: pygame.sprite.Group,
    ) -> None:
        passenger = self.passenger
        if passenger is None:
            return
        if hasattr(passenger, "mounted_vehicle"):
            passenger.mounted_vehicle = None
        passenger.rect.center = (int(self.x), int(self.y))
        if hasattr(passenger, "x"):
            passenger.x = float(passenger.rect.centerx)
        if hasattr(passenger, "y"):
            passenger.y = float(passenger.rect.centery)
        if isinstance(passenger, Survivor):
            survivor_group.add(passenger)
            all_sprites.add(passenger, layer=2)
        else:
            all_sprites.add(passenger, layer=2)
        self.passenger = None

    def _try_auto_activate(
        self: Self,
        *,
        player: "Player | None",
        survivor_group: pygame.sprite.Group,
        all_sprites: pygame.sprite.LayeredUpdates,
        now_ms: int,
    ) -> None:
        if self.passenger is not None or self._moving or now_ms < self._wait_until_ms:
            return
        if self._close_until_ms > 0 and now_ms < self._close_until_ms:
            return

        candidate: pygame.sprite.Sprite | None = None
        if (
            player is not None
            and player.alive()
            and getattr(player, "mounted_vehicle", None) is None
        ):
            dx = player.x - self.x
            dy = player.y - self.y
            if dx * dx + dy * dy <= self.activation_radius * self.activation_radius:
                candidate = player
        if candidate is None:
            for survivor in survivor_group:
                if not survivor.alive() or getattr(survivor, "mounted_vehicle", None):
                    continue
                dx = survivor.x - self.x
                dy = survivor.y - self.y
                if dx * dx + dy * dy <= self.activation_radius * self.activation_radius:
                    candidate = survivor
                    break

        if candidate is None:
            return
        all_sprites.remove(candidate)
        survivor_group.remove(candidate)
        self._begin_boarding(candidate, now_ms=now_ms)

    def _forward_blocked(
        self: Self,
        *,
        next_x: float,
        next_y: float,
        dir_x: float,
        dir_y: float,
        walls: list[pygame.sprite.Sprite],
        pitfall_cells: set[tuple[int, int]],
        cell_size: int,
        layout,
    ) -> bool:
        hit_radius = self.collision_radius + 1.0
        for wall in walls:
            if _circle_wall_collision((next_x, next_y), hit_radius, wall):
                return True

        if cell_size > 0:
            lead_x = next_x + dir_x * (hit_radius + 1.0)
            lead_y = next_y + dir_y * (hit_radius + 1.0)
            lead_cell = (int(lead_x // cell_size), int(lead_y // cell_size))
            if lead_cell in pitfall_cells:
                return True
            if lead_cell in layout.outer_wall_cells or lead_cell in layout.outside_cells:
                return True
        if not (
            0 <= next_x < layout.field_rect.width and 0 <= next_y < layout.field_rect.height
        ):
            return True
        return False

    def _arrive_waypoint(
        self: Self,
        *,
        now_ms: int,
        all_sprites: pygame.sprite.LayeredUpdates,
        survivor_group: pygame.sprite.Group,
    ) -> None:
        idx = self._target_index
        last = len(self.path_points) - 1
        if self._is_endpoint(idx):
            self._moving = False
            self._close_until_ms = 0
            self._wait_until_ms = now_ms + self.end_wait_ms
            if idx <= 0:
                self._direction = 1
                self._target_index = 1
            else:
                self._direction = -1
                self._target_index = max(0, last - 1)
            self._disembark_passenger(
                all_sprites=all_sprites,
                survivor_group=survivor_group,
            )
            return
        self._target_index = idx + self._direction

    def _sync_passenger(self: Self) -> None:
        passenger = self.passenger
        if passenger is None:
            return
        passenger.rect.center = (int(self.x), int(self.y))
        if hasattr(passenger, "x"):
            passenger.x = float(passenger.rect.centerx)
        if hasattr(passenger, "y"):
            passenger.y = float(passenger.rect.centery)

    def _push_external_entities(
        self: Self,
        *,
        player: "Player | None",
        survivors: pygame.sprite.Group,
        zombies: pygame.sprite.Group,
    ) -> None:
        if not self._moving:
            return
        entities: list[pygame.sprite.Sprite] = []
        if player is not None and player.alive():
            entities.append(player)
        entities.extend([s for s in survivors if s.alive()])
        entities.extend([z for z in zombies if z.alive()])
        for entity in entities:
            if entity is self.passenger:
                continue
            if getattr(entity, "mounted_vehicle", None) is not None:
                continue
            ex, ey = entity.rect.center
            dx = float(ex) - self.x
            dy = float(ey) - self.y
            dist_sq = dx * dx + dy * dy
            entity_radius = float(
                getattr(
                    entity,
                    "collision_radius",
                    getattr(entity, "radius", max(entity.rect.width, entity.rect.height) / 2),
                )
            )
            min_dist = self.collision_radius + entity_radius
            if dist_sq <= 0.0:
                dx, dy, dist_sq = 1.0, 0.0, 1.0
            dist = math.sqrt(dist_sq)
            if dist >= min_dist:
                continue
            push = min_dist - dist
            new_x = float(ex) + (dx / dist) * push
            new_y = float(ey) + (dy / dist) * push
            entity.rect.center = (int(new_x), int(new_y))
            if hasattr(entity, "x"):
                entity.x = float(entity.rect.centerx)
            if hasattr(entity, "y"):
                entity.y = float(entity.rect.centery)

    def update(
        self: Self,
        walls: list[pygame.sprite.Sprite],
        *,
        player: "Player | None",
        survivor_group: pygame.sprite.Group,
        zombie_group: pygame.sprite.Group,
        all_sprites: pygame.sprite.LayeredUpdates,
        layout,
        cell_size: int,
        pitfall_cells: set[tuple[int, int]],
        now_ms: int,
    ) -> None:
        self._try_auto_activate(
            player=player,
            survivor_group=survivor_group,
            all_sprites=all_sprites,
            now_ms=now_ms,
        )
        if self.passenger is not None and not self._moving and now_ms >= self._close_until_ms:
            self._moving = True
            if self._is_endpoint(self._target_index):
                self._target_index = 1 if self._direction > 0 else len(self.path_points) - 2

        if self._moving:
            start_x, start_y = self.x, self.y
            target_x, target_y = self.path_points[self._target_index]
            dx = target_x - start_x
            dy = target_y - start_y
            dist = math.hypot(dx, dy)
            if dist <= 1e-6:
                self.x, self.y = target_x, target_y
                self._arrive_waypoint(
                    now_ms=now_ms,
                    all_sprites=all_sprites,
                    survivor_group=survivor_group,
                )
            else:
                step = min(self.speed, dist)
                dir_x = dx / dist
                dir_y = dy / dist
                next_x = start_x + dir_x * step
                next_y = start_y + dir_y * step
                if self._forward_blocked(
                    next_x=next_x,
                    next_y=next_y,
                    dir_x=dir_x,
                    dir_y=dir_y,
                    walls=walls,
                    pitfall_cells=pitfall_cells,
                    cell_size=cell_size,
                    layout=layout,
                ):
                    self._reverse_direction()
                else:
                    self.x, self.y = next_x, next_y
                    if step >= dist - 1e-6:
                        self.x, self.y = target_x, target_y
                        self._arrive_waypoint(
                            now_ms=now_ms,
                            all_sprites=all_sprites,
                            survivor_group=survivor_group,
                        )

        self.rect.center = (int(self.x), int(self.y))
        self._sync_passenger()
        self._push_external_entities(
            player=player,
            survivors=survivor_group,
            zombies=zombie_group,
        )
