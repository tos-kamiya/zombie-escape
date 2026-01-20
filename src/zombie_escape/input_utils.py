from __future__ import annotations

from typing import Tuple

import pygame

DEADZONE = 0.25
JOY_BUTTON_A = 0
JOY_BUTTON_BACK = 6
JOY_BUTTON_START = 7
JOY_BUTTON_RB = 5

CONTROLLER_AVAILABLE = hasattr(pygame, "controller")
CONTROLLER_DEVICE_ADDED = getattr(pygame, "CONTROLLERDEVICEADDED", None)
CONTROLLER_DEVICE_REMOVED = getattr(pygame, "CONTROLLERDEVICEREMOVED", None)
CONTROLLER_BUTTON_DOWN = getattr(pygame, "CONTROLLERBUTTONDOWN", None)
CONTROLLER_BUTTON_A = getattr(pygame, "CONTROLLER_BUTTON_A", None)
CONTROLLER_BUTTON_BACK = getattr(pygame, "CONTROLLER_BUTTON_BACK", None)
CONTROLLER_BUTTON_START = getattr(pygame, "CONTROLLER_BUTTON_START", None)
CONTROLLER_BUTTON_DPAD_UP = getattr(pygame, "CONTROLLER_BUTTON_DPAD_UP", None)
CONTROLLER_BUTTON_DPAD_DOWN = getattr(pygame, "CONTROLLER_BUTTON_DPAD_DOWN", None)
CONTROLLER_BUTTON_DPAD_LEFT = getattr(pygame, "CONTROLLER_BUTTON_DPAD_LEFT", None)
CONTROLLER_BUTTON_DPAD_RIGHT = getattr(pygame, "CONTROLLER_BUTTON_DPAD_RIGHT", None)
CONTROLLER_BUTTON_RB = getattr(pygame, "CONTROLLER_BUTTON_RIGHTSHOULDER", None)
CONTROLLER_AXIS_LEFTX = getattr(pygame, "CONTROLLER_AXIS_LEFTX", None)
CONTROLLER_AXIS_LEFTY = getattr(pygame, "CONTROLLER_AXIS_LEFTY", None)
CONTROLLER_AXIS_TRIGGERRIGHT = getattr(
    pygame, "CONTROLLER_AXIS_TRIGGERRIGHT", None
)


def init_first_controller() -> pygame.controller.Controller | None:
    if not CONTROLLER_AVAILABLE:
        return None
    try:
        if pygame.controller.get_count() > 0:
            controller = pygame.controller.Controller(0)
            if not controller.get_init():
                controller.init()
            return controller
    except pygame.error:
        return None
    return None


def init_first_joystick() -> pygame.joystick.Joystick | None:
    try:
        if pygame.joystick.get_count() > 0:
            joystick = pygame.joystick.Joystick(0)
            if not joystick.get_init():
                joystick.init()
            return joystick
    except pygame.error:
        return None
    return None


def is_confirm_event(event: pygame.event.Event) -> bool:
    if CONTROLLER_BUTTON_DOWN is not None and event.type == CONTROLLER_BUTTON_DOWN:
        return CONTROLLER_BUTTON_A is not None and event.button == CONTROLLER_BUTTON_A
    if event.type == pygame.JOYBUTTONDOWN:
        return event.button == JOY_BUTTON_A
    return False


def is_start_event(event: pygame.event.Event) -> bool:
    if CONTROLLER_BUTTON_DOWN is not None and event.type == CONTROLLER_BUTTON_DOWN:
        return (
            CONTROLLER_BUTTON_START is not None
            and event.button == CONTROLLER_BUTTON_START
        )
    if event.type == pygame.JOYBUTTONDOWN:
        return event.button == JOY_BUTTON_START
    return False


def is_select_event(event: pygame.event.Event) -> bool:
    if CONTROLLER_BUTTON_DOWN is not None and event.type == CONTROLLER_BUTTON_DOWN:
        return (
            CONTROLLER_BUTTON_BACK is not None
            and event.button == CONTROLLER_BUTTON_BACK
        )
    if event.type == pygame.JOYBUTTONDOWN:
        return event.button == JOY_BUTTON_BACK
    return False


def read_gamepad_move(
    controller: pygame.controller.Controller | None,
    joystick: pygame.joystick.Joystick | None,
    *,
    deadzone: float = DEADZONE,
) -> Tuple[float, float]:
    x = 0.0
    y = 0.0
    if controller and controller.get_init():
        if CONTROLLER_AXIS_LEFTX is None or CONTROLLER_AXIS_LEFTY is None:
            return 0.0, 0.0
        x = float(controller.get_axis(CONTROLLER_AXIS_LEFTX))
        y = float(controller.get_axis(CONTROLLER_AXIS_LEFTY))
        if abs(x) < deadzone:
            x = 0.0
        if abs(y) < deadzone:
            y = 0.0
        if (
            CONTROLLER_BUTTON_DPAD_LEFT is not None
            and controller.get_button(CONTROLLER_BUTTON_DPAD_LEFT)
        ):
            x = -1.0
        elif (
            CONTROLLER_BUTTON_DPAD_RIGHT is not None
            and controller.get_button(CONTROLLER_BUTTON_DPAD_RIGHT)
        ):
            x = 1.0
        if (
            CONTROLLER_BUTTON_DPAD_UP is not None
            and controller.get_button(CONTROLLER_BUTTON_DPAD_UP)
        ):
            y = -1.0
        elif (
            CONTROLLER_BUTTON_DPAD_DOWN is not None
            and controller.get_button(CONTROLLER_BUTTON_DPAD_DOWN)
        ):
            y = 1.0
        return x, y

    if joystick and joystick.get_init():
        if joystick.get_numaxes() >= 2:
            x = float(joystick.get_axis(0))
            y = float(joystick.get_axis(1))
            if abs(x) < deadzone:
                x = 0.0
            if abs(y) < deadzone:
                y = 0.0
        if joystick.get_numhats() > 0:
            hat_x, hat_y = joystick.get_hat(0)
            if hat_x:
                x = float(hat_x)
            if hat_y:
                y = float(-hat_y)
    return x, y


def is_accel_active(
    keys: pygame.key.ScancodeWrapper,
    controller: pygame.controller.Controller | None,
    joystick: pygame.joystick.Joystick | None,
) -> bool:
    if keys[pygame.K_LSHIFT] or keys[pygame.K_RSHIFT]:
        return True
    if controller and controller.get_init():
        if (
            CONTROLLER_BUTTON_RB is not None
            and controller.get_button(CONTROLLER_BUTTON_RB)
        ):
            return True
        if CONTROLLER_AXIS_TRIGGERRIGHT is not None:
            if controller.get_axis(CONTROLLER_AXIS_TRIGGERRIGHT) > DEADZONE:
                return True
    if joystick and joystick.get_init():
        if joystick.get_numbuttons() > JOY_BUTTON_RB:
            if joystick.get_button(JOY_BUTTON_RB):
                return True
        if joystick.get_numaxes() > 5:
            if joystick.get_axis(5) > DEADZONE:
                return True
    return False
