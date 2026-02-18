from __future__ import annotations

import math
import random
from dataclasses import dataclass

import pygame
import numpy as np  # type: ignore

from ..entities_constants import (
    ZOMBIE_DOG_LONG_AXIS_RATIO,
    ZOMBIE_DOG_SHORT_AXIS_RATIO,
    ZOMBIE_RADIUS,
)
from ..render_assets import (
    build_zombie_dog_directional_surfaces,
    build_zombie_directional_surfaces,
)
from ..screen_constants import FPS

DECAY_VARIANT_COUNT = 3


DECAY_EFFECT_DURATION_FRAMES = max(1, int(FPS))
BURNED_DECAY_EFFECT_DURATION_FRAMES = max(
    1, int(round(DECAY_EFFECT_DURATION_FRAMES * 0.6))
)


@dataclass(frozen=True)
class DecayMask:
    width: int
    height: int
    positions: list[tuple[int, int]]


_DECAY_MASKS: dict[str, list[DecayMask]] | None = None


def _max_decay_surface_size() -> tuple[int, int]:
    zombie_surfaces = build_zombie_directional_surfaces(ZOMBIE_RADIUS, draw_hands=False)
    base_size = ZOMBIE_RADIUS * 2.0
    long_axis = base_size * ZOMBIE_DOG_LONG_AXIS_RATIO
    short_axis = base_size * ZOMBIE_DOG_SHORT_AXIS_RATIO
    dog_surfaces = build_zombie_dog_directional_surfaces(long_axis, short_axis)
    widths = [surf.get_width() for surf in zombie_surfaces + dog_surfaces]
    heights = [surf.get_height() for surf in zombie_surfaces + dog_surfaces]
    return max(widths), max(heights)


def _build_decay_mask() -> DecayMask:
    width, height = _max_decay_surface_size()
    positions = [(x, y) for y in range(height) for x in range(width)]
    random.shuffle(positions)
    return DecayMask(width=width, height=height, positions=positions)


def _build_decay_masks() -> dict[str, list[DecayMask]]:
    return {
        "grayscale": [_build_decay_mask() for _ in range(DECAY_VARIANT_COUNT)],
        "burned": [_build_decay_mask() for _ in range(DECAY_VARIANT_COUNT)],
    }


def prepare_decay_mask() -> DecayMask:
    global _DECAY_MASKS
    if _DECAY_MASKS is None:
        _DECAY_MASKS = _build_decay_masks()
    return _DECAY_MASKS["grayscale"][0]


def get_decay_mask(*, tone: str = "grayscale") -> DecayMask:
    prepare_decay_mask()
    assert _DECAY_MASKS is not None
    masks = _DECAY_MASKS.get(tone) or _DECAY_MASKS["grayscale"]
    return random.choice(masks)


