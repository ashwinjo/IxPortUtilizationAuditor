#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

VENV="$SCRIPT_DIR/.venv"
PYTHON="$VENV/bin/python"
PIP="$VENV/bin/pip"

# Create venv if missing
if [ ! -f "$PYTHON" ]; then
  echo "Creating virtual environment..."
  python3 -m venv "$VENV"
fi

# Install / sync dependencies
echo "Installing dependencies..."
"$PIP" install -q -r requirements.txt

# Load .env if present
if [ -f "$SCRIPT_DIR/.env" ]; then
  set -a
  # shellcheck disable=SC1091
  source "$SCRIPT_DIR/.env"
  set +a
fi

HOST="${API_HOST:-0.0.0.0}"
PORT="${API_PORT:-8890}"

echo "Starting IxPort API on http://${HOST}:${PORT}"
echo "  Swagger UI → http://localhost:${PORT}/docs"
echo ""

exec "$VENV/bin/uvicorn" api.main:app --host "$HOST" --port "$PORT"
