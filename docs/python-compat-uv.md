# Python互換性確認（uv / CPython 3.10-3.13）

この文書は、`pyproject.toml` の `requires-python = ">=3.10"` に沿って、uv を使って CPython 3.10 / 3.11 / 3.12 / 3.13 で動作確認するためのコマンド例をまとめたものです。

## 前提

- uv がインストール済みであること
- リポジトリルートで実行すること
- 依存関係は `pyproject.toml` に記載済み（`pygame` など）

## 共通手順（各バージョンで実行 / activate不要）

以下の手順を **3.10 / 3.11 / 3.12 / 3.13** それぞれで繰り返します。`.venv/bin/python` を指定して `uv` を実行するため、`activate` は不要です。

```bash
# 例: 3.12 の場合
uv venv --python 3.12
uv pip install -p .venv/bin/python -e .
uv pip install -p .venv/bin/python pytest
uv run -p .venv/bin/python -m pytest
uv run -p .venv/bin/python -m ruff check
```

## バージョン別コマンド一覧

### CPython 3.10

```bash
uv venv --clear --python 3.10
uv pip install -p .venv/bin/python -e .
uv pip install -p .venv/bin/python pytest
uv run -p .venv/bin/python -m pytest
uv run -p .venv/bin/python -m ruff check
```

### CPython 3.11

```bash
uv venv --clear --python 3.11
uv pip install -p .venv/bin/python -e .
uv pip install -p .venv/bin/python pytest
uv run -p .venv/bin/python -m pytest
uv run -p .venv/bin/python -m ruff check
```

### CPython 3.12

```bash
uv venv --clear --python 3.12
uv pip install -p .venv/bin/python -e .
uv pip install -p .venv/bin/python pytest
uv run -p .venv/bin/python -m pytest
uv run -p .venv/bin/python -m ruff check
```

### CPython 3.13

```bash
uv venv --clear --python 3.13
uv pip install -p .venv/bin/python -e .
uv pip install -p .venv/bin/python pytest
uv run -p .venv/bin/python -m pytest
uv run -p .venv/bin/python -m ruff check
```

## 補足

- 実行コマンドは互換性確認のため `uv run -p .venv/bin/python -m pytest` を推奨します。ゲーム起動が必要なら `uv run -p .venv/bin/python zombie-escape` でも構いません。
- 依存関係の取得で失敗する場合は、該当バージョンの `pygame` が提供されているかを確認してください。
