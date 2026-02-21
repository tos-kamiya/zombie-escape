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

from zombie_escape.colors import get_environment_palette


def encode_stage_barcode(stage_number: int) -> str:
    value = max(0, int(stage_number))
    bits = bin(value)[2:]
    one_count = bits.count("1")
    parity_bit = "0" if (one_count % 2 == 0) else "1"

    start = "**_"
    end = "_**"
    encoded_bits = "".join("_*" if bit == "0" else "*_" for bit in bits)
    encoded_parity = "_*" if parity_bit == "0" else "*_"
    return start + encoded_bits + encoded_parity + end


def _draw_floor_panel(
    surface: pygame.Surface,
    *,
    panel_rect: pygame.Rect,
    cell_size: int,
    primary: tuple[int, int, int],
    secondary: tuple[int, int, int],
) -> None:
    cols = max(1, panel_rect.width // cell_size)
    rows = max(1, panel_rect.height // cell_size)
    for y in range(rows):
        for x in range(cols):
            color = secondary if ((x // 2) + (y // 2)) % 2 == 0 else primary
            tile_rect = pygame.Rect(
                panel_rect.left + x * cell_size,
                panel_rect.top + y * cell_size,
                cell_size,
                cell_size,
            )
            pygame.draw.rect(surface, color, tile_rect)


def _draw_barcode_overlay(
    surface: pygame.Surface,
    *,
    panel_rect: pygame.Rect,
    pattern: str,
    module_width: int,
    alpha: int,
) -> None:
    barcode_width = len(pattern) * module_width
    barcode_height = max(3, int(panel_rect.height * 0.18))
    x0 = panel_rect.right - barcode_width - 1
    y0 = panel_rect.bottom - barcode_height - 1

    overlay = pygame.Surface((barcode_width, barcode_height), pygame.SRCALPHA)
    bar_color = (10, 10, 10, max(0, min(255, alpha)))
    for i, symbol in enumerate(pattern):
        if symbol != "*":
            continue
        x = i * module_width
        pygame.draw.rect(
            overlay,
            bar_color,
            pygame.Rect(x, 0, module_width, barcode_height),
        )
    surface.blit(overlay, (x0, y0))


def build_preview_surface(
    *,
    stage_number: int,
    cell_size: int,
    module_width: int,
    alpha: int,
) -> pygame.Surface:
    palette = get_environment_palette(None)
    panel_w = cell_size * 8
    panel_h = cell_size * 8
    gap = 12
    margin = 12
    title_h = 24
    out_w = margin * 2 + panel_w * 2 + gap
    out_h = margin * 2 + title_h + panel_h

    out = pygame.Surface((out_w, out_h), pygame.SRCALPHA)
    out.fill((24, 24, 24, 255))

    normal_rect = pygame.Rect(margin, margin + title_h, panel_w, panel_h)
    fall_rect = pygame.Rect(normal_rect.right + gap, margin + title_h, panel_w, panel_h)

    _draw_floor_panel(
        out,
        panel_rect=normal_rect,
        cell_size=cell_size,
        primary=palette.floor_primary,
        secondary=palette.floor_secondary,
    )
    _draw_floor_panel(
        out,
        panel_rect=fall_rect,
        cell_size=cell_size,
        primary=palette.fall_zone_primary,
        secondary=palette.fall_zone_secondary,
    )

    pattern = encode_stage_barcode(stage_number)
    _draw_barcode_overlay(
        out,
        panel_rect=normal_rect,
        pattern=pattern,
        module_width=module_width,
        alpha=alpha,
    )
    _draw_barcode_overlay(
        out,
        panel_rect=fall_rect,
        pattern=pattern,
        module_width=module_width,
        alpha=alpha,
    )

    pygame.font.init()
    font = pygame.font.Font(None, 24)
    label_color = (225, 225, 225)
    out.blit(font.render("Normal Floor", True, label_color), (normal_rect.left, margin))
    out.blit(font.render("Fall Spawn Floor", True, label_color), (fall_rect.left, margin))

    info_font = pygame.font.Font(None, 20)
    info = f"Stage {stage_number}  pattern: {pattern}"
    out.blit(info_font.render(info, True, (190, 190, 190)), (margin, out_h - 18))
    return out


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Export floor tile preview with simple 1D stage barcode overlay."
    )
    parser.add_argument(
        "--stage",
        type=int,
        default=1,
        help="Stage number to encode.",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=Path("imgs/exports/floor-barcode-preview.png"),
        help="Output image path.",
    )
    parser.add_argument(
        "--cell-size",
        type=int,
        default=20,
        help="Tile cell size.",
    )
    parser.add_argument(
        "--module-width",
        type=int,
        default=1,
        help="Barcode module width in pixels.",
    )
    parser.add_argument(
        "--alpha",
        type=int,
        default=44,
        help="Barcode alpha (0-255).",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if not pygame.get_init():
        pygame.init()
    if not pygame.display.get_init():
        pygame.display.init()
    if pygame.display.get_surface() is None:
        flags = pygame.HIDDEN if hasattr(pygame, "HIDDEN") else 0
        pygame.display.set_mode((1, 1), flags=flags)
    try:
        surface = build_preview_surface(
            stage_number=max(0, args.stage),
            cell_size=max(8, args.cell_size),
            module_width=max(1, args.module_width),
            alpha=max(0, min(255, args.alpha)),
        )
        args.out.parent.mkdir(parents=True, exist_ok=True)
        pygame.image.save(surface, args.out.as_posix())
        print(f"Saved floor barcode preview: {args.out}")
        return 0
    finally:
        pygame.font.quit()


if __name__ == "__main__":
    raise SystemExit(main())
