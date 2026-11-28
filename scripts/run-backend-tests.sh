#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

if [ -x "$ROOT_DIR/venv/bin/pytest" ]; then
  PYTEST="$ROOT_DIR/venv/bin/pytest"
elif [ -x "$ROOT_DIR/.venv/bin/pytest" ]; then
  PYTEST="$ROOT_DIR/.venv/bin/pytest"
elif command -v pytest >/dev/null 2>&1; then
  PYTEST="$(command -v pytest)"
else
  echo "Error: pytest not found in ./venv/bin/pytest, ./.venv/bin/pytest, or PATH." >&2
  exit 1
fi

exec "$PYTEST" "$@"
