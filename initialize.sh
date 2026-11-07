#!/usr/bin/env bash
# One-time setup: backend virtual environment + dependencies + .env.
# Works in Git Bash (Windows), Linux and macOS, with or without uv.
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_DIR="$ROOT_DIR/backend"
VENV_DIR="$BACKEND_DIR/.venv"

venv_python() {
  if [ -x "$VENV_DIR/Scripts/python.exe" ]; then
    printf '%s' "$VENV_DIR/Scripts/python.exe"   # Windows (Git Bash)
  else
    printf '%s' "$VENV_DIR/bin/python"            # Linux / macOS
  fi
}

find_system_python() {
  for candidate in python python3 "py -3"; do
    if $candidate -c "import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)" >/dev/null 2>&1; then
      printf '%s' "$candidate"
      return 0
    fi
  done
  return 1
}

if [ -x "$(venv_python)" ]; then
  printf '%s\n' "Using existing environment: $VENV_DIR"
elif command -v uv >/dev/null 2>&1; then
  printf '%s\n' "Creating environment with uv..."
  uv venv "$VENV_DIR"
else
  SYSTEM_PYTHON="$(find_system_python)" || {
    printf '%s\n' "Python 3.10+ not found. Install it from https://www.python.org/downloads/ and run this script again."
    exit 1
  }
  printf '%s\n' "Creating environment with $SYSTEM_PYTHON -m venv..."
  $SYSTEM_PYTHON -m venv "$VENV_DIR"
fi

PYTHON="$(venv_python)"
printf '%s\n' "Installing backend dependencies (first time can take several minutes: PyTorch for YOLO)..."
if command -v uv >/dev/null 2>&1; then
  uv pip install --python "$PYTHON" -r "$BACKEND_DIR/requirements.txt"
else
  "$PYTHON" -m pip install --upgrade pip
  "$PYTHON" -m pip install -r "$BACKEND_DIR/requirements.txt"
fi

if [ ! -f "$ROOT_DIR/.env" ]; then
  cp "$ROOT_DIR/.env.example" "$ROOT_DIR/.env"
  printf '%s\n' "Created .env from .env.example. Add GEMINI_API_KEY to enable the LLM narrative."
else
  printf '%s\n' ".env already exists; leaving it unchanged."
fi

printf '%s\n' "Initialization complete. Start the server with ./run.sh"
