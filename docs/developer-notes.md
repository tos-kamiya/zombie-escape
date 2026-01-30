# Developer Notes (uv / CPython 3.12)

This doc collects compact, developer-facing commands for local verification and asset generation.
We target CPython 3.12 here for day-to-day checks.

## Prerequisites

- uv is installed
- Run from the repository root

## Quick Setup (3.12)

```bash
uv venv --clear --python 3.12
uv pip install -p .venv/bin/python -e ".[dev]"
```

## Verification

```bash
uv run -p .venv/bin/python -m pytest
uv run -p .venv/bin/python -m ruff check
uv run -p .venv/bin/python -m pyright
```

## Export Documentation Images

```bash
uv run -p .venv/bin/python -m zombie_escape --export-images
```

Images are written to `imgs/exports/` and are intended to be committed.
