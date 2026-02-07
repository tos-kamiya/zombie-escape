import math
from types import SimpleNamespace

from zombie_escape.zombie_escape import (
    CAR_SPEED,
    SURVIVOR_MAX_SAFE_PASSENGERS,
    SURVIVOR_MIN_SPEED_FACTOR,
    calculate_car_speed_for_passengers,
)
from zombie_escape.gameplay import (
    apply_passenger_speed_penalty,
    increase_survivor_capacity,
)


def test_car_speed_no_passengers_matches_base() -> None:
    assert math.isclose(
        calculate_car_speed_for_passengers(0),
        CAR_SPEED,
        rel_tol=1e-6,
    )


def test_car_speed_respects_penalty_and_floor() -> None:
    safe_limit_speed = calculate_car_speed_for_passengers(
        SURVIVOR_MAX_SAFE_PASSENGERS,
        capacity=SURVIVOR_MAX_SAFE_PASSENGERS,
    )
    assert safe_limit_speed < CAR_SPEED
    assert safe_limit_speed >= CAR_SPEED * SURVIVOR_MIN_SPEED_FACTOR


def test_car_speed_over_capacity_follows_inverse_root() -> None:
    capacity = SURVIVOR_MAX_SAFE_PASSENGERS
    passengers = capacity + 2  # sqrt(3) denominator
    overloaded_speed = calculate_car_speed_for_passengers(
        passengers,
        capacity=capacity,
    )
    expected = CAR_SPEED / math.sqrt(passengers - capacity + 1)
    assert math.isclose(overloaded_speed, expected, rel_tol=1e-6)


def test_car_speed_respects_min_floor_when_extreme_overload() -> None:
    overloaded_speed = calculate_car_speed_for_passengers(
        SURVIVOR_MAX_SAFE_PASSENGERS + 200,
        capacity=SURVIVOR_MAX_SAFE_PASSENGERS,
    )
    assert overloaded_speed == CAR_SPEED * SURVIVOR_MIN_SPEED_FACTOR


def test_capacity_boost_refreshes_speed_after_overload() -> None:
    passengers = SURVIVOR_MAX_SAFE_PASSENGERS + 1
    car = SimpleNamespace(speed=CAR_SPEED)
    game_data = SimpleNamespace(
        car=car,
        stage=SimpleNamespace(survivor_rescue_stage=True),
        state=SimpleNamespace(
            survivors_onboard=passengers,
            survivor_capacity=SURVIVOR_MAX_SAFE_PASSENGERS,
        ),
    )
    apply_passenger_speed_penalty(game_data)
    overloaded_speed = game_data.car.speed
    assert math.isclose(overloaded_speed, CAR_SPEED / math.sqrt(2), rel_tol=1e-6)

    increase_survivor_capacity(game_data, increments=1)
    refreshed_speed = game_data.car.speed
    assert refreshed_speed > overloaded_speed
    assert math.isclose(
        refreshed_speed,
        calculate_car_speed_for_passengers(
            passengers,
            capacity=game_data.state.survivor_capacity,
        ),
        rel_tol=1e-6,
    )
