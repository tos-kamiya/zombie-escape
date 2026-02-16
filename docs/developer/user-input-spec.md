# User Input Specification (Normalization and Runtime Policy)

This document defines how `zombie-escape` handles player input and related
window/runtime input behavior. It is the implementation-oriented source of
truth for developers.

Scope:

- Keyboard, mouse, and gamepad/joystick input normalization.
- Gameplay pause behavior triggered by input and window operations.
- Screen-level usage contract for normalized input snapshots.

Out of scope:

- Key remapping UI.
- Multiplayer input routing.
- Replay/recorded input systems.

## 1. Goals

- Keep gameplay and menu control behavior consistent across devices.
- Reduce per-screen duplicated event branching.
- Separate raw device events from game action semantics.
- Make window/focus transitions predictable during gameplay.

## 2. Input Categories

Input is grouped into three categories.

### 2.1 Keyboard-Only

Keyboard-driven actions that should not be abstracted into cross-device
actions.

Examples:

- Seed text entry on title screen.
- Window operations: `[` / `]` / `F`.
- Screen-local utility keys such as settings reset.

### 2.2 Analog Vector

Continuous movement vectors from analog input sources.

- Controller API: left stick axes.
- Joystick API: axis 0/1 fallback.
- Deadzone is applied before values are exposed.

### 2.3 Common Actions

Device-agnostic discrete actions used by screens and gameplay logic.

- `CONFIRM`
- `BACK`
- `START`
- `UP`
- `DOWN`
- `LEFT`
- `RIGHT`
- `ACCEL`

Screen semantics are screen-defined. Example: `START` means pause in gameplay,
but may mean open/advance in other screens.

## 3. Normalization Responsibilities

`InputHelper` is responsible for:

- Initializing and tracking controller/joystick availability.
- Handling device add/remove events.
- Building per-frame `InputSnapshot` from event stream + key state.
- Exposing `pressed`, `released`, `held` states for Common Actions.
- Exposing movement vectors (`analog_vector`, `move_vector`).

`InputHelper` should not decide game semantics (pause, retry, screen transition).
Those remain screen responsibilities.

## 4. Data Model

Current target model:

```python
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
```

Notes:

- `text_input` is populated only when `include_text=True`.
- `keyboard_pressed_keys` stores this-frame key presses for keyboard-only logic.

## 5. Default Mappings

### 5.1 Common Actions

- `CONFIRM`
  - Keyboard: `Enter`, `Space`
  - Gamepad: South (`A`)
- `BACK`
  - Keyboard: `Escape`
  - Gamepad: `Back/Select`
- `START`
  - Keyboard: `P`
  - Gamepad: `Start`
- `UP`/`DOWN`/`LEFT`/`RIGHT`
  - Keyboard: arrows + `WASD`
  - Gamepad: D-pad / hat
- `ACCEL`
  - Keyboard: `LShift` / `RShift`
  - Gamepad: `RB` and/or right trigger threshold

### 5.2 Analog Vector

- Left stick (controller API) or axis fallback (joystick API).
- Deadzone filtering is mandatory.

### 5.3 Keyboard-Only Operations

- Title seed text entry and edit behavior.
- Gameplay window operations (`[` / `]` / `F`).
- Screen-specific utility keys (for example, settings reset).

## 6. Gameplay Pause and Window Policy

To keep input/focus transitions explicit and safe in gameplay:

- Enter manual pause after `[` / `]` / `F` window operations.
- Enter manual pause on runtime resize events:
  - `VIDEORESIZE`
  - `WINDOWSIZECHANGED`
- Corner hotspot triangles trigger pause on left-click, not on hover.
- In `--debug` mode (when pause overlay is hidden), render a small
  `-- paused --` marker near the top of the screen while paused.
- In `--debug` mode, left mouse button release while paused should resume
  gameplay (same behavior as selecting `Resume` in the normal pause overlay).
- Pause overlay menu should expose `Resume`, `Return to Title`, and `Toggle Fullscreen`.

This behavior is intentional and should be preserved unless replaced by a
documented alternative policy.

## 7. Screen Usage Contract

Each `screens/*.py` should process input in this order:

1. Read events.
2. Handle screen-level window/runtime events.
3. Build `snapshot = input_helper.snapshot(events, keys, ...)`.
4. Process Keyboard-Only input.
5. Process Common Actions.
6. For gameplay movement, use `snapshot.move_vector` plus keyboard/mouse policy.

Avoid:

- Re-implementing raw gamepad button/hat branching in each screen.
- Reading controller/joystick raw APIs directly in screen code unless there is a
  documented exception.

## 8. Compatibility Requirements

Required:

- Keyboard-only operation works across title/settings/gameplay/game-over.
- Gamepad-only operation works for non-keyboard-only actions.
- Device hotplug does not crash and recovers cleanly.
- Acceleration behavior remains consistent with current gameplay expectations.

Allowed internal changes:

- Function/class naming.
- Module boundaries and helper layering.
- Event handling location, as long as runtime behavior remains equivalent.

## 9. Validation Checklist

- Verify keyboard navigation across all major screens.
- Verify gamepad navigation across all major screens.
- Verify analog + D-pad/hat interaction does not produce unstable vectors.
- Verify `ACCEL` behavior for Shift and gamepad equivalents.
- Verify pause enters after `[` / `]` / `F` and resize events.
- Verify `--debug` paused marker is visible while paused.
- Verify `--debug` mode can resume from pause by left-clicking anywhere in the window.
- Verify device add/remove handling during runtime.

## 10. Maintenance Rules (Updated)

- When input behavior changes, update this document in the same change set.
- When gameplay pause/window policy changes, update both:
  - `docs/developer/user-input-spec.md`
  - `docs/design/gameplay-flow.md` and/or `docs/design/windowing-platform.md`
- Keep this spec implementation-focused; keep long design rationale in design docs.
- If a new screen introduces keyboard-only controls, add them to section 5.3.
