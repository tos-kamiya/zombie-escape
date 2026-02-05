from __future__ import annotations

from typing import Callable

import pygame
from pygame import rect

try:
    from typing import Self
except ImportError:  # pragma: no cover - Python 3.10 fallback
    from typing_extensions import Self

from ..entities_constants import INTERNAL_WALL_BEVEL_DEPTH, INTERNAL_WALL_HEALTH, STEEL_BEAM_HEALTH
from ..render_assets import (
    EnvironmentPalette,
    build_beveled_polygon,
    build_rubble_wall_surface,
    paint_steel_beam_surface,
    paint_wall_surface,
    resolve_steel_beam_colors,
    resolve_wall_colors,
    rubble_offset_for_size,
    RUBBLE_ROTATION_DEG,
)
from .movement import _circle_polygon_collision, _circle_rect_collision, _rect_polygon_collision


class Wall(pygame.sprite.Sprite):
    def __init__(
        self: Self,
        x: int,
        y: int,
        width: int,
        height: int,
        *,
        health: int = INTERNAL_WALL_HEALTH,
        palette: EnvironmentPalette | None = None,
        palette_category: str = "inner_wall",
        bevel_depth: int = INTERNAL_WALL_BEVEL_DEPTH,
        bevel_mask: tuple[bool, bool, bool, bool] | None = None,
        draw_bottom_side: bool = False,
        bottom_side_ratio: float = 0.1,
        side_shade_ratio: float = 0.9,
        on_destroy: Callable[[Self], None] | None = None,
    ) -> None:
        super().__init__()
        safe_width = max(1, width)
        safe_height = max(1, height)
        self.image = pygame.Surface((safe_width, safe_height), pygame.SRCALPHA)
        self.palette = palette
        self.palette_category = palette_category
        self.health = health
        self.max_health = max(1, health)
        self.on_destroy = on_destroy
        self.bevel_depth = max(0, bevel_depth)
        self.bevel_mask = bevel_mask or (False, False, False, False)
        self.draw_bottom_side = draw_bottom_side
        self.bottom_side_ratio = max(0.0, bottom_side_ratio)
        self.side_shade_ratio = max(0.0, min(1.0, side_shade_ratio))
        self._local_polygon = _build_beveled_polygon(safe_width, safe_height, self.bevel_depth, self.bevel_mask)
        self._update_color()
        self.rect = self.image.get_rect(topleft=(x, y))
        # Keep collision rectangular even when beveled visually.
        self._collision_polygon = None

    def _take_damage(self: Self, *, amount: int = 1) -> None:
        if self.health > 0:
            self.health -= amount
            self._update_color()
            if self.health <= 0:
                if self.on_destroy:
                    try:
                        self.on_destroy(self)
                    except Exception as exc:
                        print(f"Wall destroy callback failed: {exc}")
                self.kill()

    def _update_color(self: Self) -> None:
        if self.health <= 0:
            health_ratio = 0.0
        else:
            health_ratio = max(0.0, self.health / self.max_health)
        fill_color, border_color = resolve_wall_colors(
            health_ratio=health_ratio,
            palette_category=self.palette_category,
            palette=self.palette,
        )
        paint_wall_surface(
            self.image,
            fill_color=fill_color,
            border_color=border_color,
            bevel_depth=self.bevel_depth,
            bevel_mask=self.bevel_mask,
            draw_bottom_side=self.draw_bottom_side,
            bottom_side_ratio=self.bottom_side_ratio,
            side_shade_ratio=self.side_shade_ratio,
        )

    def collides_rect(self: Self, rect_obj: rect.Rect) -> bool:
        if self._collision_polygon is None:
            return self.rect.colliderect(rect_obj)
        return _rect_polygon_collision(rect_obj, self._collision_polygon)

    def _collides_circle(self: Self, center: tuple[float, float], radius: float) -> bool:
        if not _circle_rect_collision(center, radius, self.rect):
            return False
        if self._collision_polygon is None:
            return True
        return _circle_polygon_collision(center, radius, self._collision_polygon)

    def set_palette(self: Self, palette: EnvironmentPalette | None, *, force: bool = False) -> None:
        """Update the wall's palette to match the current ambient palette."""

        if not force and self.palette is palette:
            return
        self.palette = palette
        self._update_color()


