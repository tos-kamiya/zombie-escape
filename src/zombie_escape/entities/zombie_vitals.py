from __future__ import annotations

from typing import Callable

import pygame

from .patrol_paralyze import update_paralyze_from_patrol_contact


class ZombieVitals:
    def __init__(
        self,
        *,
        max_health: int,
        decay_duration_frames: float,
        decay_min_speed_ratio: float,
        carbonize_decay_frames: float,
        on_health_ratio: Callable[[float], None],
        on_kill: Callable[[], None],
        on_carbonize: Callable[[], None],
    ) -> None:
        self.max_health = max(1, int(max_health))
        self.health = self.max_health
        self.decay_duration_frames = float(decay_duration_frames)
        self.decay_min_speed_ratio = float(decay_min_speed_ratio)
        self.carbonize_decay_frames = float(carbonize_decay_frames)
        self.on_health_ratio = on_health_ratio
        self.on_kill = on_kill
        self.on_carbonize = on_carbonize
        self.carbonized = False
        self.decay_carry = 0.0
        self.last_damage_ms: int | None = None
        self.last_damage_source: str | None = None
        self.patrol_paralyze_until_ms = 0
        self.patrol_damage_frame_counter = 0

    def _set_health(self, new_health: int) -> None:
        self.health = max(0, min(self.max_health, int(new_health)))
        health_ratio = 0.0 if self.max_health <= 0 else self.health / self.max_health
        health_ratio = max(0.0, min(1.0, health_ratio))
        speed_ratio = self.decay_min_speed_ratio + (
            1.0 - self.decay_min_speed_ratio
        ) * health_ratio
        self.on_health_ratio(speed_ratio)
        if self.health <= 0:
            self.on_kill()

    def apply_decay(self) -> None:
        if self.decay_duration_frames <= 0:
            return
        self.decay_carry += self.max_health / self.decay_duration_frames
        if self.decay_carry >= 1.0:
            decay_amount = int(self.decay_carry)
            self.decay_carry -= decay_amount
            self._set_health(self.health - decay_amount)

    def take_damage(
        self, amount: int, *, source: str | None = None, now_ms: int | None = None
    ) -> None:
        if amount <= 0:
            return
        self.last_damage_ms = pygame.time.get_ticks() if now_ms is None else now_ms
        self.last_damage_source = source
        self._set_health(self.health - amount)

    def carbonize(self) -> None:
        if self.carbonized:
            return
        self.carbonized = True
        if self.decay_duration_frames > 0:
            remaining_ratio = min(
                1.0, self.carbonize_decay_frames / self.decay_duration_frames
            )
            remaining_health = max(1, int(round(self.max_health * remaining_ratio)))
            self.health = min(self.health, remaining_health)
            self.decay_carry = 0.0
        self.on_health_ratio(0.0)
        self.on_carbonize()

    def update_patrol_paralyze(
        self,
        *,
        entity_center: tuple[float, float],
        entity_radius: float,
        patrol_bots: list,
        now_ms: int,
        paralyze_duration_ms: int,
        damage_interval_frames: int,
        damage_amount: int,
        apply_damage: Callable[[int], None],
    ) -> bool:
        _, self.patrol_paralyze_until_ms, self.patrol_damage_frame_counter = (
            update_paralyze_from_patrol_contact(
                entity_center=entity_center,
                entity_radius=entity_radius,
                patrol_bots=patrol_bots,
                now_ms=now_ms,
                paralyze_until_ms=self.patrol_paralyze_until_ms,
                paralyze_duration_ms=paralyze_duration_ms,
                damage_counter=self.patrol_damage_frame_counter,
                damage_interval_frames=damage_interval_frames,
                damage_amount=damage_amount,
                apply_damage=apply_damage,
            )
        )
        return now_ms < self.patrol_paralyze_until_ms
