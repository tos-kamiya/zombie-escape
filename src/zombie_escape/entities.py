"""Sprite and entity definitions for zombie_escape."""

from __future__ import annotations

import math
from typing import Callable, Iterable, Sequence, cast

try:
    from typing import Self
except ImportError:  # pragma: no cover - Python 3.10 fallback
    from typing_extensions import Self

import pygame
from pygame import rect

from .entities_constants import (
    BUDDY_FOLLOW_SPEED,
    BUDDY_RADIUS,
    CAR_HEALTH,
    CAR_HEIGHT,
    CAR_SPEED,
    CAR_WALL_DAMAGE,
    CAR_WIDTH,
    FAST_ZOMBIE_BASE_SPEED,
    FLASHLIGHT_HEIGHT,
    FLASHLIGHT_WIDTH,
    FUEL_CAN_HEIGHT,
    FUEL_CAN_WIDTH,
    INTERNAL_WALL_BEVEL_DEPTH,
    INTERNAL_WALL_HEALTH,
    PLAYER_RADIUS,
    PLAYER_SPEED,
    PLAYER_WALL_DAMAGE,
    STEEL_BEAM_HEALTH,
    SURVIVOR_APPROACH_RADIUS,
    SURVIVOR_APPROACH_SPEED,
    SURVIVOR_RADIUS,
    ZOMBIE_AGING_DURATION_FRAMES,
    ZOMBIE_AGING_MIN_SPEED_RATIO,
    ZOMBIE_RADIUS,
    ZOMBIE_SEPARATION_DISTANCE,
    ZOMBIE_SIGHT_RANGE,
    ZOMBIE_SPEED,
    ZOMBIE_TRACKER_SCAN_INTERVAL_MS,
    ZOMBIE_TRACKER_SCAN_RADIUS_MULTIPLIER,
    ZOMBIE_TRACKER_SCENT_RADIUS,
    ZOMBIE_TRACKER_SCENT_TOP_K,
    ZOMBIE_TRACKER_SIGHT_RANGE,
    ZOMBIE_TRACKER_WANDER_INTERVAL_MS,
    ZOMBIE_WALL_DAMAGE,
    ZOMBIE_WALL_FOLLOW_LOST_WALL_MS,
    ZOMBIE_WALL_FOLLOW_PROBE_ANGLE_DEG,
    ZOMBIE_WALL_FOLLOW_PROBE_STEP,
    ZOMBIE_WALL_FOLLOW_SENSOR_DISTANCE,
    ZOMBIE_WALL_FOLLOW_TARGET_GAP,
    ZOMBIE_WANDER_INTERVAL_MS,
)
from .gameplay.constants import FOOTPRINT_STEP_DISTANCE
from .models import Footprint
from .render_assets import (
    EnvironmentPalette,
    build_beveled_polygon,
    build_car_surface,
    build_flashlight_surface,
    build_fuel_can_surface,
    build_player_surface,
    build_survivor_surface,
    build_zombie_surface,
    paint_car_surface,
    paint_steel_beam_surface,
    paint_wall_surface,
    paint_zombie_surface,
    resolve_car_color,
    resolve_steel_beam_colors,
    resolve_wall_colors,
)
from .rng import get_rng
from .screen_constants import SCREEN_HEIGHT, SCREEN_WIDTH
from .world_grid import WallIndex, apply_tile_edge_nudge, walls_for_radius

RNG = get_rng()


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
        health_ratio = max(0, self.health / self.max_health)
        base_color, line_color = resolve_steel_beam_colors(
            health_ratio=health_ratio, palette=self.palette
        )
        paint_steel_beam_surface(
            self.image,
            base_color=base_color,
            line_color=line_color,
            health_ratio=health_ratio,
        )


MovementStrategy = Callable[
    [
        "Zombie",
        tuple[int, int],
        list[Wall],
        list[Footprint],
        int,
        int,
        int,
        set[tuple[int, int]] | None,
    ],
    tuple[float, float],
]
def _sprite_center_and_radius(
    sprite: pygame.sprite.Sprite,
) -> tuple[tuple[int, int], float]:
    center = sprite.rect.center
    if hasattr(sprite, "radius"):
        radius = float(sprite.radius)
    else:
        radius = float(max(sprite.rect.width, sprite.rect.height) / 2)
    return center, radius


def _walls_for_sprite(
    sprite: pygame.sprite.Sprite,
    wall_index: WallIndex,
    *,
    cell_size: int,
    grid_cols: int | None = None,
    grid_rows: int | None = None,
) -> list[Wall]:
    center, radius = _sprite_center_and_radius(sprite)
    return walls_for_radius(
        wall_index,
        center,
        radius,
        cell_size=cell_size,
        grid_cols=grid_cols,
        grid_rows=grid_rows,
    )


def _circle_rect_collision(
    center: tuple[float, float], radius: float, rect_obj: rect.Rect
) -> bool:
    """Return True if a circle overlaps the provided rectangle."""
    cx, cy = center
    closest_x = max(rect_obj.left, min(cx, rect_obj.right))
    closest_y = max(rect_obj.top, min(cy, rect_obj.bottom))
    dx = cx - closest_x
    dy = cy - closest_y
    return dx * dx + dy * dy <= radius * radius


def _build_beveled_polygon(
    width: int,
    height: int,
    depth: int,
    bevels: tuple[bool, bool, bool, bool],
) -> list[tuple[int, int]]:
    return build_beveled_polygon(width, height, depth, bevels)


def _point_in_polygon(
    point: tuple[float, float], polygon: Sequence[tuple[float, float]]
) -> bool:
    x, y = point
    inside = False
    count = len(polygon)
    j = count - 1
    for i in range(count):
        xi, yi = polygon[i]
        xj, yj = polygon[j]
        intersects = (yi > y) != (yj > y) and (
            x < (xj - xi) * (y - yi) / (yj - yi + 0.000001) + xi
        )
        if intersects:
            inside = not inside
        j = i
    return inside