class RubbleWall(Wall):
    def __init__(
        self: Self,
        x: int,
        y: int,
        width: int,
        height: int,
        *,
        health: int = INTERNAL_WALL_HEALTH,
        palette: EnvironmentPalette | None = None,
        palette_category: str = "inner_wall",
        bevel_depth: int = INTERNAL_WALL_BEVEL_DEPTH,
        rubble_rotation_deg: float | None = None,
        rubble_offset_px: int | None = None,
        on_destroy: Callable[[Self], None] | None = None,
    ) -> None:
        self._rubble_rotation_deg = RUBBLE_ROTATION_DEG if rubble_rotation_deg is None else rubble_rotation_deg
        base_size = max(1, min(width, height))
        self._rubble_offset_px = rubble_offset_for_size(base_size) if rubble_offset_px is None else rubble_offset_px
        super().__init__(
            x,
            y,
            width,
            height,
            health=health,
            palette=palette,
            palette_category=palette_category,
            bevel_depth=bevel_depth,
            bevel_mask=(False, False, False, False),
            draw_bottom_side=False,
            on_destroy=on_destroy,
        )

    def _update_color(self: Self) -> None:
        if self.health <= 0:
            health_ratio = 0.0
        else:
            health_ratio = max(0.0, self.health / self.max_health)
        fill_color, border_color = resolve_wall_colors(
            health_ratio=health_ratio,
            palette_category=self.palette_category,
            palette=self.palette,
        )
        rubble_surface = build_rubble_wall_surface(
            self.image.get_width(),
            fill_color=fill_color,
            border_color=border_color,
            angle_deg=self._rubble_rotation_deg,
            offset_px=self._rubble_offset_px,
            bevel_depth=self.bevel_depth,
        )
        self.image.fill((0, 0, 0, 0))
        self.image.blit(rubble_surface, (0, 0))


class SteelBeam(pygame.sprite.Sprite):
    """Single-cell obstacle that behaves like a tougher internal wall."""

    def __init__(
        self: Self,
        x: int,
        y: int,
        size: int,
        *,
        health: int = STEEL_BEAM_HEALTH,
        palette: EnvironmentPalette | None = None,
    ) -> None:
        super().__init__()
        # Slightly inset from the cell size so it reads as a separate object.
        margin = max(3, size // 14)
        inset_size = max(4, size - margin * 2)
        self.image = pygame.Surface((inset_size, inset_size), pygame.SRCALPHA)
        self._added_to_groups = False
        self.health = health
        self.max_health = max(1, health)
        self.palette = palette
        self._update_color()
        self.rect = self.image.get_rect(center=(x + size // 2, y + size // 2))

    def _take_damage(self: Self, *, amount: int = 1) -> None:
        if self.health > 0:
            self.health -= amount
            self._update_color()
            if self.health <= 0:
                self.kill()

    def _update_color(self: Self) -> None:
        """Render a simple square with crossed diagonals that darkens as damaged."""
        if self.health <= 0:
            return
        health_ratio = max(0.0, self.health / self.max_health)
        base_color, line_color = resolve_steel_beam_colors(health_ratio=health_ratio, palette=self.palette)
        paint_steel_beam_surface(
            self.image,
            base_color=base_color,
            line_color=line_color,
            health_ratio=health_ratio,
        )


def _build_beveled_polygon(
    width: int,
    height: int,
    depth: int,
    bevels: tuple[bool, bool, bool, bool],
) -> list[tuple[int, int]]:
    return build_beveled_polygon(width, height, depth, bevels)


def _is_inner_wall(wall: pygame.sprite.Sprite) -> bool:
    if isinstance(wall, SteelBeam):
        return True
    if isinstance(wall, Wall):
        return wall.palette_category == "inner_wall"
    return False
