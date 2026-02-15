from __future__ import annotations

from dataclasses import dataclass
from enum import Enum, auto
from typing import Any, Iterable, Sequence, Tuple

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
CONTROLLER_AXIS_TRIGGERRIGHT = getattr(pygame, "CONTROLLER_AXIS_TRIGGERRIGHT", None)


class CommonAction(Enum):
    CONFIRM = auto()
    BACK = auto()
    START = auto()
    UP = auto()
    DOWN = auto()
    LEFT = auto()
    RIGHT = auto()
    ACCEL = auto()


@dataclass(frozen=True)
class ActionState:
    pressed: bool = False
    released: bool = False
    held: bool = False


@dataclass(frozen=True)
class InputSnapshot:
    actions: dict[CommonAction, ActionState]
    analog_vector: tuple[float, float]
    move_vector: tuple[float, float]
    text_input: str
    keyboard_pressed_keys: set[int]

    def pressed(self, action: CommonAction) -> bool:
        state = self.actions.get(action)
        return bool(state and state.pressed)

    def released(self, action: CommonAction) -> bool:
        state = self.actions.get(action)
        return bool(state and state.released)

    def held(self, action: CommonAction) -> bool:
        state = self.actions.get(action)
        return bool(state and state.held)


@dataclass(frozen=True)
class ClickTarget:
    target_id: Any
    rect: pygame.Rect
    enabled: bool = True


class ClickableMap:
    """Simple rect-based target map for hover/click selection."""

    def __init__(self) -> None:
        self._targets: list[ClickTarget] = []

    def set_targets(self, targets: Iterable[ClickTarget]) -> None:
        self._targets = list(targets)

    def pick_hover(self, pos: tuple[int, int]) -> Any | None:
        for target in self._targets:
            if target.enabled and target.rect.collidepoint(pos):
                return target.target_id
        return None

    def pick_click(self, pos: tuple[int, int]) -> Any | None:
        return self.pick_hover(pos)


class MouseUiGuard:
    """Focus-aware mouse gate with one-frame suppression after focus regain."""

    def __init__(self, *, regain_guard_frames: int = 1) -> None:
        self._regain_guard_frames = max(0, int(regain_guard_frames))
        self._guard_frames = 0

    def handle_focus_event(self, event: pygame.event.Event) -> None:
        if event.type == pygame.WINDOWFOCUSGAINED:
            self._guard_frames = self._regain_guard_frames

    def can_process_mouse(self) -> bool:
        return bool(pygame.mouse.get_focused()) and self._guard_frames == 0

    def end_frame(self) -> None:
        if self._guard_frames > 0:
            self._guard_frames -= 1


