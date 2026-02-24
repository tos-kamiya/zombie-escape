import pytest

from zombie_escape.entities.base_line_bot import BaseLineBot

pygame = pytest.importorskip("pygame")


class _DummyLineBot(BaseLineBot):
    def __init__(self) -> None:
        super().__init__()
        self.direction = (1, 0)


def test_movement_axis_uses_direction() -> None:
    bot = _DummyLineBot()
    bot.direction = (1, 0)
    assert bot._movement_axis() == "x"
    bot.direction = (-3, 0)
    assert bot._movement_axis() == "x"
    bot.direction = (0, 2)
    assert bot._movement_axis() == "y"
    bot.direction = (1, 4)
    assert bot._movement_axis() == "y"


def test_forward_cell_follows_current_direction() -> None:
    bot = _DummyLineBot()
    bot.direction = (1, 0)
    assert bot._forward_cell(x=25.0, y=35.0, cell_size=10) == (3, 3)
    bot.direction = (-1, 0)
    assert bot._forward_cell(x=25.0, y=35.0, cell_size=10) == (1, 3)
    bot.direction = (0, 1)
    assert bot._forward_cell(x=25.0, y=35.0, cell_size=10) == (2, 4)
    bot.direction = (0, -1)
    assert bot._forward_cell(x=25.0, y=35.0, cell_size=10) == (2, 2)


def test_forward_cell_handles_invalid_cell_size_and_step() -> None:
    bot = _DummyLineBot()
    bot.direction = (1, 0)
    assert bot._forward_cell(x=25.0, y=35.0, cell_size=0) is None
    assert bot._forward_cell(x=25.0, y=35.0, cell_size=10, step_cells=0) == (3, 3)
    assert bot._forward_cell(x=25.0, y=35.0, cell_size=10, step_cells=2) == (4, 3)