def _segments_intersect(
    a1: tuple[float, float],
    a2: tuple[float, float],
    b1: tuple[float, float],
    b2: tuple[float, float],
) -> bool:
    def orient(
        p: tuple[float, float], q: tuple[float, float], r: tuple[float, float]
    ) -> float:
        return (q[0] - p[0]) * (r[1] - p[1]) - (q[1] - p[1]) * (r[0] - p[0])

    def on_segment(
        p: tuple[float, float], q: tuple[float, float], r: tuple[float, float]
    ) -> bool:
        return min(p[0], r[0]) <= q[0] <= max(p[0], r[0]) and min(p[1], r[1]) <= q[
            1
        ] <= max(p[1], r[1])

    o1 = orient(a1, a2, b1)
    o2 = orient(a1, a2, b2)
    o3 = orient(b1, b2, a1)
    o4 = orient(b1, b2, a2)

    if (o1 > 0) != (o2 > 0) and (o3 > 0) != (o4 > 0):
        return True
    if o1 == 0 and on_segment(a1, b1, a2):
        return True
    if o2 == 0 and on_segment(a1, b2, a2):
        return True
    if o3 == 0 and on_segment(b1, a1, b2):
        return True
    if o4 == 0 and on_segment(b1, a2, b2):
        return True
    return False


def _point_segment_distance_sq(
    point: tuple[float, float],
    seg_a: tuple[float, float],
    seg_b: tuple[float, float],
) -> float:
    px, py = point
    ax, ay = seg_a
    bx, by = seg_b
    dx = bx - ax
    dy = by - ay
    if dx == 0 and dy == 0:
        return (px - ax) ** 2 + (py - ay) ** 2
    t = ((px - ax) * dx + (py - ay) * dy) / (dx * dx + dy * dy)
    t = max(0.0, min(1.0, t))
    nearest_x = ax + t * dx
    nearest_y = ay + t * dy
    return (px - nearest_x) ** 2 + (py - nearest_y) ** 2


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


def _rect_polygon_collision(
    rect_obj: rect.Rect, polygon: Sequence[tuple[float, float]]
) -> bool:
    min_x = min(p[0] for p in polygon)
    max_x = max(p[0] for p in polygon)
    min_y = min(p[1] for p in polygon)
    max_y = max(p[1] for p in polygon)
    if not rect_obj.colliderect(
        pygame.Rect(min_x, min_y, max_x - min_x, max_y - min_y)
    ):
        return False

    rect_points = [
        (rect_obj.left, rect_obj.top),
        (rect_obj.right, rect_obj.top),
        (rect_obj.right, rect_obj.bottom),
        (rect_obj.left, rect_obj.bottom),
    ]
    if any(_point_in_polygon(p, polygon) for p in rect_points):
        return True
    if any(rect_obj.collidepoint(p) for p in polygon):
        return True

    rect_edges = [
        (rect_points[0], rect_points[1]),
        (rect_points[1], rect_points[2]),
        (rect_points[2], rect_points[3]),
        (rect_points[3], rect_points[0]),
    ]
    poly_edges = [
        (polygon[i], polygon[(i + 1) % len(polygon)]) for i in range(len(polygon))
    ]
    for edge_a in rect_edges:
        for edge_b in poly_edges:
            if _segments_intersect(edge_a[0], edge_a[1], edge_b[0], edge_b[1]):
                return True
    return False


def _circle_polygon_collision(
    center: tuple[float, float],
    radius: float,
    polygon: Sequence[tuple[float, float]],
) -> bool:
    if _point_in_polygon(center, polygon):
        return True
    radius_sq = radius * radius
    for i in range(len(polygon)):
        a = polygon[i]
        b = polygon[(i + 1) % len(polygon)]
        if _point_segment_distance_sq(center, a, b) <= radius_sq:
            return True
    return False


def _collide_sprite_wall(
    sprite: pygame.sprite.Sprite, wall: pygame.sprite.Sprite
) -> bool:
    if hasattr(sprite, "radius"):
        center = sprite.rect.center
        radius = float(sprite.radius)
        if hasattr(wall, "_collides_circle"):
            return wall._collides_circle(center, radius)
        return _circle_rect_collision(center, radius, wall.rect)
    if hasattr(wall, "collides_rect"):
        return wall.collides_rect(sprite.rect)
    if hasattr(sprite, "collides_rect"):
        return sprite.collides_rect(wall.rect)
    return sprite.rect.colliderect(wall.rect)


def _spritecollide_walls(
    sprite: pygame.sprite.Sprite,
    walls: pygame.sprite.Group,
    *,
    dokill: bool = False,
    wall_index: WallIndex | None = None,
    cell_size: int | None = None,
    grid_cols: int | None = None,
    grid_rows: int | None = None,
) -> list[Wall]:
    if wall_index is None:
        return cast(
            list[Wall],
            pygame.sprite.spritecollide(
                sprite, walls, dokill, collided=_collide_sprite_wall
            ),
        )
    if cell_size is None:
        raise ValueError("cell_size is required when using wall_index")
    candidates = _walls_for_sprite(
        sprite,
        wall_index,
        cell_size=cell_size,
        grid_cols=grid_cols,
        grid_rows=grid_rows,
    )
    if not candidates:
        return []
    hit_list = [wall for wall in candidates if _collide_sprite_wall(sprite, wall)]
    if dokill:
        for wall in hit_list:
            wall.kill()
    return hit_list