class InputHelper:
    """Normalize keyboard/gamepad input into action-based snapshots."""

    _KEYBOARD_ACTION_KEYS: dict[CommonAction, tuple[int, ...]] = {
        CommonAction.CONFIRM: (pygame.K_RETURN, pygame.K_SPACE),
        CommonAction.BACK: (pygame.K_ESCAPE,),
        CommonAction.START: (pygame.K_p,),
        CommonAction.UP: (pygame.K_UP, pygame.K_w),
        CommonAction.DOWN: (pygame.K_DOWN, pygame.K_s),
        CommonAction.LEFT: (pygame.K_LEFT, pygame.K_a),
        CommonAction.RIGHT: (pygame.K_RIGHT, pygame.K_d),
    }

    def __init__(self) -> None:
        self.controller = init_first_controller()
        self.joystick = init_first_joystick() if self.controller is None else None
        self._hat_value = (0, 0)

    def handle_device_event(self, event: pygame.event.Event) -> None:
        if event.type == pygame.JOYDEVICEADDED or (
            CONTROLLER_DEVICE_ADDED is not None
            and event.type == CONTROLLER_DEVICE_ADDED
        ):
            if self.controller is None:
                self.controller = init_first_controller()
            if self.controller is None:
                self.joystick = init_first_joystick()
            return
        if event.type == pygame.JOYDEVICEREMOVED or (
            CONTROLLER_DEVICE_REMOVED is not None
            and event.type == CONTROLLER_DEVICE_REMOVED
        ):
            if self.controller and not self.controller.get_init():
                self.controller = None
            if self.joystick and not self.joystick.get_init():
                self.joystick = None
                self._hat_value = (0, 0)
            return
    def snapshot(
        self,
        events: Iterable[pygame.event.Event],
        keys: Sequence[bool],
        *,
        include_text: bool = False,
    ) -> InputSnapshot:
        pressed: dict[CommonAction, bool] = {action: False for action in CommonAction}
        released: dict[CommonAction, bool] = {action: False for action in CommonAction}
        keyboard_pressed_keys: set[int] = set()
        text_parts: list[str] = []

        for event in events:
            if event.type == pygame.KEYDOWN:
                key = int(event.key)
                keyboard_pressed_keys.add(key)
                if include_text and event.unicode:
                    text_parts.append(event.unicode)
                self._mark_keyboard_action(pressed, key)
                continue
            if event.type == pygame.KEYUP:
                self._mark_keyboard_action(released, int(event.key))
                continue
            if event.type == pygame.JOYBUTTONDOWN or (
                CONTROLLER_BUTTON_DOWN is not None
                and event.type == CONTROLLER_BUTTON_DOWN
            ):
                self._mark_button_action(pressed, event)
                continue
            if event.type == pygame.JOYBUTTONUP or (
                CONTROLLER_BUTTON_DOWN is not None
                and event.type == getattr(pygame, "CONTROLLERBUTTONUP", None)
            ):
                self._mark_button_action(released, event)
                continue
            if event.type == pygame.JOYHATMOTION:
                self._mark_hat_action(pressed, released, event)

        held = self._compute_held_states(keys)
        actions = {
            action: ActionState(
                pressed=pressed[action],
                released=released[action],
                held=held[action],
            )
            for action in CommonAction
        }
        return InputSnapshot(
            actions=actions,
            analog_vector=self.read_analog_vector(),
            move_vector=read_gamepad_move(self.controller, self.joystick),
            text_input=("".join(text_parts) if include_text else ""),
            keyboard_pressed_keys=keyboard_pressed_keys,
        )

    def read_analog_vector(self, *, deadzone: float = DEADZONE) -> tuple[float, float]:
        x = 0.0
        y = 0.0
        controller = self.controller
        joystick = self.joystick
        if controller and controller.get_init():
            if CONTROLLER_AXIS_LEFTX is None or CONTROLLER_AXIS_LEFTY is None:
                return 0.0, 0.0
            x = float(controller.get_axis(CONTROLLER_AXIS_LEFTX))
            y = float(controller.get_axis(CONTROLLER_AXIS_LEFTY))
        elif joystick and joystick.get_init() and joystick.get_numaxes() >= 2:
            x = float(joystick.get_axis(0))
            y = float(joystick.get_axis(1))
        if abs(x) < deadzone:
            x = 0.0
        if abs(y) < deadzone:
            y = 0.0
        return x, y

    def is_confirm_held(self, keys: Sequence[bool] | None = None) -> bool:
        if keys is not None and (
            keys[pygame.K_RETURN] or keys[pygame.K_SPACE]
        ):
            return True
        return self._held_confirm_button()

    def _mark_keyboard_action(self, target: dict[CommonAction, bool], key: int) -> None:
        for action, action_keys in self._KEYBOARD_ACTION_KEYS.items():
            if key in action_keys:
                target[action] = True

    def _mark_button_action(
        self, target: dict[CommonAction, bool], event: pygame.event.Event
    ) -> None:
        if is_confirm_event(event):
            target[CommonAction.CONFIRM] = True
        if is_select_event(event):
            target[CommonAction.BACK] = True
        if is_start_event(event):
            target[CommonAction.START] = True
        if (
            CONTROLLER_BUTTON_DOWN is not None
            and event.type in (
                CONTROLLER_BUTTON_DOWN,
                getattr(pygame, "CONTROLLERBUTTONUP", None),
            )
        ):
            if (
                CONTROLLER_BUTTON_DPAD_UP is not None
                and event.button == CONTROLLER_BUTTON_DPAD_UP
            ):
                target[CommonAction.UP] = True
            if (
                CONTROLLER_BUTTON_DPAD_DOWN is not None
                and event.button == CONTROLLER_BUTTON_DPAD_DOWN
            ):
                target[CommonAction.DOWN] = True
            if (
                CONTROLLER_BUTTON_DPAD_LEFT is not None
                and event.button == CONTROLLER_BUTTON_DPAD_LEFT
            ):
                target[CommonAction.LEFT] = True
            if (
                CONTROLLER_BUTTON_DPAD_RIGHT is not None
                and event.button == CONTROLLER_BUTTON_DPAD_RIGHT
            ):
                target[CommonAction.RIGHT] = True

    def _mark_hat_action(
        self,
        pressed: dict[CommonAction, bool],
        released: dict[CommonAction, bool],
        event: pygame.event.Event,
    ) -> None:
        old_x, old_y = self._hat_value
        new_x, new_y = tuple(event.value)
        if old_y != 1 and new_y == 1:
            pressed[CommonAction.UP] = True
        if old_y == 1 and new_y != 1:
            released[CommonAction.UP] = True
        if old_y != -1 and new_y == -1:
            pressed[CommonAction.DOWN] = True
        if old_y == -1 and new_y != -1:
            released[CommonAction.DOWN] = True
        if old_x != -1 and new_x == -1:
            pressed[CommonAction.LEFT] = True
        if old_x == -1 and new_x != -1:
            released[CommonAction.LEFT] = True
        if old_x != 1 and new_x == 1:
            pressed[CommonAction.RIGHT] = True
        if old_x == 1 and new_x != 1:
            released[CommonAction.RIGHT] = True
        self._hat_value = (new_x, new_y)

    def _compute_held_states(self, keys: Sequence[bool]) -> dict[CommonAction, bool]:
        held: dict[CommonAction, bool] = {action: False for action in CommonAction}
        for action, action_keys in self._KEYBOARD_ACTION_KEYS.items():
            held[action] = any(keys[key] for key in action_keys)
        if self._held_confirm_button():
            held[CommonAction.CONFIRM] = True
        if self._held_select_button():
            held[CommonAction.BACK] = True
        if self._held_start_button():
            held[CommonAction.START] = True
        if self._held_dpad_up():
            held[CommonAction.UP] = True
        if self._held_dpad_down():
            held[CommonAction.DOWN] = True
        if self._held_dpad_left():
            held[CommonAction.LEFT] = True
        if self._held_dpad_right():
            held[CommonAction.RIGHT] = True
        if is_accel_active(keys, self.controller, self.joystick):
            held[CommonAction.ACCEL] = True
        return held

    def _held_confirm_button(self) -> bool:
        controller = self.controller
        joystick = self.joystick
        if controller and controller.get_init():
            if CONTROLLER_BUTTON_A is not None and controller.get_button(
                CONTROLLER_BUTTON_A
            ):
                return True
        if joystick and joystick.get_init():
            if joystick.get_numbuttons() > JOY_BUTTON_A and joystick.get_button(
                JOY_BUTTON_A
            ):
                return True
        return False

    def _held_select_button(self) -> bool:
        controller = self.controller
        joystick = self.joystick
        if controller and controller.get_init():
            if CONTROLLER_BUTTON_BACK is not None and controller.get_button(
                CONTROLLER_BUTTON_BACK
            ):
                return True
        if joystick and joystick.get_init():
            if joystick.get_numbuttons() > JOY_BUTTON_BACK and joystick.get_button(
                JOY_BUTTON_BACK
            ):
                return True
        return False

    def _held_start_button(self) -> bool:
        controller = self.controller
        joystick = self.joystick
        if controller and controller.get_init():
            if CONTROLLER_BUTTON_START is not None and controller.get_button(
                CONTROLLER_BUTTON_START
            ):
                return True
        if joystick and joystick.get_init():
            if joystick.get_numbuttons() > JOY_BUTTON_START and joystick.get_button(
                JOY_BUTTON_START
            ):
                return True
        return False

    def _held_dpad_up(self) -> bool:
        controller = self.controller
        joystick = self.joystick
        if controller and controller.get_init():
            return bool(
                CONTROLLER_BUTTON_DPAD_UP is not None
                and controller.get_button(CONTROLLER_BUTTON_DPAD_UP)
            )
        if joystick and joystick.get_init() and joystick.get_numhats() > 0:
            return joystick.get_hat(0)[1] == 1
        return False

    def _held_dpad_down(self) -> bool:
        controller = self.controller
        joystick = self.joystick
        if controller and controller.get_init():
            return bool(
                CONTROLLER_BUTTON_DPAD_DOWN is not None
                and controller.get_button(CONTROLLER_BUTTON_DPAD_DOWN)
            )
        if joystick and joystick.get_init() and joystick.get_numhats() > 0:
            return joystick.get_hat(0)[1] == -1
        return False

    def _held_dpad_left(self) -> bool:
        controller = self.controller
        joystick = self.joystick
        if controller and controller.get_init():
            return bool(
                CONTROLLER_BUTTON_DPAD_LEFT is not None
                and controller.get_button(CONTROLLER_BUTTON_DPAD_LEFT)
            )
        if joystick and joystick.get_init() and joystick.get_numhats() > 0:
            return joystick.get_hat(0)[0] == -1
        return False

    def _held_dpad_right(self) -> bool:
        controller = self.controller
        joystick = self.joystick
        if controller and controller.get_init():
            return bool(
                CONTROLLER_BUTTON_DPAD_RIGHT is not None
                and controller.get_button(CONTROLLER_BUTTON_DPAD_RIGHT)
            )
        if joystick and joystick.get_init() and joystick.get_numhats() > 0:
            return joystick.get_hat(0)[0] == 1
        return False


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


