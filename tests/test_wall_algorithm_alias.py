from __future__ import annotations

import zombie_escape.level_blueprints as level_blueprints
from zombie_escape.level_blueprints import generate_random_blueprint
from zombie_escape.level_constants import DEFAULT_WALL_LINES


def test_wall_algorithm_normal_percent_uses_default_line_density(
    monkeypatch,
) -> None:
    captured: dict[str, int] = {}

    def fake_default(
        grid: list[list[str]],
        *,
        line_count: int = DEFAULT_WALL_LINES,
        forbidden_cells: set[tuple[int, int]] | None = None,
    ) -> None:
        del grid, forbidden_cells
        captured["line_count"] = line_count

    monkeypatch.setitem(level_blueprints.WALL_ALGORITHMS, "default", fake_default)

    generate_random_blueprint(
        steel_chance=0.0,
        cols=20,
        rows=20,
        wall_algo="normal.40%",
        fuel_count=0,
        flashlight_count=0,
        shoes_count=0,
    )

    assert captured["line_count"] == int(DEFAULT_WALL_LINES * 0.4)
