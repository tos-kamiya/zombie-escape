# Repository Guidelines

## Project Structure & Module Organization
- Core game loop and entities live in `src/zombie_escape/zombie_escape.py`; configuration helpers in `config.py`; level layout logic in `level_blueprints.py`; package metadata in `__about__.py`.
- Screenshots sit in `imgs/`; `dev-samples/` holds the Windows demo binary and supporting assets; keep it untouched unless preparing a new release build.
- Tests belong in `tests/` (currently minimal). Add fixtures and helpers there instead of mixing them into game code.

## Build, Test, and Development Commands
- Create an environment with uv (Python 3.10+): `uv venv --python 3.12` then `source .venv/bin/activate` (or `Scripts\\activate`).
- Install for development: `uv pip install -e .` (pulls `pygame` and `platformdirs`).
- Run the game: `uv run zombie-escape` (preferred) or `uv run python -m zombie_escape.zombie_escape` from the repo root after install.
- Package check: `uv pip install .` to verify a clean install flow before tagging a release.

## Coding Style & Naming Conventions
- Follow PEP 8 with 4-space indentation and type hints (see existing signatures). Use `UPPER_SNAKE_CASE` for constants, `lower_snake_case` for functions/variables, and `CamelCase` for classes.
- Keep game state changes side-effect clear; avoid hidden globals beyond the existing constants.
- When adding configuration, extend `DEFAULT_CONFIG` in `config.py` and ensure persistence via `load_config`/`save_config`.

## Testing Guidelines
- Use `pytest` for new tests; place files as `tests/test_*.py`. Prefer deterministic unit tests around utility functions and configuration helpers.
- For gameplay changes, document manual steps (expected behavior, repro keys, map conditions) in the PR if automation is impractical.
- Aim to include at least one new test when modifying logic that affects spawning, movement, or configuration parsing.

## Commit & Pull Request Guidelines
- Use semantic commit messages: `<type>(<scope>): <description>` (e.g., `feat(ai): add fast zombie ratio toggle`, `fix(config): persist car hint delay`, `chore: bump version`). Keep descriptions imperative and under ~72 chars.
- In PRs, include: purpose, scope of change, manual/automated test results, and screenshots or short clips for visual tweaks.
- Link related issues, note any config migrations, and call out gameplay-affecting parameter changes.

## Security & Configuration Tips
- User config is stored under the platform-specific path from `platformdirs.user_config_dir`; avoid checking personal `config.json` into the repo.
- Do not commit large binaries—publish new `.exe` builds via Releases and keep `dev-samples/` aligned with the latest tagged artifact.