def is_confirm_held(
    controller: pygame.controller.Controller | None,
    joystick: pygame.joystick.Joystick | None,
) -> bool:
    """Return True if the confirm (South/A) button is currently held."""
    if controller and controller.get_init():
        if CONTROLLER_BUTTON_A is not None and controller.get_button(
            CONTROLLER_BUTTON_A
        ):
            return True
    if joystick and joystick.get_init():
        if joystick.get_numbuttons() > JOY_BUTTON_A and joystick.get_button(
            JOY_BUTTON_A
        ):
            return True
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
        if CONTROLLER_BUTTON_DPAD_LEFT is not None and controller.get_button(
            CONTROLLER_BUTTON_DPAD_LEFT
        ):
            x = -1.0
        elif CONTROLLER_BUTTON_DPAD_RIGHT is not None and controller.get_button(
            CONTROLLER_BUTTON_DPAD_RIGHT
        ):
            x = 1.0
        if CONTROLLER_BUTTON_DPAD_UP is not None and controller.get_button(
            CONTROLLER_BUTTON_DPAD_UP
        ):
            y = -1.0
        elif CONTROLLER_BUTTON_DPAD_DOWN is not None and controller.get_button(
            CONTROLLER_BUTTON_DPAD_DOWN
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
        if CONTROLLER_BUTTON_RB is not None and controller.get_button(
            CONTROLLER_BUTTON_RB
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
