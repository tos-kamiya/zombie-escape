#!/usr/bin/env bash
set -euo pipefail

PY_VERSIONS="${PY_VERSIONS:-3.10 3.11 3.12 3.13}"

for version in ${PY_VERSIONS}; do
  venv_dir=".venv-py${version/./}"
  echo "==> Python ${version}"
  uv venv --clear --python "${version}" "${venv_dir}"
  uv pip install -p "${venv_dir}/bin/python" -e ".[dev]"
  uv run -p "${venv_dir}/bin/python" ruff check
  uv run -p "${venv_dir}/bin/python" pytest
done
