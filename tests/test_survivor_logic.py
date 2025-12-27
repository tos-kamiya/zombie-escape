import math

from zombie_escape.zombie_escape import (
    CAR_SPEED,
    SURVIVOR_MAX_SAFE_PASSENGERS,
    SURVIVOR_MIN_SPEED_FACTOR,
    calculate_car_speed_for_passengers,
)


def test_car_speed_no_passengers_matches_base():
    assert math.isclose(
        calculate_car_speed_for_passengers(0),
        CAR_SPEED,
        rel_tol=1e-6,
    )


def test_car_speed_respects_penalty_and_floor():
    safe_limit_speed = calculate_car_speed_for_passengers(SURVIVOR_MAX_SAFE_PASSENGERS)
    assert safe_limit_speed < CAR_SPEED
    assert safe_limit_speed >= CAR_SPEED * SURVIVOR_MIN_SPEED_FACTOR


def test_car_speed_clamped_when_exceeding_limit():
    overloaded_speed = calculate_car_speed_for_passengers(SURVIVOR_MAX_SAFE_PASSENGERS + 5)
    assert math.isclose(
        overloaded_speed,
        CAR_SPEED * SURVIVOR_MIN_SPEED_FACTOR,
        rel_tol=1e-6,
    )
