# ruff: noqa: E402

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pygame

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from zombie_escape.export_images import (
    _ensure_pygame_ready,
    _render_studio_snapshot,
    _studio_grid_size,
)
from zombie_escape.screen_constants import SCREEN_HEIGHT, SCREEN_WIDTH


def _center_target_rect(*, cell_size: int, cols: int, rows: int) -> pygame.Rect:
    studio_cols, studio_rows = _studio_grid_size(cell_size)
    center_cell_x = studio_cols // 2
    center_cell_y = studio_rows // 2
    left = (center_cell_x - cols // 2) * cell_size
    top = (center_cell_y - rows // 2) * cell_size
    return pygame.Rect(left, top, cols * cell_size, rows * cell_size)


def _build_fall_spawn_cells_for_rect(target_rect: pygame.Rect, *, cell_size: int) -> set[tuple[int, int]]:
    x0 = target_rect.left // cell_size
    y0 = target_rect.top // cell_size
    x1 = target_rect.right // cell_size
    y1 = target_rect.bottom // cell_size

    cells: set[tuple[int, int]] = set()
    for y in range(y0, y1):
        for x in range(x0, x1):
            local_x = x - x0
            local_y = y - y0
            # Sparse diagonal + staggered clusters so floor decoration difference is visible.
            if (local_x + local_y) % 5 == 0:
                cells.add((x, y))
            elif local_x % 7 == 0 and (local_y % 3) == 1:
                cells.add((x, y))
    return cells


def build_preview_surface(*, cell_size: int) -> pygame.Surface:
    cols = max(8, int((SCREEN_WIDTH * 0.55) // cell_size))
    rows = max(6, int((SCREEN_HEIGHT * 0.55) // cell_size))
    target_rect = _center_target_rect(cell_size=cell_size, cols=cols, rows=rows)

    normal = _render_studio_snapshot(
        cell_size=cell_size,
        target_rect=target_rect,
        fall_spawn_cells=set(),
        ambient_palette_key=None,
        wall_rubble_ratio=0.5,
    )
    with_fall_spawn = _render_studio_snapshot(
        cell_size=cell_size,
        target_rect=target_rect,
        fall_spawn_cells=_build_fall_spawn_cells_for_rect(target_rect, cell_size=cell_size),
        ambient_palette_key=None,
        wall_rubble_ratio=0.5,
    )
    # _render_studio_snapshot returns a padded framing area; crop to center floor area.
    crop_w = max(8, int(round(normal.get_width() / 1.3)))
    crop_h = max(8, int(round(normal.get_height() / 1.3)))
    crop_rect = pygame.Rect(0, 0, crop_w, crop_h)
    crop_rect.center = normal.get_rect().center
    normal = normal.subsurface(crop_rect).copy()
    with_fall_spawn = with_fall_spawn.subsurface(crop_rect).copy()

    pygame.font.init()
    font = pygame.font.Font(None, 24)
    label_color = (220, 220, 220)
    bg = (24, 24, 24, 255)
    panel = (38, 38, 38, 255)

    margin = 12
    gap = 10
    label_h = 22
    width = margin * 2 + normal.get_width() * 2 + gap
    height = margin * 2 + label_h + normal.get_height()
    out = pygame.Surface((width, height), pygame.SRCALPHA)
    out.fill(bg)

    left_x = margin
    right_x = margin + normal.get_width() + gap
    image_y = margin + label_h

    pygame.draw.rect(
        out,
        panel,
        pygame.Rect(left_x - 1, image_y - 1, normal.get_width() + 2, normal.get_height() + 2),
        width=1,
    )
    pygame.draw.rect(
        out,
        panel,
        pygame.Rect(right_x - 1, image_y - 1, with_fall_spawn.get_width() + 2, with_fall_spawn.get_height() + 2),
        width=1,
    )

    out.blit(normal, (left_x, image_y))
    out.blit(with_fall_spawn, (right_x, image_y))

    out.blit(font.render("Normal Floor", True, label_color), (left_x, margin))
    out.blit(font.render("Fall Spawn + Floor", True, label_color), (right_x, margin))
    return out


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Export floor ruin dressing preview image."
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=Path("imgs/exports/floor-ruin-preview.png"),
        help="Output image path.",
    )
    parser.add_argument(
        "--cell-size",
        type=int,
        default=20,
        help="Cell size for preview rendering.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    _ensure_pygame_ready()
    try:
        surface = build_preview_surface(cell_size=max(8, args.cell_size))
        args.out.parent.mkdir(parents=True, exist_ok=True)
        pygame.image.save(surface, args.out.as_posix())
        print(f"Saved floor ruin preview: {args.out}")
        return 0
    finally:
        pygame.font.quit()


if __name__ == "__main__":
    raise SystemExit(main())
