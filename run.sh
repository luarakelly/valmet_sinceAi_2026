#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_DIR="$ROOT_DIR/backend"
# Linux/macOS venvs use bin/python; Windows venvs (Git Bash) use Scripts/python.exe.
PYTHON="$BACKEND_DIR/.venv/bin/python"
if [ ! -x "$PYTHON" ] && [ -x "$BACKEND_DIR/.venv/Scripts/python.exe" ]; then
  PYTHON="$BACKEND_DIR/.venv/Scripts/python.exe"
fi

if [ ! -x "$PYTHON" ]; then
  printf '%s\n' "Backend environment not found. Run ./initialize.sh first."
  exit 1
fi

cd "$BACKEND_DIR"
exec "$PYTHON" -m uvicorn app.main:app --reload
