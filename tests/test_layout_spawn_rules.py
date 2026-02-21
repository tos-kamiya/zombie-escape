from zombie_escape.entities_constants import MovingFloorDirection
from zombie_escape.gameplay.layout import generate_level_from_blueprint
from zombie_escape.models import Stage, transport_path_cells


def test_car_and_item_spawn_cells_share_blocking_rules() -> None:
    stage = Stage(
        id="spawn_rules_shared",
        name_key="n",
        description_key="d",
        grid_cols=30,
        grid_rows=15,
        transport_bot_paths=[[(3, 3), (10, 3)]],
        moving_floor_cells={(6, 4): MovingFloorDirection.UP},
        fire_floor_zones=[(7, 4, 1, 1)],
        zombie_normal_ratio=1.0,
    )

    layout, layout_data, _, _, _ = generate_level_from_blueprint(
        stage,
        {},
        seed=12345,
        ambient_palette_key=None,
    )
    blocked_cells = (
        transport_path_cells(stage.transport_bot_paths)
        | set(layout.fire_floor_cells)
        | set(layout.moving_floor_cells.keys())
    )
    car_blocked_cells = blocked_cells | set(layout.spiky_plant_cells)

    assert all(cell not in blocked_cells for cell in layout_data["item_spawn_cells"])
    assert all(cell not in car_blocked_cells for cell in layout_data["car_spawn_cells"])
    assert all(cell not in car_blocked_cells for cell in layout_data["car_cells"])
    assert set(layout_data["car_spawn_cells"]).issubset(
        set(layout_data["car_walkable_cells"])
    )
