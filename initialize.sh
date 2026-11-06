#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_DIR="$ROOT_DIR/backend"
VENV_DIR="$BACKEND_DIR/.venv"

if ! command -v uv >/dev/null 2>&1; then
  printf '%s\n' "uv is required. Install it from https://docs.astral.sh/uv/ and run this script again."
  exit 1
fi

printf '%s\n' "Creating or updating the backend uv environment..."
uv venv "$VENV_DIR"
uv pip install --python "$VENV_DIR/bin/python" -r "$BACKEND_DIR/requirements.txt"

if [ ! -f "$ROOT_DIR/.env" ]; then
  cp "$ROOT_DIR/.env.example" "$ROOT_DIR/.env"
  printf '%s\n' "Created .env from .env.example. Add your API key before using Gemini."
else
  printf '%s\n' ".env already exists; leaving it unchanged."
fi

printf '%s\n' "Initialization complete. Start the backend with ./run.sh"