def spritecollideany_walls(
    sprite: pygame.sprite.Sprite,
    walls: pygame.sprite.Group,
    *,
    wall_index: WallIndex | None = None,
    cell_size: int | None = None,
    grid_cols: int | None = None,
    grid_rows: int | None = None,
) -> Wall | None:
    if wall_index is None:
        return cast(
            Wall | None,
            pygame.sprite.spritecollideany(
                sprite, walls, collided=_collide_sprite_wall
            ),
        )
    if cell_size is None:
        raise ValueError("cell_size is required when using wall_index")
    for wall in _walls_for_sprite(
        sprite,
        wall_index,
        cell_size=cell_size,
        grid_cols=grid_cols,
        grid_rows=grid_rows,
    ):
        if _collide_sprite_wall(sprite, wall):
            return wall
    return None


def _circle_wall_collision(
    center: tuple[float, float],
    radius: float,
    wall: pygame.sprite.Sprite,
) -> bool:
    if hasattr(wall, "_collides_circle"):
        return wall._collides_circle(center, radius)
    return _circle_rect_collision(center, radius, wall.rect)


class Camera:
    def __init__(self: Self, width: int, height: int) -> None:
        self.camera = pygame.Rect(0, 0, width, height)
        self.width = width
        self.height = height

    def apply(self: Self, entity: pygame.sprite.Sprite) -> rect.Rect:
        return entity.rect.move(self.camera.topleft)

    def apply_rect(self: Self, rect: rect.Rect) -> rect.Rect:
        return rect.move(self.camera.topleft)

    def update(self: Self, target: pygame.sprite.Sprite) -> None:
        x = -target.rect.centerx + int(SCREEN_WIDTH / 2)
        y = -target.rect.centery + int(SCREEN_HEIGHT / 2)
        x = max(-(self.width - SCREEN_WIDTH), min(0, x))
        y = max(-(self.height - SCREEN_HEIGHT), min(0, y))
        self.camera = pygame.Rect(x, y, self.width, self.height)


