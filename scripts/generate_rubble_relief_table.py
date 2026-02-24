#!/usr/bin/env python3
"""Generate rubble relief lookup tables for render-time use."""

from __future__ import annotations

import random
from pathlib import Path

_RUBBLE_ROTATION_SCALES: tuple[float, ...] = (
    -1.20,
    -0.80,
    -0.45,
    -0.15,
    0.15,
    0.45,
    0.80,
    1.10,
    1.35,
)

_RUBBLE_RELIEF_VARIANTS: tuple[tuple[tuple[float, float], ...], ...] = (
    (
        (-0.20, -0.05),
        (0.10, -0.20),
        (0.05, -0.15),
        (0.18, 0.00),
        (0.12, 0.12),
        (-0.08, 0.20),
        (-0.15, 0.10),
        (-0.18, -0.12),
    ),
    (
        (-0.10, -0.20),
        (0.20, -0.08),
        (0.18, -0.10),
        (0.05, 0.15),
        (-0.05, 0.20),
        (-0.20, 0.10),
        (-0.10, 0.05),
        (-0.02, -0.18),
    ),
    (
        (0.05, -0.18),
        (0.18, -0.02),
        (0.20, 0.05),
        (0.10, 0.20),
        (-0.12, 0.18),
        (-0.22, 0.00),
        (-0.15, -0.08),
        (-0.04, -0.20),
    ),
    (
        (-0.18, -0.02),
        (0.00, -0.22),
        (0.12, -0.05),
        (0.20, 0.08),
        (0.18, 0.15),
        (0.05, 0.22),
        (-0.10, 0.10),
        (-0.20, 0.00),
    ),
    (
        (-0.12, -0.12),
        (0.12, -0.12),
        (0.15, 0.00),
        (0.12, 0.12),
        (0.00, 0.15),
        (-0.12, 0.12),
        (-0.15, 0.00),
        (-0.12, -0.12),
    ),
    (
        (0.00, -0.22),
        (0.22, -0.02),
        (0.12, 0.10),
        (0.00, 0.22),
        (-0.12, 0.10),
        (-0.22, -0.02),
        (-0.12, -0.10),
        (0.00, -0.12),
    ),
    (
        (-0.22, 0.00),
        (-0.05, -0.18),
        (0.10, -0.20),
        (0.22, -0.05),
        (0.20, 0.10),
        (0.05, 0.18),
        (-0.10, 0.20),
        (-0.20, 0.10),
    ),
    (
        (-0.05, -0.20),
        (0.15, -0.15),
        (0.22, 0.00),
        (0.15, 0.15),
        (-0.05, 0.20),
        (-0.18, 0.12),
        (-0.22, -0.02),
        (-0.15, -0.15),
    ),
    (
        (-0.15, -0.15),
        (0.05, -0.22),
        (0.20, -0.05),
        (0.18, 0.12),
        (0.05, 0.22),
        (-0.15, 0.15),
        (-0.20, 0.00),
        (-0.18, -0.10),
    ),
)


