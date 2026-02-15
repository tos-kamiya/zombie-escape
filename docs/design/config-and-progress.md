# Config and Progress

## Config (`config.py`)

- `DEFAULT_CONFIG` is the baseline.
- `load_config()` merges user config onto defaults.
- `save_config()` persists to platform-specific config dir via `platformdirs.user_config_dir(APP_NAME, APP_NAME)`.
- Includes visual toggles such as `visual.shadows.enabled`.

## Progress (`progress.py`)

- Stores stage clear counts in user data dir (`platformdirs.user_data_dir`).

## Seed and RNG

- Deterministic RNG comes from `rng.py` (MT19937).
- Title screen supports seed input and generated seed values.

## Buddy Stage Win Addendum

For buddy-required stages (`buddy_required_count > 0`), win requires:

1. Escape condition (outside with car, or endurance completion for carless endurance stage)
2. Buddy condition (`buddy_onboard + nearby_following_buddies >= buddy_required_count`)
