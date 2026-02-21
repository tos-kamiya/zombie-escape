import pytest

from zombie_escape.entities import Player, Survivor, TransportBot
from zombie_escape.level_constants import DEFAULT_CELL_SIZE, DEFAULT_GRID_COLS, DEFAULT_GRID_ROWS
from zombie_escape.models import LevelLayout

pygame = pytest.importorskip("pygame")


def _init_pygame() -> None:
    if not pygame.get_init():
        pygame.init()


def _make_layout() -> LevelLayout:
    return LevelLayout(
        field_rect=pygame.Rect(
            0,
            0,
            DEFAULT_GRID_COLS * DEFAULT_CELL_SIZE,
            DEFAULT_GRID_ROWS * DEFAULT_CELL_SIZE,
        ),
        grid_cols=DEFAULT_GRID_COLS,
        grid_rows=DEFAULT_GRID_ROWS,
        outside_cells=set(),
        walkable_cells=[],
        outer_wall_cells=set(),
        wall_cells=set(),
        steel_beam_cells=set(),
        pitfall_cells=set(),
        car_walkable_cells=set(),
        car_spawn_cells=[],
        fall_spawn_cells=set(),
        spiky_plant_cells=set(),
        puddle_cells=set(),
        bevel_corners={},
        moving_floor_cells={},
    )


def test_transport_bot_auto_boards_player_and_moves() -> None:
    _init_pygame()
    layout = _make_layout()
    bot = TransportBot(
        [(100, 100), (140, 100)],
        speed=5.0,
        activation_radius=12.0,
        door_close_ms=0,
        end_wait_ms=0,
    )
    player = Player(100, 100)
    survivor_group = pygame.sprite.Group()
    zombie_group = pygame.sprite.Group()
    all_sprites = pygame.sprite.LayeredUpdates()
    all_sprites.add(player)
    all_sprites.add(bot)

    bot.update(
        [],
        player=player,
        survivor_group=survivor_group,
        zombie_group=zombie_group,
        all_sprites=all_sprites,
        layout=layout,
        cell_size=DEFAULT_CELL_SIZE,
        pitfall_cells=set(),
        now_ms=0,
    )

    assert player.mounted_vehicle is bot
    assert player not in all_sprites
    assert bot.moving
    assert bot.x > 100


def test_transport_bot_reverses_when_pitfall_blocks_path() -> None:
    _init_pygame()
    layout = _make_layout()
    bot = TransportBot(
        [(100, 100), (200, 100)],
        speed=5.0,
        activation_radius=12.0,
        door_close_ms=0,
        end_wait_ms=0,
    )
    player = Player(100, 100)
    survivor_group = pygame.sprite.Group()
    zombie_group = pygame.sprite.Group()
    all_sprites = pygame.sprite.LayeredUpdates()
    all_sprites.add(player)
    all_sprites.add(bot)

    bot.update(
        [],
        player=player,
        survivor_group=survivor_group,
        zombie_group=zombie_group,
        all_sprites=all_sprites,
        layout=layout,
        cell_size=50,
        pitfall_cells={(2, 2)},
        now_ms=0,
    )

    assert player.mounted_vehicle is bot
    assert bot.x == 100
    assert bot._direction == -1


def test_transport_bot_disembarks_survivor_at_endpoint() -> None:
    _init_pygame()
    layout = _make_layout()
    bot = TransportBot(
        [(100, 100), (130, 100)],
        speed=10.0,
        activation_radius=12.0,
        door_close_ms=0,
        end_wait_ms=1000,
    )
    survivor = Survivor(100, 100)
    survivor_group = pygame.sprite.Group()
    survivor_group.add(survivor)
    zombie_group = pygame.sprite.Group()
    all_sprites = pygame.sprite.LayeredUpdates()
    all_sprites.add(survivor)
    all_sprites.add(bot)

    for now_ms in range(0, 10):
        bot.update(
            [],
            player=None,
            survivor_group=survivor_group,
            zombie_group=zombie_group,
            all_sprites=all_sprites,
            layout=layout,
            cell_size=DEFAULT_CELL_SIZE,
            pitfall_cells=set(),
            now_ms=now_ms,
        )

    assert survivor.mounted_vehicle is None
    assert survivor in survivor_group
    assert survivor in all_sprites
    assert bot.moving is False
