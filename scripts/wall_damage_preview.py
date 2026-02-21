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

from zombie_escape.entities.walls import RubbleWall, SteelBeam, Wall

PREVIEW_DAMAGE_SEED = 1337


def _build_row(
    label: str,
    wall_factory,
    *,
    steps: int,
    tile_size: int,
    font: pygame.font.Font,
    label_width: int,
    padding: int,
) -> pygame.Surface:
    cell_width = tile_size + padding * 2
    row_width = label_width + (cell_width * steps) + padding
    row_height = tile_size + padding * 2
    row = pygame.Surface((row_width, row_height), pygame.SRCALPHA)
    row.fill((35, 35, 35, 255))

    text = font.render(label, True, (220, 220, 220))
    row.blit(text, (padding, max(padding, (row_height - text.get_height()) // 2)))

    base_health = 100
    for idx in range(steps):
        damage_ratio = idx / max(1, steps - 1)
        health_ratio = 1.0 - (damage_ratio * 0.9)
        health = max(1, int(round(base_health * health_ratio)))
        wall = wall_factory(health=base_health)
        wall.health = health
        wall._update_color()

        col_x = label_width + (idx * cell_width) + padding
        cell_rect = pygame.Rect(col_x, padding, tile_size, tile_size)
        pygame.draw.rect(row, (60, 60, 60), cell_rect)
        scaled = pygame.transform.smoothscale(wall.image, (tile_size, tile_size))
        row.blit(scaled, cell_rect.topleft)

        step_text = font.render(f"{idx}", True, (225, 225, 225))
        step_rect = step_text.get_rect(
            bottomright=(cell_rect.right - 3, cell_rect.bottom - 2)
        )
        row.blit(step_text, step_rect.topleft)
    return row


def build_preview_surface(*, steps: int = 12, wall_size: int = 56) -> pygame.Surface:
    pygame.font.init()
    font = pygame.font.Font(None, 18)
    label_width = 88
    padding = 8

    rows = [
        _build_row(
            "Wall",
            lambda health: Wall(
                0, 0, 48, 48, health=health, damage_overlay_seed=PREVIEW_DAMAGE_SEED
            ),
            steps=steps,
            tile_size=wall_size,
            font=font,
            label_width=label_width,
            padding=padding,
        ),
        _build_row(
            "Rubble",
            lambda health: RubbleWall(
                0, 0, 48, 48, health=health, damage_overlay_seed=PREVIEW_DAMAGE_SEED
            ),
            steps=steps,
            tile_size=wall_size,
            font=font,
            label_width=label_width,
            padding=padding,
        ),
        _build_row(
            "Steel Beam",
            lambda health: SteelBeam(
                0, 0, 48, health=health, damage_overlay_seed=PREVIEW_DAMAGE_SEED
            ),
            steps=steps,
            tile_size=wall_size,
            font=font,
            label_width=label_width,
            padding=padding,
        ),
    ]

    gap = 8
    width = max(row.get_width() for row in rows)
    height = sum(row.get_height() for row in rows) + gap * (len(rows) - 1)
    preview = pygame.Surface((width, height), pygame.SRCALPHA)
    preview.fill((22, 22, 22, 255))

    y = 0
    for row in rows:
        preview.blit(row, (0, y))
        y += row.get_height() + gap
    return preview


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Export a 12-step wall damage visual preview."
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=Path("imgs/exports/wall-damage-preview.png"),
        help="Output image path.",
    )
    parser.add_argument(
        "--steps",
        type=int,
        default=12,
        help="Damage step count (default: 12).",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    pygame.font.init()
    try:
        surface = build_preview_surface(steps=max(2, args.steps))
        args.out.parent.mkdir(parents=True, exist_ok=True)
        pygame.image.save(surface, args.out.as_posix())
        print(f"Saved wall damage preview: {args.out}")
        return 0
    finally:
        pygame.font.quit()


if __name__ == "__main__":
    raise SystemExit(main())
