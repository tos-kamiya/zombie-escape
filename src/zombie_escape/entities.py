"""Sprite and entity definitions for zombie_escape."""

from __future__ import annotations

import math
from typing import Callable, Iterable, Self, Sequence

import pygame
from pygame import rect

from .colors import (
    BLACK,
    BLUE,
    DARK_RED,
    INTERNAL_WALL_BORDER_COLOR,
    INTERNAL_WALL_COLOR,
    ORANGE,
    RED,
    STEEL_BEAM_COLOR,
    STEEL_BEAM_LINE_COLOR,
    YELLOW,
)
from .gameplay_constants import (
    CAR_HEALTH,
    CAR_HEIGHT,
    CAR_SPEED,
    CAR_WALL_DAMAGE,
    CAR_WIDTH,
    COMPANION_COLOR,
    COMPANION_FOLLOW_SPEED,
    COMPANION_RADIUS,
    FAST_ZOMBIE_BASE_SPEED,
    FLASHLIGHT_HEIGHT,
    FLASHLIGHT_WIDTH,
    FUEL_CAN_HEIGHT,
    FUEL_CAN_WIDTH,
    HUMANOID_OUTLINE_COLOR,
    HUMANOID_OUTLINE_WIDTH,
    INTERNAL_WALL_BEVEL_DEPTH,
    INTERNAL_WALL_HEALTH,
    PLAYER_RADIUS,
    PLAYER_SPEED,
    PLAYER_WALL_DAMAGE,
    STEEL_BEAM_HEALTH,
    SURVIVOR_APPROACH_RADIUS,
    SURVIVOR_APPROACH_SPEED,
    SURVIVOR_COLOR,
    SURVIVOR_RADIUS,
    ZOMBIE_AGING_DURATION_FRAMES,
    ZOMBIE_AGING_MIN_SPEED_RATIO,
    ZOMBIE_RADIUS,
    ZOMBIE_SEPARATION_DISTANCE,
    ZOMBIE_SIGHT_RANGE,
    ZOMBIE_SPEED,
    ZOMBIE_TRACKER_SCENT_RADIUS,
    ZOMBIE_TRACKER_SIGHT_RANGE,
    ZOMBIE_TRACKER_WANDER_INTERVAL_MS,
    ZOMBIE_WALL_DAMAGE,
    ZOMBIE_WALL_FOLLOW_LOST_WALL_MS,
    ZOMBIE_WALL_FOLLOW_SENSOR_DISTANCE,
    ZOMBIE_WANDER_INTERVAL_MS,
    car_body_radius,
)
from .level_constants import CELL_SIZE, GRID_COLS, GRID_ROWS, LEVEL_HEIGHT, LEVEL_WIDTH
from .screen_constants import SCREEN_HEIGHT, SCREEN_WIDTH
from .rng import get_rng

RNG = get_rng()

MovementStrategy = Callable[
    ["Zombie", tuple[int, int], list["Wall"], list[dict[str, object]]],
    tuple[float, float],
]


def circle_rect_collision(
    center: tuple[float, float], radius: float, rect_obj: rect.Rect
) -> bool:
    """Return True if a circle overlaps the provided rectangle."""
    cx, cy = center
    closest_x = max(rect_obj.left, min(cx, rect_obj.right))
    closest_y = max(rect_obj.top, min(cy, rect_obj.bottom))
    dx = cx - closest_x
    dy = cy - closest_y
    return dx * dx + dy * dy <= radius * radius


def _draw_outlined_circle(
    surface: pygame.Surface,
    center: tuple[int, int],
    radius: int,
    fill_color: tuple[int, int, int],
    outline_color: tuple[int, int, int],
    outline_width: int,
) -> None:
    pygame.draw.circle(surface, fill_color, center, radius)
    if outline_width > 0:
        pygame.draw.circle(surface, outline_color, center, radius, width=outline_width)


