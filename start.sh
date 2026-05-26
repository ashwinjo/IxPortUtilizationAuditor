#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

PORT="${API_PORT:-8890}"

# ── Ensure Docker is running ──────────────────────────────────────────
if ! docker info &>/dev/null; then
  echo "Docker not running — starting Docker Desktop..."
  open -a Docker

  echo -n "Waiting for Docker"
  for i in $(seq 1 30); do
    sleep 2
    if docker info &>/dev/null; then
      echo " ready."
      break
    fi
    echo -n "."
    if [ "$i" -eq 30 ]; then
      echo ""
      echo "ERROR: Docker did not start after 60 seconds. Start Docker Desktop manually and retry."
      exit 1
    fi
  done
fi

echo "Building IxPort container..."
docker compose build ixport

echo ""
echo "Starting IxPort on http://0.0.0.0:${PORT}"
echo "  Dashboard  → http://localhost:${PORT}"
echo "  Swagger UI → http://localhost:${PORT}/docs"
echo ""

exec docker compose up ixport