# --- Game Classes ---
class Player(pygame.sprite.Sprite):
    def __init__(
        self: Self,
        x: float,
        y: float,
    ) -> None:
        super().__init__()
        self.radius = PLAYER_RADIUS
        self.image = build_player_surface(self.radius)
        self.rect = self.image.get_rect(center=(x, y))
        self.speed = PLAYER_SPEED
        self.in_car = False
        self.x = float(self.rect.centerx)
        self.y = float(self.rect.centery)

    def move(
        self: Self,
        dx: float,
        dy: float,
        walls: pygame.sprite.Group,
        *,
        wall_index: WallIndex | None = None,
        cell_size: int | None = None,
        level_width: int | None = None,
        level_height: int | None = None,
    ) -> None:
        if self.in_car:
            return

        if level_width is None or level_height is None:
            raise ValueError("level_width/level_height are required for movement")

        if dx != 0:
            self.x += dx
            self.x = min(level_width, max(0, self.x))
            self.rect.centerx = int(self.x)
            hit_list_x = _spritecollide_walls(
                self,
                walls,
                wall_index=wall_index,
                cell_size=cell_size,
            )
            if hit_list_x:
                damage = max(1, PLAYER_WALL_DAMAGE // len(hit_list_x))
                for wall in hit_list_x:
                    if wall.alive():
                        wall._take_damage(amount=damage)
                self.x -= dx * 1.5
                self.rect.centerx = int(self.x)

        if dy != 0:
            self.y += dy
            self.y = min(level_height, max(0, self.y))
            self.rect.centery = int(self.y)
            hit_list_y = _spritecollide_walls(
                self,
                walls,
                wall_index=wall_index,
                cell_size=cell_size,
            )
            if hit_list_y:
                damage = max(1, PLAYER_WALL_DAMAGE // len(hit_list_y))
                for wall in hit_list_y:
                    if wall.alive():
                        wall._take_damage(amount=damage)
                self.y -= dy * 1.5
                self.rect.centery = int(self.y)

        self.rect.center = (int(self.x), int(self.y))


class Survivor(pygame.sprite.Sprite):
    """Civilians that gather near the player; optional buddy behavior."""

    def __init__(
        self: Self,
        x: float,
        y: float,
        *,
        is_buddy: bool = False,
    ) -> None:
        super().__init__()
        self.is_buddy = is_buddy
        self.radius = BUDDY_RADIUS if is_buddy else SURVIVOR_RADIUS
        self.image = build_survivor_surface(
            self.radius,
            is_buddy=is_buddy,
        )
        self.rect = self.image.get_rect(center=(int(x), int(y)))
        self.x = float(self.rect.centerx)
        self.y = float(self.rect.centery)
        self.following = False
        self.rescued = False

    def set_following(self: Self) -> None:
        if self.is_buddy and not self.rescued:
            self.following = True

    def mark_rescued(self: Self) -> None:
        if self.is_buddy:
            self.following = False
            self.rescued = True

    def teleport(self: Self, pos: tuple[int, int]) -> None:
        """Reposition the survivor (used for quiet respawns)."""
        self.x, self.y = float(pos[0]), float(pos[1])
        self.rect.center = (int(self.x), int(self.y))
        if self.is_buddy:
            self.following = False

    def update_behavior(
        self: Self,
        player_pos: tuple[int, int],
        walls: pygame.sprite.Group,
        *,
        wall_index: WallIndex | None = None,
        cell_size: int | None = None,
        wall_cells: set[tuple[int, int]] | None = None,
        bevel_corners: dict[tuple[int, int], tuple[bool, bool, bool, bool]]
        | None = None,
        grid_cols: int | None = None,
        grid_rows: int | None = None,
        level_width: int | None = None,
        level_height: int | None = None,
    ) -> None:
        if level_width is None or level_height is None:
            raise ValueError("level_width/level_height are required for movement")
        if self.is_buddy:
            if self.rescued or not self.following:
                self.rect.center = (int(self.x), int(self.y))
                return

            dx = player_pos[0] - self.x
            dy = player_pos[1] - self.y
            dist_sq = dx * dx + dy * dy
            if dist_sq <= 0:
                self.rect.center = (int(self.x), int(self.y))
                return

            dist = math.sqrt(dist_sq)
            move_x = (dx / dist) * BUDDY_FOLLOW_SPEED
            move_y = (dy / dist) * BUDDY_FOLLOW_SPEED

            if (
                cell_size is not None
                and wall_cells is not None
                and grid_cols is not None
                and grid_rows is not None
            ):
                move_x, move_y = apply_tile_edge_nudge(
                    self.x,
                    self.y,
                    move_x,
                    move_y,
                    cell_size=cell_size,
                    wall_cells=wall_cells,
                    bevel_corners=bevel_corners,
                    grid_cols=grid_cols,
                    grid_rows=grid_rows,
                )

            if move_x:
                self.x += move_x
                self.rect.centerx = int(self.x)
                if spritecollideany_walls(
                    self,
                    walls,
                    wall_index=wall_index,
                    cell_size=cell_size,
                ):
                    self.x -= move_x
                    self.rect.centerx = int(self.x)
            if move_y:
                self.y += move_y
                self.rect.centery = int(self.y)
                if spritecollideany_walls(
                    self,
                    walls,
                    wall_index=wall_index,
                    cell_size=cell_size,
                ):
                    self.y -= move_y
                    self.rect.centery = int(self.y)

            overlap_radius = (self.radius + PLAYER_RADIUS) * 1.05
            dx_after = player_pos[0] - self.x
            dy_after = player_pos[1] - self.y
            dist_after_sq = dx_after * dx_after + dy_after * dy_after
            if 0 < dist_after_sq < overlap_radius * overlap_radius:
                dist_after = math.sqrt(dist_after_sq)
                push_dist = overlap_radius - dist_after
                self.x -= (dx_after / dist_after) * push_dist
                self.y -= (dy_after / dist_after) * push_dist
                self.rect.center = (int(self.x), int(self.y))

            self.x = min(level_width, max(0, self.x))
            self.y = min(level_height, max(0, self.y))
            self.rect.center = (int(self.x), int(self.y))
            return

        dx = player_pos[0] - self.x
        dy = player_pos[1] - self.y
        dist_sq = dx * dx + dy * dy
        if (
            dist_sq <= 0
            or dist_sq > SURVIVOR_APPROACH_RADIUS * SURVIVOR_APPROACH_RADIUS
        ):
            return

        dist = math.sqrt(dist_sq)
        move_x = (dx / dist) * SURVIVOR_APPROACH_SPEED
        move_y = (dy / dist) * SURVIVOR_APPROACH_SPEED

        if (
            cell_size is not None
            and wall_cells is not None
            and grid_cols is not None
            and grid_rows is not None
        ):
            move_x, move_y = apply_tile_edge_nudge(
                self.x,
                self.y,
                move_x,
                move_y,
                cell_size=cell_size,
                wall_cells=wall_cells,
                bevel_corners=bevel_corners,
                grid_cols=grid_cols,
                grid_rows=grid_rows,
            )

        if move_x:
            self.x += move_x
            self.rect.centerx = int(self.x)
            if spritecollideany_walls(
                self,
                walls,
                wall_index=wall_index,
                cell_size=cell_size,
            ):
                self.x -= move_x
                self.rect.centerx = int(self.x)
        if move_y:
            self.y += move_y
            self.rect.centery = int(self.y)
            if spritecollideany_walls(
                self,
                walls,
                wall_index=wall_index,
                cell_size=cell_size,
            ):
                self.y -= move_y
                self.rect.centery = int(self.y)

        self.rect.center = (int(self.x), int(self.y))


def random_position_outside_building(
    level_width: int, level_height: int
) -> tuple[int, int]:
    side = RNG.choice(["top", "bottom", "left", "right"])
    margin = 0
    if side == "top":
        x, y = RNG.randint(0, level_width), -margin
    elif side == "bottom":
        x, y = RNG.randint(0, level_width), level_height + margin
    elif side == "left":
        x, y = -margin, RNG.randint(0, level_height)
    else:
        x, y = level_width + margin, RNG.randint(0, level_height)
    return x, y


def _zombie_tracker_movement(
    zombie: Zombie,
    player_center: tuple[int, int],
    walls: list[Wall],
    footprints: list[Footprint],
    cell_size: int,
    grid_cols: int,
    grid_rows: int,
    outer_wall_cells: set[tuple[int, int]] | None,
) -> tuple[float, float]:
    is_in_sight = zombie._update_mode(player_center, ZOMBIE_TRACKER_SIGHT_RANGE)
    if not is_in_sight:
        _zombie_update_tracker_target(zombie, footprints, walls)
        if zombie.tracker_target_pos is not None:
            return _zombie_move_toward(zombie, zombie.tracker_target_pos)
        return _zombie_wander_move(
            zombie,
            walls,
            cell_size=cell_size,
            grid_cols=grid_cols,
            grid_rows=grid_rows,
            outer_wall_cells=outer_wall_cells,
        )
    return _zombie_move_toward(zombie, player_center)


def _zombie_wander_movement(
    zombie: Zombie,
    _player_center: tuple[int, int],
    walls: list[Wall],
    _footprints: list[Footprint],
    cell_size: int,
    grid_cols: int,
    grid_rows: int,
    outer_wall_cells: set[tuple[int, int]] | None,
) -> tuple[float, float]:
    return _zombie_wander_move(
        zombie,
        walls,
        cell_size=cell_size,
        grid_cols=grid_cols,
        grid_rows=grid_rows,
        outer_wall_cells=outer_wall_cells,
    )


def _zombie_wall_follow_has_wall(
    zombie: Zombie,
    walls: list[Wall],
    angle: float,
    distance: float,
) -> bool:
    check_x = zombie.x + math.cos(angle) * distance
    check_y = zombie.y + math.sin(angle) * distance
    candidates = [
        wall
        for wall in walls
        if abs(wall.rect.centerx - check_x) < 120
        and abs(wall.rect.centery - check_y) < 120
    ]
    return any(
        _circle_wall_collision((check_x, check_y), zombie.radius, wall)
        for wall in candidates
    )


def _zombie_wall_follow_wall_distance(
    zombie: Zombie,
    walls: list[Wall],
    angle: float,
    max_distance: float,
    *,
    step: float = ZOMBIE_WALL_FOLLOW_PROBE_STEP,
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
            _circle_wall_collision((check_x, check_y), zombie.radius, wall)
            for wall in candidates
        ):
            return distance
        distance += step
    return max_distance


def _zombie_wall_follow_movement(
    zombie: Zombie,
    player_center: tuple[int, int],
    walls: list[Wall],
    _footprints: list[Footprint],
    cell_size: int,
    grid_cols: int,
    grid_rows: int,
    outer_wall_cells: set[tuple[int, int]] | None,
) -> tuple[float, float]:
    is_in_sight = zombie._update_mode(player_center, ZOMBIE_TRACKER_SIGHT_RANGE)
    if zombie.wall_follow_angle is None:
        zombie.wall_follow_angle = zombie.wander_angle
    if zombie.wall_follow_side == 0:
        sensor_distance = ZOMBIE_WALL_FOLLOW_SENSOR_DISTANCE + zombie.radius
        forward_angle = zombie.wall_follow_angle
        probe_offset = math.radians(ZOMBIE_WALL_FOLLOW_PROBE_ANGLE_DEG)
        left_angle = forward_angle + probe_offset
        right_angle = forward_angle - probe_offset
        left_dist = _zombie_wall_follow_wall_distance(
            zombie, walls, left_angle, sensor_distance
        )
        right_dist = _zombie_wall_follow_wall_distance(
            zombie, walls, right_angle, sensor_distance
        )
        forward_dist = _zombie_wall_follow_wall_distance(
            zombie, walls, forward_angle, sensor_distance
        )
        left_wall = left_dist < sensor_distance
        right_wall = right_dist < sensor_distance
        forward_wall = forward_dist < sensor_distance
        if left_wall or right_wall or forward_wall:
            if left_wall and not right_wall:
                zombie.wall_follow_side = 1.0
            elif right_wall and not left_wall:
                zombie.wall_follow_side = -1.0
            elif left_wall and right_wall:
                zombie.wall_follow_side = 1.0 if left_dist <= right_dist else -1.0
            else:
                zombie.wall_follow_side = RNG.choice([-1.0, 1.0])
            zombie.wall_follow_last_wall_time = pygame.time.get_ticks()
            zombie.wall_follow_last_side_has_wall = left_wall or right_wall
        else:
            if is_in_sight:
                return _zombie_move_toward(zombie, player_center)
            return _zombie_wander_move(
                zombie,
                walls,
                cell_size=cell_size,
                grid_cols=grid_cols,
                grid_rows=grid_rows,
                outer_wall_cells=outer_wall_cells,
            )

    sensor_distance = ZOMBIE_WALL_FOLLOW_SENSOR_DISTANCE + zombie.radius
    probe_offset = math.radians(ZOMBIE_WALL_FOLLOW_PROBE_ANGLE_DEG)
    side_angle = zombie.wall_follow_angle + zombie.wall_follow_side * probe_offset
    side_dist = _zombie_wall_follow_wall_distance(
        zombie, walls, side_angle, sensor_distance
    )
    forward_dist = _zombie_wall_follow_wall_distance(
        zombie, walls, zombie.wall_follow_angle, sensor_distance
    )
    side_has_wall = side_dist < sensor_distance
    forward_has_wall = forward_dist < sensor_distance
    now = pygame.time.get_ticks()
    wall_recent = (
        zombie.wall_follow_last_wall_time is not None
        and now - zombie.wall_follow_last_wall_time <= ZOMBIE_WALL_FOLLOW_LOST_WALL_MS
    )
    if is_in_sight:
        return _zombie_move_toward(zombie, player_center)

    turn_step = math.radians(5)
    if side_has_wall or forward_has_wall:
        zombie.wall_follow_last_wall_time = now
    if side_has_wall:
        zombie.wall_follow_last_side_has_wall = True
        gap_error = ZOMBIE_WALL_FOLLOW_TARGET_GAP - side_dist
        if abs(gap_error) > 0.1:
            ratio = min(1.0, abs(gap_error) / ZOMBIE_WALL_FOLLOW_TARGET_GAP)
            turn = turn_step * ratio
            if gap_error > 0:
                zombie.wall_follow_angle -= zombie.wall_follow_side * turn
            else:
                zombie.wall_follow_angle += zombie.wall_follow_side * turn
        if forward_dist < ZOMBIE_WALL_FOLLOW_TARGET_GAP:
            zombie.wall_follow_angle -= zombie.wall_follow_side * (turn_step * 1.5)
    else:
        zombie.wall_follow_last_side_has_wall = False
        if forward_has_wall:
            zombie.wall_follow_angle -= zombie.wall_follow_side * turn_step
        elif wall_recent:
            zombie.wall_follow_angle += zombie.wall_follow_side * (turn_step * 0.75)
        else:
            zombie.wall_follow_angle += zombie.wall_follow_side * (math.pi / 2.0)
            zombie.wall_follow_side = 0.0
    zombie.wall_follow_angle %= math.tau

    move_x = math.cos(zombie.wall_follow_angle) * zombie.speed
    move_y = math.sin(zombie.wall_follow_angle) * zombie.speed
    return move_x, move_y


def _zombie_normal_movement(
    zombie: Zombie,
    player_center: tuple[int, int],
    walls: list[Wall],
    _footprints: list[Footprint],
    cell_size: int,
    grid_cols: int,
    grid_rows: int,
    outer_wall_cells: set[tuple[int, int]] | None,
) -> tuple[float, float]:
    is_in_sight = zombie._update_mode(player_center, ZOMBIE_SIGHT_RANGE)
    if not is_in_sight:
        return _zombie_wander_move(
            zombie,
            walls,
            cell_size=cell_size,
            grid_cols=grid_cols,
            grid_rows=grid_rows,
            outer_wall_cells=outer_wall_cells,
        )
    return _zombie_move_toward(zombie, player_center)


def _zombie_update_tracker_target(
    zombie: Zombie,
    footprints: list[Footprint],
    walls: list[Wall],
) -> None:
    now = pygame.time.get_ticks()
    if now - zombie.tracker_last_scan_time < zombie.tracker_scan_interval_ms:
        return
    zombie.tracker_last_scan_time = now
    if not footprints:
        zombie.tracker_target_pos = None
        return
    nearby: list[Footprint] = []
    last_target_time = zombie.tracker_target_time
    scan_radius = ZOMBIE_TRACKER_SCENT_RADIUS * ZOMBIE_TRACKER_SCAN_RADIUS_MULTIPLIER
    scent_radius_sq = scan_radius * scan_radius
    min_target_dist_sq = (FOOTPRINT_STEP_DISTANCE * 0.5) ** 2
    for fp in footprints:
        pos = fp.pos
        fp_time = fp.time
        dx = pos[0] - zombie.x
        dy = pos[1] - zombie.y
        if dx * dx + dy * dy <= min_target_dist_sq:
            continue
        if dx * dx + dy * dy <= scent_radius_sq:
            nearby.append(fp)

    if not nearby:
        return

    nearby.sort(key=lambda fp: fp.time, reverse=True)
    if last_target_time is not None:
        newer = [fp for fp in nearby if fp.time > last_target_time]
    else:
        newer = nearby

    for fp in newer[:ZOMBIE_TRACKER_SCENT_TOP_K]:
        pos = fp.pos
        fp_time = fp.time
        if _line_of_sight_clear((zombie.x, zombie.y), pos, walls):
            zombie.tracker_target_pos = pos
            zombie.tracker_target_time = fp_time
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

    candidates = [fp for fp in nearby if fp.time > last_target_time]
    if not candidates:
        return
    candidates.sort(key=lambda fp: fp.time)
    next_fp = candidates[0]
    zombie.tracker_target_pos = next_fp.pos
    zombie.tracker_target_time = next_fp.time
    return


def _zombie_wander_move(
    zombie: Zombie,
    walls: list[Wall],
    *,
    cell_size: int,
    grid_cols: int,
    grid_rows: int,
    outer_wall_cells: set[tuple[int, int]] | None,
) -> tuple[float, float]:
    now = pygame.time.get_ticks()
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
                    _circle_wall_collision((next_x, next_y), zombie.radius, wall)
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
    return move_x, move_y


def _zombie_move_toward(
    zombie: Zombie, target: tuple[float, float]
) -> tuple[float, float]:
    dx = target[0] - zombie.x
    dy = target[1] - zombie.y
    dist = math.hypot(dx, dy)
    if dist <= 0:
        return 0.0, 0.0
    return (dx / dist) * zombie.speed, (dy / dist) * zombie.speed


class Zombie(pygame.sprite.Sprite):
    def __init__(
        self: Self,
        x: float,
        y: float,
        *,
        speed: float = ZOMBIE_SPEED,
        tracker: bool = False,
        wall_follower: bool = False,
        movement_strategy: MovementStrategy | None = None,
        aging_duration_frames: float = ZOMBIE_AGING_DURATION_FRAMES,
    ) -> None:
        super().__init__()
        self.radius = ZOMBIE_RADIUS
        self.tracker = tracker
        self.wall_follower = wall_follower
        self.carbonized = False
        self.image = build_zombie_surface(
            self.radius, tracker=self.tracker, wall_follower=self.wall_follower
        )
        self._redraw_image()
        self.rect = self.image.get_rect(center=(x, y))
        jitter_base = FAST_ZOMBIE_BASE_SPEED if speed > ZOMBIE_SPEED else ZOMBIE_SPEED
        jitter = jitter_base * 0.2
        base_speed = speed + RNG.uniform(-jitter, jitter)
        self.initial_speed = base_speed
        self.speed = base_speed
        self.x = float(self.rect.centerx)
        self.y = float(self.rect.centery)
        self.was_in_sight = False
        self.age_frames = 0.0
        self.aging_duration_frames = aging_duration_frames
        if movement_strategy is None:
            if tracker:
                movement_strategy = _zombie_tracker_movement
            elif wall_follower:
                movement_strategy = _zombie_wall_follow_movement
            else:
                movement_strategy = _zombie_normal_movement
        self.movement_strategy = movement_strategy
        self.tracker_target_pos: tuple[float, float] | None = None
        self.tracker_target_time: int | None = None
        self.tracker_last_scan_time = 0
        self.tracker_scan_interval_ms = ZOMBIE_TRACKER_SCAN_INTERVAL_MS
        self.wall_follow_side = RNG.choice([-1.0, 1.0]) if wall_follower else 0.0
        self.wall_follow_angle = RNG.uniform(0, math.tau) if wall_follower else None
        self.wall_follow_last_wall_time: int | None = None
        self.wall_follow_last_side_has_wall = False
        self.wall_follow_stuck_flag = False
        self.pos_history: list[tuple[float, float]] = []
        self.wander_angle = RNG.uniform(0, math.tau)
        self.wander_interval_ms = (
            ZOMBIE_TRACKER_WANDER_INTERVAL_MS if tracker else ZOMBIE_WANDER_INTERVAL_MS
        )
        self.last_wander_change_time = pygame.time.get_ticks()
        self.wander_change_interval = max(
            0, self.wander_interval_ms + RNG.randint(-500, 500)
        )

    def _redraw_image(self: Self, palm_angle: float | None = None) -> None:
        paint_zombie_surface(
            self.image,
            radius=self.radius,
            palm_angle=palm_angle,
            tracker=self.tracker,
            wall_follower=self.wall_follower,
        )

    def _update_mode(
        self: Self, player_center: tuple[int, int], sight_range: float
    ) -> bool:
        dx_target = player_center[0] - self.x
        dy_target = player_center[1] - self.y
        dist_to_player_sq = dx_target * dx_target + dy_target * dy_target
        is_in_sight = dist_to_player_sq <= sight_range * sight_range
        self.was_in_sight = is_in_sight
        return is_in_sight

    def _handle_wall_collision(
        self: Self, next_x: float, next_y: float, walls: list[Wall]
    ) -> tuple[float, float]:
        final_x, final_y = next_x, next_y

        possible_walls = [
            w
            for w in walls
            if abs(w.rect.centerx - self.x) < 100 and abs(w.rect.centery - self.y) < 100
        ]

        for wall in possible_walls:
            collides = _circle_wall_collision((next_x, self.y), self.radius, wall)
            if collides:
                if wall.alive():
                    wall._take_damage(amount=ZOMBIE_WALL_DAMAGE)
                if wall.alive():
                    final_x = self.x
                    break

        for wall in possible_walls:
            collides = _circle_wall_collision((final_x, next_y), self.radius, wall)
            if collides:
                if wall.alive():
                    wall._take_damage(amount=ZOMBIE_WALL_DAMAGE)
                if wall.alive():
                    final_y = self.y
                    break

        return final_x, final_y

    def _avoid_other_zombies(
        self: Self,
        move_x: float,
        move_y: float,
        zombies: Iterable[Zombie],
    ) -> tuple[float, float]:
        """If another zombie is too close, steer directly away from the closest one."""
        next_x = self.x + move_x
        next_y = self.y + move_y

        closest: Zombie | None = None
        closest_dist_sq = ZOMBIE_SEPARATION_DISTANCE * ZOMBIE_SEPARATION_DISTANCE
        for other in zombies:
            if other is self or not other.alive():
                continue
            dx = other.x - next_x
            dy = other.y - next_y
            if (
                abs(dx) > ZOMBIE_SEPARATION_DISTANCE
                or abs(dy) > ZOMBIE_SEPARATION_DISTANCE
            ):
                continue
            dist_sq = dx * dx + dy * dy
            if dist_sq < closest_dist_sq:
                closest = other
                closest_dist_sq = dist_sq

        if closest is None:
            return move_x, move_y

        if self.wall_follower:
            other_radius = float(closest.radius)
            bump_dist_sq = (self.radius + other_radius) ** 2
            if closest_dist_sq < bump_dist_sq and RNG.random() < 0.1:
                if self.wall_follow_angle is None:
                    self.wall_follow_angle = self.wander_angle
                self.wall_follow_angle = (self.wall_follow_angle + math.pi) % math.tau
                self.wall_follow_side *= -1.0
                return (
                    math.cos(self.wall_follow_angle) * self.speed,
                    math.sin(self.wall_follow_angle) * self.speed,
                )

        away_dx = next_x - closest.x
        away_dy = next_y - closest.y
        away_dist = math.hypot(away_dx, away_dy)
        if away_dist == 0:
            angle = RNG.uniform(0, 2 * math.pi)
            away_dx, away_dy = math.cos(angle), math.sin(angle)
            away_dist = 1

        move_x = (away_dx / away_dist) * self.speed
        move_y = (away_dy / away_dist) * self.speed
        return move_x, move_y

    def _apply_aging(self: Self) -> None:
        """Slowly reduce zombie speed over time to simulate decay."""
        if self.aging_duration_frames <= 0:
            return
        if self.age_frames < self.aging_duration_frames:
            self.age_frames += 1
        progress = min(1.0, self.age_frames / self.aging_duration_frames)
        slowdown_ratio = 1.0 - progress * (1.0 - ZOMBIE_AGING_MIN_SPEED_RATIO)
        self.speed = self.initial_speed * slowdown_ratio

    def _update_stuck_state(self: Self) -> None:
        history = self.pos_history
        history.append((self.x, self.y))
        if len(history) > 20:
            history.pop(0)
            max_dist_sq = max(
                (self.x - hx) ** 2 + (self.y - hy) ** 2 for hx, hy in history
            )
            self.wall_follow_stuck_flag = max_dist_sq < 25
        if not self.wall_follow_stuck_flag:
            return
        if self.wall_follower:
            if self.wall_follow_angle is None:
                self.wall_follow_angle = self.wander_angle
            self.wall_follow_angle = (self.wall_follow_angle + math.pi) % math.tau
            self.wall_follow_side *= -1.0
        self.wall_follow_stuck_flag = False
        self.pos_history = []

    def update(
        self: Self,
        player_center: tuple[int, int],
        walls: list[Wall],
        nearby_zombies: Iterable[Zombie],
        footprints: list[Footprint] | None = None,
        *,
        cell_size: int,
        grid_cols: int,
        grid_rows: int,
        level_width: int,
        level_height: int,
        outer_wall_cells: set[tuple[int, int]] | None = None,
        wall_cells: set[tuple[int, int]] | None = None,
        bevel_corners: dict[tuple[int, int], tuple[bool, bool, bool, bool]]
        | None = None,
    ) -> None:
        if self.carbonized:
            return
        self._update_stuck_state()
        self._apply_aging()
        dx_player = player_center[0] - self.x
        dy_player = player_center[1] - self.y
        dist_to_player_sq = dx_player * dx_player + dy_player * dy_player
        avoid_radius = max(SCREEN_WIDTH, SCREEN_HEIGHT) * 2
        avoid_radius_sq = avoid_radius * avoid_radius
        move_x, move_y = self.movement_strategy(
            self,
            player_center,
            walls,
            footprints or [],
            cell_size,
            grid_cols,
            grid_rows,
            outer_wall_cells,
        )
        if dist_to_player_sq <= avoid_radius_sq or self.wall_follower:
            move_x, move_y = self._avoid_other_zombies(move_x, move_y, nearby_zombies)
        if wall_cells is not None:
            move_x, move_y = apply_tile_edge_nudge(
                self.x,
                self.y,
                move_x,
                move_y,
                cell_size=cell_size,
                wall_cells=wall_cells,
                bevel_corners=bevel_corners,
                grid_cols=grid_cols,
                grid_rows=grid_rows,
            )
        if self.wall_follower and self.wall_follow_side != 0:
            if move_x != 0 or move_y != 0:
                heading = math.atan2(move_y, move_x)
            elif self.wall_follow_angle is not None:
                heading = self.wall_follow_angle
            else:
                heading = self.wander_angle
            if self.wall_follow_side > 0:
                palm_angle = heading + (math.pi / 2.0)
            else:
                palm_angle = heading - (math.pi / 2.0)
            self._redraw_image(palm_angle)
        final_x, final_y = self._handle_wall_collision(
            self.x + move_x, self.y + move_y, walls
        )

        if not (0 <= final_x < level_width and 0 <= final_y < level_height):
            self.kill()
            return

        self.x = final_x
        self.y = final_y
        self.rect.center = (int(self.x), int(self.y))

    def carbonize(self: Self) -> None:
        if self.carbonized:
            return
        self.carbonized = True
        self.speed = 0
        self.image.fill((0, 0, 0, 0))
        color = (80, 80, 80)
        pygame.draw.circle(self.image, color, (self.radius, self.radius), self.radius)
        pygame.draw.circle(
            self.image, (30, 30, 30), (self.radius, self.radius), self.radius, width=1
        )


class Car(pygame.sprite.Sprite):
    def __init__(self: Self, x: int, y: int, *, appearance: str = "default") -> None:
        super().__init__()
        self.original_image = build_car_surface(CAR_WIDTH, CAR_HEIGHT)
        self.appearance = appearance
        self.image = self.original_image.copy()
        self.rect = self.image.get_rect(center=(x, y))
        self.speed = CAR_SPEED
        self.angle = 0
        self.x = float(self.rect.centerx)
        self.y = float(self.rect.centery)
        self.health = CAR_HEALTH
        self.max_health = CAR_HEALTH
        self.collision_radius = _car_body_radius(CAR_WIDTH, CAR_HEIGHT)
        self._update_color()

    def _take_damage(self: Self, amount: int) -> None:
        if self.health > 0:
            self.health -= amount
            self._update_color()

    def _update_color(self: Self) -> None:
        health_ratio = max(0, self.health / self.max_health)
        color = resolve_car_color(health_ratio=health_ratio, appearance=self.appearance)
        paint_car_surface(
            self.original_image,
            width=CAR_WIDTH,
            height=CAR_HEIGHT,
            color=color,
        )
        self.image = pygame.transform.rotate(self.original_image, self.angle)
        old_center = self.rect.center
        self.rect = self.image.get_rect(center=old_center)

    def move(
        self: Self,
        dx: float,
        dy: float,
        walls: Iterable[Wall],
        *,
        walls_nearby: bool = False,
    ) -> None:
        if self.health <= 0:
            return
        if dx == 0 and dy == 0:
            self.rect.center = (int(self.x), int(self.y))
            return
        target_angle = math.degrees(math.atan2(-dy, dx)) - 90
        self.angle = target_angle
        self.image = pygame.transform.rotate(self.original_image, self.angle)
        old_center = (self.x, self.y)
        self.rect = self.image.get_rect(center=old_center)
        new_x = self.x + dx
        new_y = self.y + dy

        hit_walls = []
        if walls_nearby:
            possible_walls = list(walls)
        else:
            possible_walls = [
                w
                for w in walls
                if abs(w.rect.centery - self.y) < 100
                and abs(w.rect.centerx - new_x) < 100
            ]
        car_center = (new_x, new_y)
        for wall in possible_walls:
            if _circle_wall_collision(car_center, self.collision_radius, wall):
                hit_walls.append(wall)
        if hit_walls:
            self._take_damage(CAR_WALL_DAMAGE)
            hit_walls.sort(
                key=lambda w: (w.rect.centery - self.y) ** 2
                + (w.rect.centerx - self.x) ** 2
            )
            nearest_wall = hit_walls[0]
            new_x += (self.x - nearest_wall.rect.centerx) * 1.2
            new_y += (self.y - nearest_wall.rect.centery) * 1.2

        self.x = new_x
        self.y = new_y
        self.rect.center = (int(self.x), int(self.y))


class FuelCan(pygame.sprite.Sprite):
    """Simple fuel can collectible used in Stage 2."""

    def __init__(self: Self, x: int, y: int) -> None:
        super().__init__()
        self.image = build_fuel_can_surface(FUEL_CAN_WIDTH, FUEL_CAN_HEIGHT)
        self.rect = self.image.get_rect(center=(x, y))


class Flashlight(pygame.sprite.Sprite):
    """Flashlight pickup that expands the player's visible radius when collected."""

    def __init__(self: Self, x: int, y: int) -> None:
        super().__init__()
        self.image = build_flashlight_surface(FLASHLIGHT_WIDTH, FLASHLIGHT_HEIGHT)
        self.rect = self.image.get_rect(center=(x, y))


def _car_body_radius(width: float, height: float) -> float:
    """Approximate car collision radius using only its own dimensions."""
    return min(width, height) / 2


__all__ = [
    "Wall",
    "SteelBeam",
    "Camera",
    "Player",
    "Survivor",
    "Zombie",
    "Car",
    "FuelCan",
    "Flashlight",
    "random_position_outside_building",
]