def _build_beveled_polygon(
    width: int,
    height: int,
    depth: int,
    bevels: tuple[bool, bool, bool, bool],
) -> list[tuple[int, int]]:
    d = max(0, min(depth, width // 2, height // 2))
    if d == 0 or not any(bevels):
        return [(0, 0), (width, 0), (width, height), (0, height)]

    segments = max(4, d // 2)
    tl, tr, br, bl = bevels
    points: list[tuple[int, int]] = []

    def add_point(x: float, y: float) -> None:
        point = (int(round(x)), int(round(y)))
        if not points or points[-1] != point:
            points.append(point)

    def add_arc(
        center_x: float,
        center_y: float,
        radius: float,
        start_deg: float,
        end_deg: float,
        *,
        skip_first: bool = False,
        skip_last: bool = False,
    ) -> None:
        for i in range(segments + 1):
            if skip_first and i == 0:
                continue
            if skip_last and i == segments:
                continue
            t = i / segments
            angle = math.radians(start_deg + (end_deg - start_deg) * t)
            add_point(
                center_x + radius * math.cos(angle),
                center_y + radius * math.sin(angle),
            )

    add_point(d if tl else 0, 0)
    if tr:
        add_point(width - d, 0)
        add_arc(width - d, d, d, -90, 0, skip_first=True)
    else:
        add_point(width, 0)
    if br:
        add_point(width, height - d)
        add_arc(width - d, height - d, d, 0, 90, skip_first=True)
    else:
        add_point(width, height)
    if bl:
        add_point(d, height)
        add_arc(d, height - d, d, 90, 180, skip_first=True)
    else:
        add_point(0, height)
    if tl:
        add_point(0, d)
        add_arc(d, d, d, 180, 270, skip_first=True, skip_last=True)
    return points


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


def rect_polygon_collision(
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


def circle_polygon_collision(
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


def collide_sprite_wall(
    sprite: pygame.sprite.Sprite, wall: pygame.sprite.Sprite
) -> bool:
    if hasattr(sprite, "radius"):
        center = sprite.rect.center
        radius = float(getattr(sprite, "radius"))
        if hasattr(wall, "collides_circle"):
            return wall.collides_circle(center, radius)
        return circle_rect_collision(center, radius, wall.rect)
    if hasattr(wall, "collides_rect"):
        return wall.collides_rect(sprite.rect)
    if hasattr(sprite, "collides_rect"):
        return sprite.collides_rect(wall.rect)
    return sprite.rect.colliderect(wall.rect)


def spritecollide_walls(
    sprite: pygame.sprite.Sprite,
    walls: pygame.sprite.Group,
    *,
    dokill: bool = False,
) -> list[pygame.sprite.Sprite]:
    return pygame.sprite.spritecollide(
        sprite, walls, dokill, collided=collide_sprite_wall
    )


def spritecollideany_walls(
    sprite: pygame.sprite.Sprite,
    walls: pygame.sprite.Group,
) -> pygame.sprite.Sprite | None:
    return pygame.sprite.spritecollideany(sprite, walls, collided=collide_sprite_wall)


def circle_wall_collision(
    center: tuple[float, float],
    radius: float,
    wall: pygame.sprite.Sprite,
) -> bool:
    if hasattr(wall, "collides_circle"):
        return wall.collides_circle(center, radius)
    return circle_rect_collision(center, radius, wall.rect)


# --- Camera Class ---
class Wall(pygame.sprite.Sprite):
    def __init__(
        self: Self,
        x: int,
        y: int,
        width: int,
        height: int,
        *,
        health: int = INTERNAL_WALL_HEALTH,
        color: tuple[int, int, int] = INTERNAL_WALL_COLOR,
        border_color: tuple[int, int, int] = INTERNAL_WALL_BORDER_COLOR,
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
        self.base_color = color
        self.border_base_color = border_color
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
        self.update_color()
        self.rect = self.image.get_rect(topleft=(x, y))
        self._collision_polygon = (
            [(px + self.rect.x, py + self.rect.y) for px, py in self._local_polygon]
            if self.bevel_depth > 0 and any(self.bevel_mask)
            else None
        )

    def take_damage(self: Self, *, amount: int = 1) -> None:
        if self.health > 0:
            self.health -= amount
            self.update_color()
            if self.health <= 0:
                if self.on_destroy:
                    try:
                        self.on_destroy(self)
                    except Exception as exc:
                        print(f"Wall destroy callback failed: {exc}")
                self.kill()

    def update_color(self: Self) -> None:
        self.image.fill((0, 0, 0, 0))
        if self.health <= 0:
            health_ratio = 0
            fill_color = (40, 40, 40)
        else:
            health_ratio = max(0, self.health / self.max_health)
            mix = (
                0.6 + 0.4 * health_ratio
            )  # keep at least 60% of the base color even when nearly destroyed
            r = int(self.base_color[0] * mix)
            g = int(self.base_color[1] * mix)
            b = int(self.base_color[2] * mix)
            fill_color = (r, g, b)
        # Bright edge to separate walls from floor
        br = int(self.border_base_color[0] * (0.6 + 0.4 * health_ratio))
        bg = int(self.border_base_color[1] * (0.6 + 0.4 * health_ratio))
        bb = int(self.border_base_color[2] * (0.6 + 0.4 * health_ratio))
        border_color = (br, bg, bb)

        rect_obj = self.image.get_rect()
        side_height = 0
        if self.draw_bottom_side:
            side_height = max(1, int(rect_obj.height * self.bottom_side_ratio))

        def draw_face(
            target: pygame.Surface,
            *,
            face_size: tuple[int, int] | None = None,
        ) -> None:
            face_width, face_height = face_size or target.get_size()
            if self.bevel_depth > 0 and any(self.bevel_mask):
                face_polygon = _build_beveled_polygon(
                    face_width, face_height, self.bevel_depth, self.bevel_mask
                )
                pygame.draw.polygon(target, border_color, face_polygon)
            else:
                target.fill(border_color)
            border_width = 18
            inner_rect = target.get_rect().inflate(-border_width, -border_width)
            if inner_rect.width > 0 and inner_rect.height > 0:
                inner_depth = max(0, self.bevel_depth - border_width)
                if inner_depth > 0 and any(self.bevel_mask):
                    inner_polygon = _build_beveled_polygon(
                        inner_rect.width,
                        inner_rect.height,
                        inner_depth,
                        self.bevel_mask,
                    )
                    inner_points = [
                        (px + inner_rect.x, py + inner_rect.y)
                        for px, py in inner_polygon
                    ]
                    pygame.draw.polygon(target, fill_color, inner_points)
                else:
                    pygame.draw.rect(target, fill_color, inner_rect)

        if self.draw_bottom_side:
            extra_height = max(0, int(self.bevel_depth / 2))
            side_draw_height = min(rect_obj.height, side_height + extra_height)
            side_rect = pygame.Rect(
                rect_obj.left,
                rect_obj.bottom - side_draw_height,
                rect_obj.width,
                side_draw_height,
            )
            side_color = tuple(int(c * self.side_shade_ratio) for c in fill_color)
            side_surface = pygame.Surface(rect_obj.size, pygame.SRCALPHA)
            if self.bevel_depth > 0 and any(self.bevel_mask):
                pygame.draw.polygon(side_surface, side_color, self._local_polygon)
            else:
                pygame.draw.rect(side_surface, side_color, rect_obj)
            self.image.blit(side_surface, side_rect.topleft, area=side_rect)

        if self.draw_bottom_side:
            top_height = max(0, rect_obj.height - side_height)
            top_rect = pygame.Rect(
                rect_obj.left,
                rect_obj.top,
                rect_obj.width,
                rect_obj.height - side_height,
            )
            top_surface = pygame.Surface((rect_obj.width, top_height), pygame.SRCALPHA)
            draw_face(
                top_surface,
                face_size=(rect_obj.width, top_height),
            )
            if top_rect.height > 0:
                self.image.blit(top_surface, top_rect.topleft, area=top_rect)
        else:
            draw_face(self.image)

    def collides_rect(self: Self, rect_obj: rect.Rect) -> bool:
        if self._collision_polygon is None:
            return self.rect.colliderect(rect_obj)
        return rect_polygon_collision(rect_obj, self._collision_polygon)

    def collides_circle(self: Self, center: tuple[float, float], radius: float) -> bool:
        if self._collision_polygon is None:
            return circle_rect_collision(center, radius, self.rect)
        return circle_polygon_collision(center, radius, self._collision_polygon)

    def set_palette_colors(
        self: Self,
        *,
        color: tuple[int, int, int],
        border_color: tuple[int, int, int],
        force: bool = False,
    ) -> None:
        """Update the wall's base colors to match the current ambient palette."""

        if (
            not force
            and self.base_color == color
            and self.border_base_color == border_color
        ):
            return
        self.base_color = color
        self.border_base_color = border_color
        self.update_color()


class SteelBeam(pygame.sprite.Sprite):
    """Single-cell obstacle that behaves like a tougher internal wall."""

    def __init__(
        self: Self, x: int, y: int, size: int, *, health: int = STEEL_BEAM_HEALTH
    ) -> None:
        super().__init__()
        # Slightly inset from the cell size so it reads as a separate object.
        margin = max(3, size // 14)
        inset_size = max(4, size - margin * 2)
        self.image = pygame.Surface((inset_size, inset_size), pygame.SRCALPHA)
        self.health = health
        self.max_health = max(1, health)
        self.base_color = STEEL_BEAM_COLOR
        self.line_color = STEEL_BEAM_LINE_COLOR
        self.update_color()
        self.rect = self.image.get_rect(center=(x + size // 2, y + size // 2))

    def take_damage(self: Self, *, amount: int = 1) -> None:
        if self.health > 0:
            self.health -= amount
            self.update_color()
            if self.health <= 0:
                self.kill()

    def update_color(self: Self) -> None:
        """Render a simple square with crossed diagonals that darkens as damaged."""
        self.image.fill((0, 0, 0, 0))
        if self.health <= 0:
            return
        health_ratio = max(0, self.health / self.max_health)
        fill_mix = 0.55 + 0.45 * health_ratio
        fill_color = tuple(int(c * fill_mix) for c in self.base_color)
        rect_obj = self.image.get_rect()
        side_height = max(1, int(rect_obj.height * 0.1))
        top_rect = pygame.Rect(
            rect_obj.left,
            rect_obj.top,
            rect_obj.width,
            rect_obj.height - side_height,
        )
        side_mix = 0.45 + 0.35 * health_ratio
        side_color = tuple(int(c * side_mix * 0.9) for c in self.base_color)
        side_rect = pygame.Rect(
            rect_obj.left,
            rect_obj.bottom - side_height,
            rect_obj.width,
            side_height,
        )
        pygame.draw.rect(self.image, side_color, side_rect)
        line_mix = 0.7 + 0.3 * health_ratio
        line_color = tuple(int(c * line_mix) for c in self.line_color)
        top_surface = pygame.Surface(top_rect.size, pygame.SRCALPHA)
        local_rect = top_surface.get_rect()
        pygame.draw.rect(top_surface, fill_color, local_rect)
        pygame.draw.rect(top_surface, line_color, local_rect, width=6)
        pygame.draw.line(
            top_surface, line_color, local_rect.topleft, local_rect.bottomright, width=6
        )
        pygame.draw.line(
            top_surface, line_color, local_rect.topright, local_rect.bottomleft, width=6
        )
        self.image.blit(top_surface, top_rect.topleft)


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
    def __init__(self: Self, x: float, y: float) -> None:
        super().__init__()
        self.radius = PLAYER_RADIUS
        self.image = pygame.Surface(
            (self.radius * 2 + 2, self.radius * 2 + 2), pygame.SRCALPHA
        )
        _draw_outlined_circle(
            self.image,
            (self.radius + 1, self.radius + 1),
            self.radius,
            BLUE,
            HUMANOID_OUTLINE_COLOR,
            HUMANOID_OUTLINE_WIDTH,
        )
        self.rect = self.image.get_rect(center=(x, y))
        self.speed = PLAYER_SPEED
        self.in_car = False
        self.x = float(self.rect.centerx)
        self.y = float(self.rect.centery)

    def move(self: Self, dx: float, dy: float, walls: pygame.sprite.Group) -> None:
        if self.in_car:
            return

        if dx != 0:
            self.x += dx
            self.x = min(LEVEL_WIDTH, max(0, self.x))
            self.rect.centerx = int(self.x)
            hit_list_x = spritecollide_walls(self, walls)
            if hit_list_x:
                damage = max(1, PLAYER_WALL_DAMAGE // len(hit_list_x))
                for wall in hit_list_x:
                    if wall.alive():
                        wall.take_damage(amount=damage)
                self.x -= dx * 1.5
                self.rect.centerx = int(self.x)

        if dy != 0:
            self.y += dy
            self.y = min(LEVEL_HEIGHT, max(0, self.y))
            self.rect.centery = int(self.y)
            hit_list_y = spritecollide_walls(self, walls)
            if hit_list_y:
                damage = max(1, PLAYER_WALL_DAMAGE // len(hit_list_y))
                for wall in hit_list_y:
                    if wall.alive():
                        wall.take_damage(amount=damage)
                self.y -= dy * 1.5
                self.rect.centery = int(self.y)

        self.rect.center = (int(self.x), int(self.y))


class Companion(pygame.sprite.Sprite):
    """Simple survivor sprite used in Stage 3."""

    def __init__(self: Self, x: float, y: float) -> None:
        super().__init__()
        self.radius = COMPANION_RADIUS
        self.image = pygame.Surface((self.radius * 2, self.radius * 2), pygame.SRCALPHA)
        _draw_outlined_circle(
            self.image,
            (self.radius, self.radius),
            self.radius,
            COMPANION_COLOR,
            HUMANOID_OUTLINE_COLOR,
            HUMANOID_OUTLINE_WIDTH,
        )
        self.rect = self.image.get_rect(center=(int(x), int(y)))
        self.x = float(self.rect.centerx)
        self.y = float(self.rect.centery)
        self.following = False
        self.rescued = False

    def set_following(self: Self) -> None:
        if not self.rescued:
            self.following = True

    def mark_rescued(self: Self) -> None:
        self.following = False
        self.rescued = True

    def teleport(self: Self, pos: tuple[int, int]) -> None:
        """Reposition the companion (used for quiet respawns)."""
        self.x, self.y = float(pos[0]), float(pos[1])
        self.rect.center = (int(self.x), int(self.y))
        self.following = False

    def update_follow(
        self: Self, target_pos: tuple[float, float], walls: pygame.sprite.Group
    ) -> None:
        """Follow the target at a slightly slower speed than the player."""
        if self.rescued or not self.following:
            self.rect.center = (int(self.x), int(self.y))
            return

        dx = target_pos[0] - self.x
        dy = target_pos[1] - self.y
        dist = math.hypot(dx, dy)
        if dist <= 0:
            self.rect.center = (int(self.x), int(self.y))
            return

        move_x = (dx / dist) * COMPANION_FOLLOW_SPEED
        move_y = (dy / dist) * COMPANION_FOLLOW_SPEED

        if move_x != 0:
            self.x += move_x
            self.rect.centerx = int(self.x)
            if spritecollideany_walls(self, walls):
                self.x -= move_x
                self.rect.centerx = int(self.x)
        if move_y != 0:
            self.y += move_y
            self.rect.centery = int(self.y)
            if spritecollideany_walls(self, walls):
                self.y -= move_y
                self.rect.centery = int(self.y)

        # Avoid fully overlapping the player target
        overlap_radius = (self.radius + PLAYER_RADIUS) * 1.05
        dx_after = target_pos[0] - self.x
        dy_after = target_pos[1] - self.y
        dist_after = math.hypot(dx_after, dy_after)
        if dist_after > 0 and dist_after < overlap_radius:
            push_dist = overlap_radius - dist_after
            self.x -= (dx_after / dist_after) * push_dist
            self.y -= (dy_after / dist_after) * push_dist
            self.rect.center = (int(self.x), int(self.y))

        self.x = min(LEVEL_WIDTH, max(0, self.x))
        self.y = min(LEVEL_HEIGHT, max(0, self.y))
        self.rect.center = (int(self.x), int(self.y))


class Survivor(pygame.sprite.Sprite):
    """Civilians that gather near the player during Stage 4."""

    def __init__(self: Self, x: float, y: float) -> None:
        super().__init__()
        self.radius = SURVIVOR_RADIUS
        self.image = pygame.Surface((self.radius * 2, self.radius * 2), pygame.SRCALPHA)
        _draw_outlined_circle(
            self.image,
            (self.radius, self.radius),
            self.radius,
            SURVIVOR_COLOR,
            HUMANOID_OUTLINE_COLOR,
            HUMANOID_OUTLINE_WIDTH,
        )
        self.rect = self.image.get_rect(center=(int(x), int(y)))
        self.x = float(self.rect.centerx)
        self.y = float(self.rect.centery)

    def update_behavior(
        self: Self, player_pos: tuple[int, int], walls: pygame.sprite.Group
    ) -> None:
        dx = player_pos[0] - self.x
        dy = player_pos[1] - self.y
        dist = math.hypot(dx, dy)
        if dist <= 0 or dist > SURVIVOR_APPROACH_RADIUS:
            return

        move_x = (dx / dist) * SURVIVOR_APPROACH_SPEED
        move_y = (dy / dist) * SURVIVOR_APPROACH_SPEED

        if move_x:
            self.x += move_x
            self.rect.centerx = int(self.x)
            if spritecollideany_walls(self, walls):
                self.x -= move_x
                self.rect.centerx = int(self.x)
        if move_y:
            self.y += move_y
            self.rect.centery = int(self.y)
            if spritecollideany_walls(self, walls):
                self.y -= move_y
                self.rect.centery = int(self.y)

        self.rect.center = (int(self.x), int(self.y))


def random_position_outside_building() -> tuple[int, int]:
    side = RNG.choice(["top", "bottom", "left", "right"])
    margin = 0
    if side == "top":
        x, y = RNG.randint(0, LEVEL_WIDTH), -margin
    elif side == "bottom":
        x, y = RNG.randint(0, LEVEL_WIDTH), LEVEL_HEIGHT + margin
    elif side == "left":
        x, y = -margin, RNG.randint(0, LEVEL_HEIGHT)
    else:
        x, y = LEVEL_WIDTH + margin, RNG.randint(0, LEVEL_HEIGHT)
    return x, y


def zombie_tracker_movement(
    zombie: Zombie,
    player_center: tuple[int, int],
    walls: list[Wall],
    footprints: list[dict[str, object]],
) -> tuple[float, float]:
    is_in_sight = zombie._update_mode(player_center, ZOMBIE_TRACKER_SIGHT_RANGE)
    if not is_in_sight:
        zombie_update_tracker_target(zombie, footprints)
        if zombie.tracker_target_pos is not None:
            return zombie_move_toward(zombie, zombie.tracker_target_pos)
        return zombie_wander_move(zombie, walls)
    return zombie_move_toward(zombie, player_center)


def zombie_wall_follow_has_wall(
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
        circle_wall_collision((check_x, check_y), zombie.radius, wall)
        for wall in candidates
    )


def zombie_wall_follow_movement(
    zombie: Zombie,
    player_center: tuple[int, int],
    walls: list[Wall],
    _footprints: list[dict[str, object]],
) -> tuple[float, float]:
    is_in_sight = zombie._update_mode(player_center, ZOMBIE_TRACKER_SIGHT_RANGE)
    if zombie.wall_follow_angle is None:
        zombie.wall_follow_angle = zombie.wander_angle
    if zombie.wall_follow_side == 0:
        sensor_distance = ZOMBIE_WALL_FOLLOW_SENSOR_DISTANCE + zombie.radius
        forward_angle = zombie.wall_follow_angle
        left_angle = forward_angle + math.pi / 2.0
        right_angle = forward_angle - math.pi / 2.0
        left_wall = zombie_wall_follow_has_wall(
            zombie, walls, left_angle, sensor_distance
        )
        right_wall = zombie_wall_follow_has_wall(
            zombie, walls, right_angle, sensor_distance
        )
        forward_wall = zombie_wall_follow_has_wall(
            zombie, walls, forward_angle, sensor_distance
        )
        if left_wall or right_wall or forward_wall:
            if left_wall and not right_wall:
                zombie.wall_follow_side = 1.0
            elif right_wall and not left_wall:
                zombie.wall_follow_side = -1.0
            else:
                zombie.wall_follow_side = RNG.choice([-1.0, 1.0])
            zombie.wall_follow_last_wall_time = pygame.time.get_ticks()
            zombie.wall_follow_last_side_has_wall = left_wall or right_wall
        else:
            if is_in_sight:
                return zombie_move_toward(zombie, player_center)
            return zombie_wander_move(zombie, walls)

    sensor_distance = ZOMBIE_WALL_FOLLOW_SENSOR_DISTANCE + zombie.radius
    side_angle = zombie.wall_follow_angle + zombie.wall_follow_side * (math.pi / 2.0)
    side_has_wall = zombie_wall_follow_has_wall(
        zombie, walls, side_angle, sensor_distance
    )
    forward_has_wall = zombie_wall_follow_has_wall(
        zombie, walls, zombie.wall_follow_angle, sensor_distance
    )
    now = pygame.time.get_ticks()
    wall_recent = (
        zombie.wall_follow_last_wall_time is not None
        and now - zombie.wall_follow_last_wall_time <= ZOMBIE_WALL_FOLLOW_LOST_WALL_MS
    )
    if is_in_sight:
        return zombie_move_toward(zombie, player_center)

    turn_step = math.radians(5)
    if side_has_wall or forward_has_wall:
        zombie.wall_follow_last_wall_time = now
    if side_has_wall:
        zombie.wall_follow_last_side_has_wall = True
        if forward_has_wall:
            zombie.wall_follow_angle -= zombie.wall_follow_side * turn_step
    else:
        if wall_recent:
            if zombie.wall_follow_last_side_has_wall and not forward_has_wall:
                zombie.wall_follow_angle += zombie.wall_follow_side * (math.pi / 2.0)
                zombie.wall_follow_last_side_has_wall = False
            elif zombie.wall_follow_last_side_has_wall:
                zombie.wall_follow_angle += zombie.wall_follow_side * turn_step
                zombie.wall_follow_last_side_has_wall = False
        else:
            zombie.wall_follow_angle += zombie.wall_follow_side * (math.pi / 2.0)
            zombie.wall_follow_side = 0.0
    zombie.wall_follow_angle %= math.tau

    move_x = math.cos(zombie.wall_follow_angle) * zombie.speed
    move_y = math.sin(zombie.wall_follow_angle) * zombie.speed
    return move_x, move_y


def zombie_normal_movement(
    zombie: Zombie,
    player_center: tuple[int, int],
    walls: list[Wall],
    _footprints: list[dict[str, object]],
) -> tuple[float, float]:
    is_in_sight = zombie._update_mode(player_center, ZOMBIE_SIGHT_RANGE)
    if not is_in_sight:
        return zombie_wander_move(zombie, walls)
    return zombie_move_toward(zombie, player_center)


def zombie_update_tracker_target(
    zombie: Zombie, footprints: list[dict[str, object]]
) -> None:
    zombie.tracker_target_pos = None
    if not footprints:
        return
    nearby: list[dict[str, object]] = []
    for fp in footprints:
        pos = fp.get("pos")
        if not isinstance(pos, tuple):
            continue
        dx = pos[0] - zombie.x
        dy = pos[1] - zombie.y
        if math.hypot(dx, dy) <= ZOMBIE_TRACKER_SCENT_RADIUS:
            nearby.append(fp)

    if not nearby:
        return

    latest = max(
        nearby,
        key=lambda fp: fp.get("time", -1)
        if isinstance(fp.get("time"), int)
        else -1,
    )
    pos = latest.get("pos")
    if isinstance(pos, tuple):
        zombie.tracker_target_pos = pos


def zombie_wander_move(zombie: Zombie, walls: list[Wall]) -> tuple[float, float]:
    now = pygame.time.get_ticks()
    if now - zombie.last_wander_change_time > zombie.wander_change_interval:
        zombie.wander_angle = RNG.uniform(0, math.tau)
        zombie.last_wander_change_time = now
        jitter = RNG.randint(-500, 500)
        zombie.wander_change_interval = max(0, zombie.wander_interval_ms + jitter)

    cell_x = int(zombie.x // CELL_SIZE)
    cell_y = int(zombie.y // CELL_SIZE)
    at_x_edge = cell_x in (0, GRID_COLS - 1)
    at_y_edge = cell_y in (0, GRID_ROWS - 1)

    if at_x_edge or at_y_edge:
        if zombie.outer_wall_cells is not None:
            if at_x_edge:
                inward_cell = (1, cell_y) if cell_x == 0 else (GRID_COLS - 2, cell_y)
                if inward_cell not in zombie.outer_wall_cells:
                    inward_dx = zombie.speed if cell_x == 0 else -zombie.speed
                    return inward_dx, 0.0
            if at_y_edge:
                inward_cell = (cell_x, 1) if cell_y == 0 else (cell_x, GRID_ROWS - 2)
                if inward_cell not in zombie.outer_wall_cells:
                    inward_dy = zombie.speed if cell_y == 0 else -zombie.speed
                    return 0.0, inward_dy
        else:
            def path_clear(next_x: float, next_y: float) -> bool:
                nearby_walls = [
                    wall
                    for wall in walls
                    if abs(wall.rect.centerx - next_x) < 120
                    and abs(wall.rect.centery - next_y) < 120
                ]
                return not any(
                    circle_wall_collision((next_x, next_y), zombie.radius, wall)
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
        if at_x_edge:
            direction = 1.0 if math.sin(zombie.wander_angle) >= 0 else -1.0
            return 0.0, direction * zombie.speed
        if at_y_edge:
            direction = 1.0 if math.cos(zombie.wander_angle) >= 0 else -1.0
            return direction * zombie.speed, 0.0

    move_x = math.cos(zombie.wander_angle) * zombie.speed
    move_y = math.sin(zombie.wander_angle) * zombie.speed
    return move_x, move_y


def zombie_move_toward(
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
        *,
        start_pos: tuple[int, int] | None = None,
        hint_pos: tuple[float, float] | None = None,
        speed: float = ZOMBIE_SPEED,
        tracker: bool = False,
        wall_follower: bool = False,
        movement_strategy: MovementStrategy | None = None,
        aging_duration_frames: float = ZOMBIE_AGING_DURATION_FRAMES,
        outer_wall_cells: set[tuple[int, int]] | None = None,
    ) -> None:
        super().__init__()
        self.radius = ZOMBIE_RADIUS
        self.image = pygame.Surface((self.radius * 2, self.radius * 2), pygame.SRCALPHA)
        pygame.draw.circle(self.image, RED, (self.radius, self.radius), self.radius)
        if start_pos:
            x, y = start_pos
        elif hint_pos:
            points = [random_position_outside_building() for _ in range(5)]
            points.sort(
                key=lambda p: math.hypot(p[0] - hint_pos[0], p[1] - hint_pos[1])
            )
            x, y = points[0]
        else:
            x, y = random_position_outside_building()
        self.rect = self.image.get_rect(center=(x, y))
        jitter_base = FAST_ZOMBIE_BASE_SPEED if speed > ZOMBIE_SPEED else ZOMBIE_SPEED
        jitter = jitter_base * 0.2
        base_speed = speed + RNG.uniform(-jitter, jitter)
        self.initial_speed = base_speed
        self.speed = base_speed
        self.x = float(self.rect.centerx)
        self.y = float(self.rect.centery)
        self.was_in_sight = False
        self.carbonized = False
        self.age_frames = 0.0
        self.aging_duration_frames = aging_duration_frames
        self.tracker = tracker
        self.wall_follower = wall_follower
        if movement_strategy is None:
            if tracker:
                movement_strategy = zombie_tracker_movement
            elif wall_follower:
                movement_strategy = zombie_wall_follow_movement
            else:
                movement_strategy = zombie_normal_movement
        self.movement_strategy = movement_strategy
        self.outer_wall_cells = outer_wall_cells
        self.tracker_target_pos: tuple[float, float] | None = None
        self.wall_follow_side = RNG.choice([-1.0, 1.0]) if wall_follower else 0.0
        self.wall_follow_angle = (
            RNG.uniform(0, math.tau) if wall_follower else None
        )
        self.wall_follow_last_wall_time: int | None = None
        self.wall_follow_last_side_has_wall = False
        self.wander_angle = RNG.uniform(0, math.tau)
        self.wander_interval_ms = (
            ZOMBIE_TRACKER_WANDER_INTERVAL_MS if tracker else ZOMBIE_WANDER_INTERVAL_MS
        )
        self.last_wander_change_time = pygame.time.get_ticks()
        self.wander_change_interval = max(
            0, self.wander_interval_ms + RNG.randint(-500, 500)
        )

    def _update_mode(
        self: Self, player_center: tuple[int, int], sight_range: float
    ) -> bool:
        dx_target = player_center[0] - self.x
        dy_target = player_center[1] - self.y
        dist_to_player = math.hypot(dx_target, dy_target)
        is_in_sight = dist_to_player <= sight_range
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
            collides = circle_wall_collision((next_x, self.y), self.radius, wall)
            if collides:
                if wall.alive():
                    wall.take_damage(amount=ZOMBIE_WALL_DAMAGE)
                if wall.alive():
                    final_x = self.x
                    break

        for wall in possible_walls:
            collides = circle_wall_collision((final_x, next_y), self.radius, wall)
            if collides:
                if wall.alive():
                    wall.take_damage(amount=ZOMBIE_WALL_DAMAGE)
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
        closest_dist = ZOMBIE_SEPARATION_DISTANCE
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
            dist = math.hypot(dx, dy)
            if dist < closest_dist:
                closest = other
                closest_dist = dist

        if closest is None:
            return move_x, move_y

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

    def update(
        self: Self,
        player_center: tuple[int, int],
        walls: list[Wall],
        nearby_zombies: Iterable[Zombie],
        footprints: list[dict[str, object]] | None = None,
    ) -> None:
        if self.carbonized:
            return
        self._apply_aging()
        dx_player = player_center[0] - self.x
        dy_player = player_center[1] - self.y
        dist_to_player = math.hypot(dx_player, dy_player)
        avoid_radius = max(SCREEN_WIDTH, SCREEN_HEIGHT) * 2
        move_x, move_y = self.movement_strategy(
            self, player_center, walls, footprints or []
        )
        if dist_to_player <= avoid_radius:
            move_x, move_y = self._avoid_other_zombies(move_x, move_y, nearby_zombies)
        final_x, final_y = self._handle_wall_collision(
            self.x + move_x, self.y + move_y, walls
        )

        if not (0 <= final_x < LEVEL_WIDTH and 0 <= final_y < LEVEL_HEIGHT):
            final_x, final_y = random_position_outside_building()

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
    COLOR_SCHEMES: dict[str, dict[str, tuple[int, int, int]]] = {
        "default": {
            "healthy": YELLOW,
            "damaged": ORANGE,
            "critical": DARK_RED,
        },
        "disabled": {
            "healthy": (185, 185, 185),
            "damaged": (150, 150, 150),
            "critical": (110, 110, 110),
        },
    }

    def __init__(self: Self, x: int, y: int, *, appearance: str = "default") -> None:
        super().__init__()
        self.original_image = pygame.Surface((CAR_WIDTH, CAR_HEIGHT), pygame.SRCALPHA)
        self.appearance = appearance if appearance in self.COLOR_SCHEMES else "default"
        self.base_color = self.COLOR_SCHEMES[self.appearance]["healthy"]
        self.image = self.original_image.copy()
        self.rect = self.image.get_rect(center=(x, y))
        self.speed = CAR_SPEED
        self.angle = 0
        self.x = float(self.rect.centerx)
        self.y = float(self.rect.centery)
        self.health = CAR_HEALTH
        self.max_health = CAR_HEALTH
        self.collision_radius = car_body_radius(CAR_WIDTH, CAR_HEIGHT)
        self.update_color()

    def take_damage(self: Self, amount: int) -> None:
        if self.health > 0:
            self.health -= amount
            self.update_color()

    def update_color(self: Self) -> None:
        health_ratio = max(0, self.health / self.max_health)
        palette = self.COLOR_SCHEMES.get(self.appearance, self.COLOR_SCHEMES["default"])
        color = palette["healthy"]
        if health_ratio < 0.6:
            color = palette["damaged"]
        if health_ratio < 0.3:
            color = palette["critical"]
        self.original_image.fill((0, 0, 0, 0))

        body_rect = pygame.Rect(1, 4, CAR_WIDTH - 2, CAR_HEIGHT - 8)
        front_cap_height = max(8, body_rect.height // 3)
        front_cap = pygame.Rect(
            body_rect.left, body_rect.top, body_rect.width, front_cap_height
        )
        windshield_rect = pygame.Rect(
            body_rect.left + 4,
            body_rect.top + 3,
            body_rect.width - 8,
            front_cap_height - 5,
        )

        trim_color = tuple(int(c * 0.55) for c in color)
        front_cap_color = tuple(min(255, int(c * 1.08)) for c in color)
        body_color = color
        window_color = (70, 110, 150)
        wheel_color = (35, 35, 35)

        wheel_width = CAR_WIDTH // 3
        wheel_height = 6
        for y in (body_rect.top + 4, body_rect.bottom - wheel_height - 4):
            left_wheel = pygame.Rect(2, y, wheel_width, wheel_height)
            right_wheel = pygame.Rect(
                CAR_WIDTH - wheel_width - 2, y, wheel_width, wheel_height
            )
            pygame.draw.rect(
                self.original_image, wheel_color, left_wheel, border_radius=3
            )
            pygame.draw.rect(
                self.original_image, wheel_color, right_wheel, border_radius=3
            )

        pygame.draw.rect(self.original_image, body_color, body_rect, border_radius=4)
        pygame.draw.rect(
            self.original_image, trim_color, body_rect, width=2, border_radius=4
        )
        pygame.draw.rect(
            self.original_image, front_cap_color, front_cap, border_radius=10
        )
        pygame.draw.rect(
            self.original_image, trim_color, front_cap, width=2, border_radius=10
        )
        pygame.draw.rect(
            self.original_image, window_color, windshield_rect, border_radius=4
        )

        headlight_color = (245, 245, 200)
        for x in (front_cap.left + 5, front_cap.right - 5):
            pygame.draw.circle(
                self.original_image, headlight_color, (x, body_rect.top + 5), 2
            )
        grille_rect = pygame.Rect(front_cap.centerx - 6, front_cap.top + 2, 12, 6)
        pygame.draw.rect(self.original_image, trim_color, grille_rect, border_radius=2)
        tail_light_color = (255, 80, 50)
        for x in (body_rect.left + 5, body_rect.right - 5):
            pygame.draw.rect(
                self.original_image,
                tail_light_color,
                (x - 2, body_rect.bottom - 5, 4, 3),
                border_radius=1,
            )
        self.image = pygame.transform.rotate(self.original_image, self.angle)
        old_center = self.rect.center
        self.rect = self.image.get_rect(center=old_center)

    def move(self: Self, dx: float, dy: float, walls: Iterable[Wall]) -> None:
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
        possible_walls = [
            w
            for w in walls
            if abs(w.rect.centery - self.y) < 100 and abs(w.rect.centerx - new_x) < 100
        ]
        car_center = (new_x, new_y)
        for wall in possible_walls:
            if circle_wall_collision(car_center, self.collision_radius, wall):
                hit_walls.append(wall)
        if hit_walls:
            self.take_damage(CAR_WALL_DAMAGE)
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
        self.image = pygame.Surface((FUEL_CAN_WIDTH, FUEL_CAN_HEIGHT), pygame.SRCALPHA)

        # Jerrycan silhouette with cut corner
        w, h = FUEL_CAN_WIDTH, FUEL_CAN_HEIGHT
        body_pts = [
            (1, 4),
            (w - 2, 4),
            (w - 2, h - 2),
            (1, h - 2),
            (1, 8),
            (4, 4),
        ]
        pygame.draw.polygon(self.image, YELLOW, body_pts)
        pygame.draw.polygon(self.image, BLACK, body_pts, width=2)

        cap_size = max(2, w // 4)
        cap_rect = pygame.Rect(w - cap_size - 2, 1, cap_size, 3)
        pygame.draw.rect(self.image, YELLOW, cap_rect, border_radius=1)
        pygame.draw.rect(self.image, BLACK, cap_rect, width=1, border_radius=1)

        # Cross brace accent
        brace_color = (240, 200, 40)
        pygame.draw.line(self.image, brace_color, (3, h // 2), (w - 4, h // 2), width=2)
        pygame.draw.line(self.image, BLACK, (3, h // 2), (w - 4, h // 2), width=1)

        self.rect = self.image.get_rect(center=(x, y))


class Flashlight(pygame.sprite.Sprite):
    """Flashlight pickup that expands the player's visible radius when collected."""

    def __init__(self: Self, x: int, y: int) -> None:
        super().__init__()
        self.image = pygame.Surface(
            (FLASHLIGHT_WIDTH, FLASHLIGHT_HEIGHT), pygame.SRCALPHA
        )

        body_color = (230, 200, 70)
        trim_color = (80, 70, 40)
        head_color = (200, 180, 90)
        beam_color = (255, 240, 180, 150)

        body_rect = pygame.Rect(1, 2, FLASHLIGHT_WIDTH - 4, FLASHLIGHT_HEIGHT - 4)
        head_rect = pygame.Rect(
            body_rect.right - 3, body_rect.top - 1, 4, body_rect.height + 2
        )
        beam_points = [
            (head_rect.right + 4, head_rect.centery),
            (head_rect.right + 2, head_rect.top),
            (head_rect.right + 2, head_rect.bottom),
        ]

        pygame.draw.rect(self.image, body_color, body_rect, border_radius=2)
        pygame.draw.rect(self.image, trim_color, body_rect, width=1, border_radius=2)
        pygame.draw.rect(self.image, head_color, head_rect, border_radius=2)
        pygame.draw.rect(self.image, trim_color, head_rect, width=1, border_radius=2)
        pygame.draw.polygon(self.image, beam_color, beam_points)

        self.rect = self.image.get_rect(center=(x, y))


__all__ = [
    "Wall",
    "SteelBeam",
    "Camera",
    "Player",
    "Companion",
    "Survivor",
    "Zombie",
    "Car",
    "FuelCan",
    "Flashlight",
    "random_position_outside_building",
]
