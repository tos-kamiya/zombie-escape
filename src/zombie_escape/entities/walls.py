from __future__ import annotations

from typing import Callable

import pygame
from pygame import rect

try:
    from typing import Self
except ImportError:  # pragma: no cover - Python 3.10 fallback
    from typing_extensions import Self

from ..entities_constants import (
    INTERNAL_WALL_BEVEL_DEPTH,
    INTERNAL_WALL_HEALTH,
    STEEL_BEAM_HEALTH,
)
from ..render_assets import (
    EnvironmentPalette,
    build_beveled_polygon,
    build_rubble_wall_surface,
    paint_steel_beam_surface,
    paint_wall_damage_overlay,
    paint_wall_surface,
    resolve_steel_beam_colors,
    resolve_wall_colors,
    rubble_offset_for_size,
    RUBBLE_ROTATION_DEG,
)
from .movement import (
    _circle_polygon_collision,
    _circle_rect_collision,
    _rect_polygon_collision,
)

_WALL_INDEX_DIRTY = False
_WALL_DAMAGE_OVERLAY_SEED = 1337


def _damage_overlay_variant_index(
    *,
    x: int,
    y: int,
    width: int,
    height: int,
) -> int:
    cell_w = max(1, int(width))
    cell_h = max(1, int(height))
    cell_x = int(x) // cell_w
    cell_y = int(y) // cell_h
    return (cell_x % 3) + ((cell_y % 3) * 3)


def _mark_wall_index_dirty() -> None:
    global _WALL_INDEX_DIRTY
    _WALL_INDEX_DIRTY = True


def consume_wall_index_dirty() -> bool:
    global _WALL_INDEX_DIRTY
    if not _WALL_INDEX_DIRTY:
        return False
    _WALL_INDEX_DIRTY = False
    return True


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
        damage_overlay_seed: int = _WALL_DAMAGE_OVERLAY_SEED,
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
        self._damage_visual_seed = damage_overlay_seed
        self._damage_overlay_variant = _damage_overlay_variant_index(
            x=x,
            y=y,
            width=safe_width,
            height=safe_height,
        )
        self._local_polygon = _build_beveled_polygon(
            safe_width, safe_height, self.bevel_depth, self.bevel_mask
        )
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
                _mark_wall_index_dirty()
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
        self._paint_damage_marks(health_ratio=health_ratio)

    def _paint_damage_marks(self: Self, *, health_ratio: float) -> None:
        paint_wall_damage_overlay(
            self.image,
            health_ratio=health_ratio,
            seed=self._damage_visual_seed,
            variant_index=self._damage_overlay_variant,
        )

    def collides_rect(self: Self, rect_obj: rect.Rect) -> bool:
        if self._collision_polygon is None:
            return self.rect.colliderect(rect_obj)
        return _rect_polygon_collision(rect_obj, self._collision_polygon)

    def _collides_circle(
        self: Self, center: tuple[float, float], radius: float
    ) -> bool:
        if not _circle_rect_collision(center, radius, self.rect):
            return False
        if self._collision_polygon is None:
            return True
        return _circle_polygon_collision(center, radius, self._collision_polygon)

    def set_palette(
        self: Self, palette: EnvironmentPalette | None, *, force: bool = False
    ) -> None:
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
        damage_overlay_seed: int = _WALL_DAMAGE_OVERLAY_SEED,
        on_destroy: Callable[[Self], None] | None = None,
    ) -> None:
        self._rubble_rotation_deg = (
            RUBBLE_ROTATION_DEG if rubble_rotation_deg is None else rubble_rotation_deg
        )
        base_size = max(1, min(width, height))
        self._rubble_offset_px = (
            rubble_offset_for_size(base_size)
            if rubble_offset_px is None
            else rubble_offset_px
        )
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
            damage_overlay_seed=damage_overlay_seed,
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
        self._paint_damage_marks(health_ratio=health_ratio)


