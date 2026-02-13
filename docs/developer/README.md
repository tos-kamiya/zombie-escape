# Developer Docs

This folder collects developer-facing setup/build notes.

## Contents

- `docs/developer/windows-build.md`: Windows binary build notes (PyInstaller).
- `docs/developer/zone-from-ascii.md`: ASCII map to zone settings tool.
- `docs/developer/wall-hug-optimization.md`: Parameter tuning for wall-hugging AI.

## Quick Setup (3.12)

Prerequisites:

- uv is installed
- Run from the repository root

```bash
uv venv --clear --python 3.12
uv pip install -p .venv/bin/python -e ".[dev]"
```

## Verification

```bash
uv run -p .venv/bin/python pytest
uv run -p .venv/bin/python ruff check
uv run -p .venv/bin/python pyright
```

## Export Documentation Images

```bash
uv run -p .venv/bin/python -m zombie_escape --export-images
```

Images are written to `imgs/exports/` at 4x size and are intended to be committed.
Zombie dog (`zombie-dog.png`) is exported at a 45° up-left angle.

## Multi-Python Checks

This project targets multiple Python versions. Run the same checks for each
version listed in `pyproject.toml` classifiers.

### Scripted check (recommended)

```bash
./scripts/check-multi-py.sh
```

Optional: override versions.

```bash
PY_VERSIONS="3.10 3.12" ./scripts/check-multi-py.sh
```

### What it does

- Creates per-version virtual environments in `.venv-py310`, `.venv-py311`, etc.
- Installs dev dependencies.
- Runs `python -m ruff check` and `python -m pytest` for each version.
- Runs `python -m compileall src` to verify bytecode compilation.

## Related docs

- `docs/design.md`: gameplay/data flow overview.
- `docs/developer/user-input-spec.md`: user input normalization spec (keyboard/gamepad).
