#!/bin/sh
set -eu

PROJECT_ROOT=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
cd "$PROJECT_ROOT"

if [ -x "$PROJECT_ROOT/.venv/bin/python" ]; then
    DEFAULT_PYTHON="$PROJECT_ROOT/.venv/bin/python"
else
    DEFAULT_PYTHON=python3
fi

PYTHON=${PYTHON:-$DEFAULT_PYTHON}
HOST=${HOST:-127.0.0.1}
PORT=${PORT:-8001}

exec "$PYTHON" -m uvicorn src.main:app --host "$HOST" --port "$PORT" --reload