class ReinforcedWall(Wall):
    """Non-destructible-looking inner wall with metallic frame highlights."""

    def __init__(
        self: Self,
        x: int,
        y: int,
        width: int,
        height: int,
        *,
        health: int = INTERNAL_WALL_HEALTH,
        palette: EnvironmentPalette | None = None,
        bevel_depth: int = INTERNAL_WALL_BEVEL_DEPTH,
        bevel_mask: tuple[bool, bool, bool, bool] | None = None,
        draw_bottom_side: bool = False,
        bottom_side_ratio: float = 0.1,
        side_shade_ratio: float = 0.9,
        on_destroy: Callable[[Self], None] | None = None,
    ) -> None:
        super().__init__(
            x,
            y,
            width,
            height,
            health=health,
            palette=palette,
            palette_category="outer_wall",
            bevel_depth=bevel_depth,
            bevel_mask=bevel_mask,
            draw_bottom_side=draw_bottom_side,
            bottom_side_ratio=bottom_side_ratio,
            side_shade_ratio=side_shade_ratio,
            on_destroy=on_destroy,
        )

    def _update_color(self: Self) -> None:
        if self.health <= 0:
            health_ratio = 0.0
        else:
            health_ratio = max(0.0, self.health / self.max_health)
        fill_color, border_color = resolve_wall_colors(
            health_ratio=health_ratio,
            palette_category="outer_wall",
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

        w, h = self.image.get_size()
        side_height = (
            max(1, int(h * max(0.0, self.bottom_side_ratio)))
            if self.draw_bottom_side
            else 0
        )
        top_height = max(1, h - side_height)
        frame_width = max(2, min(w, top_height) // 6)
        inset = max(4, frame_width + 2)
        frame_rect = pygame.Rect(
            inset,
            inset,
            max(4, w - inset * 2),
            max(4, top_height - inset * 2),
        )

        frame_color = (
            max(0, int(border_color[0] * 0.656)),
            max(0, int(border_color[1] * 0.656)),
            max(0, int(border_color[2] * 0.704)),
        )
        highlight = (
            min(255, int(fill_color[0] * 1.14)),
            min(255, int(fill_color[1] * 1.14)),
            min(255, int(fill_color[2] * 1.14)),
        )
        thin_highlight = (
            min(255, int(fill_color[0] * 1.22)),
            min(255, int(fill_color[1] * 1.22)),
            min(255, int(fill_color[2] * 1.22)),
        )

        pygame.draw.rect(self.image, frame_color, frame_rect)

        frame_overlay = pygame.Surface((w, h), pygame.SRCALPHA)
        base_step = max(5, frame_width)
        rhythm = [
            base_step,
            max(3, base_step - 2),
            base_step + 2,
            max(4, base_step - 1),
        ]
        thick_width = max(1, frame_width // 3)
        sx = frame_rect.left - frame_rect.height
        i = 0
        while sx <= frame_rect.right + frame_rect.height:
            start = (sx, frame_rect.bottom)
            end = (sx + frame_rect.height, frame_rect.top)
            pygame.draw.line(frame_overlay, highlight, start, end, width=thick_width)
            thin_offset = max(2, thick_width + 1)
            pygame.draw.line(
                frame_overlay,
                thin_highlight,
                (start[0] + thin_offset, start[1]),
                (end[0] + thin_offset, end[1]),
                width=1,
            )
            sx += rhythm[i % len(rhythm)]
            i += 1
        frame_mask = pygame.Surface((w, h), pygame.SRCALPHA)
        pygame.draw.rect(frame_mask, (255, 255, 255, 255), frame_rect)
        pygame.draw.rect(
            frame_mask,
            (0, 0, 0, 0),
            pygame.Rect(0, top_height, w, h - top_height),
        )
        frame_overlay.blit(frame_mask, (0, 0), special_flags=pygame.BLEND_RGBA_MULT)
        self.image.blit(frame_overlay, (0, 0))

        inner_rect = frame_rect.inflate(-frame_width * 2, -frame_width * 2)
        if inner_rect.width > 0 and inner_rect.height > 0:
            panel_color = fill_color
            pygame.draw.rect(self.image, panel_color, inner_rect)
        self._paint_damage_marks(health_ratio=health_ratio)


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
        damage_overlay_seed: int = _WALL_DAMAGE_OVERLAY_SEED,
        on_destroy: Callable[[Self], None] | None = None,
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
        self.on_destroy = on_destroy
        self._damage_visual_seed = damage_overlay_seed
        self._damage_overlay_variant = _damage_overlay_variant_index(
            x=x,
            y=y,
            width=size,
            height=size,
        )
        self._update_color()
        self.rect = self.image.get_rect(center=(x + size // 2, y + size // 2))

    def _take_damage(self: Self, *, amount: int = 1) -> None:
        if self.health > 0:
            self.health -= amount
            self._update_color()
            if self.health <= 0:
                if self.on_destroy is not None:
                    self.on_destroy(self)
                _mark_wall_index_dirty()
                self.kill()

    def _update_color(self: Self) -> None:
        """Render a simple square with crossed diagonals that darkens as damaged."""
        if self.health <= 0:
            return
        health_ratio = max(0.0, self.health / self.max_health)
        base_color, line_color = resolve_steel_beam_colors(
            health_ratio=health_ratio, palette=self.palette
        )
        paint_steel_beam_surface(
            self.image,
            base_color=base_color,
            line_color=line_color,
            health_ratio=health_ratio,
        )
        paint_wall_damage_overlay(
            self.image,
            health_ratio=health_ratio,
            seed=self._damage_visual_seed,
            variant_index=self._damage_overlay_variant,
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