def _build_normalized_variant_points(
    variant: int, *, shape_scale: float = 0.95
) -> tuple[tuple[float, float], ...]:
    # Canonical geometry: half_w=half_h=1, protrude=jitter=0.1
    half_w = 1.0
    half_h = 1.0
    protrude = 0.1
    jitter = 0.1
    left = -half_w
    right = half_w
    top = -half_h
    bottom = half_h
    side_step = (bottom - top) / 3.0
    top_step = (right - left) / 4.0
    points = [
        (left, top),
        (left + top_step, top - protrude),
        (left + (top_step * 3.0), top - protrude),
        (right, top),
        (right + protrude, top + side_step),
        (right + protrude, top + (side_step * 2.0)),
        (right, bottom),
        (left + (top_step * 3.0), bottom + protrude),
        (left + top_step, bottom + protrude),
        (left, bottom),
        (left - protrude, top + (side_step * 2.0)),
        (left - protrude, top + side_step),
    ]
    normals = [
        (-1.0, -1.0),
        (0.0, -1.0),
        (0.0, -1.0),
        (1.0, -1.0),
        (1.0, 0.0),
        (1.0, 0.0),
        (1.0, 1.0),
        (0.0, 1.0),
        (0.0, 1.0),
        (-1.0, 1.0),
        (-1.0, 0.0),
        (-1.0, 0.0),
    ]

    pattern = _RUBBLE_RELIEF_VARIANTS[variant]
    variant_row = variant // 3
    variant_col = variant % 3
    out_scale = 1.00 + (variant_col * 0.22)
    in_scale = 0.78 + (variant_row * 0.18)
    tangent_scale = 0.28 + (variant_col * 0.06) + (variant_row * 0.04)
    direction_sequence = [-1.0] * 6 + [1.0] * 6
    random.Random(72_001 + variant).shuffle(direction_sequence)

    output: list[tuple[float, float]] = []
    for i in range(12):
        pat = pattern[(i + variant) % len(pattern)]
        px, py = points[i]
        nx, ny = normals[i]
        normal_len = (nx * nx + ny * ny) ** 0.5
        if normal_len > 0:
            nx /= normal_len
            ny /= normal_len
        tx, ty = -ny, nx
        direction = direction_sequence[i]
        wave_mul = 0.2
        base_amp = protrude + (jitter * (0.42 + abs(pat[0]) * 0.38))
        amp_scale = out_scale if direction > 0 else in_scale
        radial = direction * base_amp * amp_scale * wave_mul
        tangent = pat[1] * jitter * tangent_scale
        out_x = (px + (nx * radial) + (tx * tangent)) * shape_scale
        out_y = (py + (ny * radial) + (ty * tangent)) * shape_scale
        output.append((out_x, out_y))
    return tuple(output)


def _build_edge_widths(variant: int) -> tuple[int, ...]:
    rng = random.Random(91_000 + variant)
    return tuple(1 + int(rng.random() < 0.45) for _ in range(12))


def _render_module_text(
    *,
    point_table: tuple[tuple[tuple[float, float], ...], ...],
    edge_width_table: tuple[tuple[int, ...], ...],
) -> str:
    lines: list[str] = []
    lines.append("from __future__ import annotations")
    lines.append("")
    lines.append('"""Generated rubble relief lookup tables. Do not edit by hand."""')
    lines.append("")
    lines.append("RUBBLE_ROTATION_SCALES: tuple[float, ...] = (")
    for value in _RUBBLE_ROTATION_SCALES:
        lines.append(f"    {value:.2f},")
    lines.append(")")
    lines.append("")
    lines.append(
        "RUBBLE_RELIEF_POINT_TABLE: tuple[tuple[tuple[float, float], ...], ...] = ("
    )
    for variant_points in point_table:
        lines.append("    (")
        for x, y in variant_points:
            lines.append(f"        ({x:.6f}, {y:.6f}),")
        lines.append("    ),")
    lines.append(")")
    lines.append("")
    lines.append("RUBBLE_RELIEF_EDGE_WIDTH_TABLE: tuple[tuple[int, ...], ...] = (")
    for widths in edge_width_table:
        width_text = ", ".join(str(v) for v in widths)
        lines.append(f"    ({width_text}),")
    lines.append(")")
    lines.append("")
    return "\n".join(lines)


def main() -> int:
    point_table = tuple(_build_normalized_variant_points(v) for v in range(9))
    edge_width_table = tuple(_build_edge_widths(v) for v in range(9))
    output = _render_module_text(
        point_table=point_table,
        edge_width_table=edge_width_table,
    )
    out_path = (
        Path(__file__).resolve().parents[1]
        / "src"
        / "zombie_escape"
        / "render_assets"
        / "rubble_relief_table.py"
    )
    out_path.write_text(output, encoding="utf-8")
    print(f"Wrote {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