class DecayingEntityEffect:
    def __init__(
        self,
        image: pygame.Surface,
        center: tuple[int, int],
        *,
        duration_frames: int = DECAY_EFFECT_DURATION_FRAMES,
        mask: DecayMask | None = None,
        tone: str = "grayscale",
    ) -> None:
        self.surface = image.copy()
        self.surface = self.surface.convert_alpha()
        self.tone = tone
        self._apply_tone(tone=tone)
        self.rect = self.surface.get_rect(center=center)
        resolved_duration = max(1, int(duration_frames))
        if (
            self.tone == "burned"
            and resolved_duration == DECAY_EFFECT_DURATION_FRAMES
        ):
            resolved_duration = BURNED_DECAY_EFFECT_DURATION_FRAMES
        self.duration_frames = resolved_duration
        self.frames_elapsed = 0
        self.mask = mask or get_decay_mask(tone=tone)
        self.mask_index = 0
        self.pixel_carry = 0.0
        self.pixels_per_frame = len(self.mask.positions) / self.duration_frames
        self._burn_particles: list[tuple[float, float, float, float, float]] = []
        self._burn_body_circle: tuple[int, int, int] | None = None
        self._burn_body_circle_visible = False
        if self.tone == "burned":
            self._init_burn_particles()

    def update(self, *, frames: int = 1) -> bool:
        if frames <= 0:
            return True
        for _ in range(frames):
            if self.frames_elapsed >= self.duration_frames:
                return False
            self.frames_elapsed += 1
            self.pixel_carry += self.pixels_per_frame
            remove_count = int(self.pixel_carry)
            if remove_count > 0:
                self.pixel_carry -= remove_count
                self._erase_pixels(remove_count)
            if self._burn_particles and self._draw_burn_particles():
                self._burn_body_circle_visible = False
        return self.frames_elapsed < self.duration_frames

    def _erase_pixels(self, count: int) -> None:
        width, height = self.surface.get_size()
        for _ in range(count):
            if self.mask_index >= len(self.mask.positions):
                return
            x, y = self.mask.positions[self.mask_index]
            self.mask_index += 1
            if x >= width or y >= height:
                continue
            self.surface.set_at((x, y), (0, 0, 0, 0))

    def _apply_tone(self, *, tone: str) -> None:
        if tone == "burned":
            self._apply_burned_tone()
            return
        self._apply_grayscale()

    def _apply_grayscale(self) -> None:
        rgb = pygame.surfarray.pixels3d(self.surface)
        alpha = pygame.surfarray.pixels_alpha(self.surface)
        gray = (
            0.299 * rgb[:, :, 0] + 0.587 * rgb[:, :, 1] + 0.114 * rgb[:, :, 2]
        ).astype(np.uint8)
        rgb[:, :, 0] = gray
        rgb[:, :, 1] = gray
        rgb[:, :, 2] = gray
        del rgb, alpha

    def _apply_burned_tone(self) -> None:
        rgb = pygame.surfarray.pixels3d(self.surface)
        alpha = pygame.surfarray.pixels_alpha(self.surface)
        gray = (
            0.299 * rgb[:, :, 0] + 0.587 * rgb[:, :, 1] + 0.114 * rgb[:, :, 2]
        ).astype(np.uint8)
        # Slightly warm/charred tint: darker overall with red/orange bias.
        rgb[:, :, 0] = np.clip(gray * 0.80 + 26, 0, 255).astype(np.uint8)
        rgb[:, :, 1] = np.clip(gray * 0.36 + 8, 0, 255).astype(np.uint8)
        rgb[:, :, 2] = np.clip(gray * 0.20 + 2, 0, 255).astype(np.uint8)
        del rgb, alpha

    def _init_burn_particles(self) -> None:
        alpha = pygame.surfarray.array_alpha(self.surface)
        ys, xs = np.where(alpha > 0)
        if len(xs) == 0:
            return
        opaque_points = list(zip(xs.tolist(), ys.tolist(), strict=False))
        min_dim = max(2.0, float(min(self.surface.get_width(), self.surface.get_height())))
        min_x = min(x for x, _y in opaque_points)
        max_x = max(x for x, _y in opaque_points)
        min_y = min(y for _x, y in opaque_points)
        max_y = max(y for _x, y in opaque_points)
        body_w = max(1, max_x - min_x + 1)
        body_h = max(1, max_y - min_y + 1)
        body_radius = max(1, int(round(min(body_w, body_h) * 0.5)))
        body_center = (int(round((min_x + max_x) * 0.5)), int(round((min_y + max_y) * 0.5)))
        self._burn_body_circle = (body_center[0], body_center[1], body_radius)
        self._burn_body_circle_visible = True
        center_x = self.surface.get_width() * 0.5
        center_y = self.surface.get_height() * 0.5
        # Keep all burn circles within ~1.3x of the zombie diameter.
        max_effect_radius = min_dim * 0.25
        particle_count = max(8, min(12, len(opaque_points) // 10))
        shuffled = list(opaque_points)
        random.shuffle(shuffled)
        selected_count = 0
        for x, y in shuffled:
            if selected_count >= particle_count:
                break
            dist = math.hypot(float(x) - center_x, float(y) - center_y)
            max_local_radius = max_effect_radius - dist
            if max_local_radius < 1.0:
                continue
            base_radius_min = min_dim * 0.10
            base_radius_max = min(min_dim * 0.26, max_local_radius)
            if base_radius_max < base_radius_min:
                base_radius = max(1.0, max_local_radius)
            else:
                base_radius = random.uniform(base_radius_min, base_radius_max)
            start_frame = random.uniform(0.0, self.duration_frames * 0.28)
            life_frames = random.uniform(
                self.duration_frames * 0.40,
                self.duration_frames * 0.95,
            )
            jitter = random.uniform(0.85, 1.15)
            self._burn_particles.append(
                (float(x), float(y), float(base_radius), start_frame, life_frames * jitter)
            )
            selected_count += 1

    def _draw_burn_particles(self) -> bool:
        has_active_particle = False
        for px, py, base_radius, start_frame, life_frames in self._burn_particles:
            age = self.frames_elapsed - start_frame
            if age < 0 or life_frames <= 0:
                continue
            progress = max(0.0, min(1.0, age / life_frames))
            if progress >= 1.0:
                continue
            has_active_particle = True
            # Reduce shrink speed to half.
            size_progress = max(0.0, min(1.0, progress * 0.5))
            radius = max(0.8, base_radius * (1.0 - size_progress))
            self._draw_burn_gradient_circle(
                center=(int(round(px)), int(round(py))),
                radius=radius,
            )
        return has_active_particle

    def _draw_burn_gradient_circle(
        self,
        *,
        center: tuple[int, int],
        radius: float,
    ) -> None:
        cx, cy = center
        if radius <= 0:
            return
        r_outer = max(1, int(round(radius)))
        r_mid = max(1, int(round(radius * 0.70)))
        r_inner = max(1, int(round(radius * 0.42)))
        r_core = max(1, int(round(radius * 0.20)))
        outer = (173, 58, 35, 200)
        mid = (186, 62, 37, 220)
        inner = (191, 64, 38, 245)
        core = (209, 47, 42, 255)
        pygame.draw.circle(self.surface, outer, (cx, cy), r_outer)
        pygame.draw.circle(self.surface, mid, (cx, cy), r_mid)
        pygame.draw.circle(self.surface, inner, (cx, cy), r_inner)
        pygame.draw.circle(self.surface, core, (cx, cy), r_core)

    def build_draw_surface(self) -> pygame.Surface:
        if not (self.tone == "burned" and self._burn_body_circle_visible and self._burn_body_circle):
            return self.surface
        cx, cy, radius = self._burn_body_circle
        draw_surface = self.surface.copy()
        pygame.draw.circle(draw_surface, (220, 20, 20, 255), (cx, cy), radius)
        return draw_surface


def update_decay_effects(
    effects: list[DecayingEntityEffect], *, frames: int = 1
) -> None:
    if not effects:
        return
    alive: list[DecayingEntityEffect] = []
    for effect in effects:
        if effect.update(frames=frames):
            alive.append(effect)
    effects[:] = alive
