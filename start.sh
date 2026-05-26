#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

PORT="${API_PORT:-8890}"

echo "Building IxPort container..."
docker compose build ixport

echo ""
echo "Starting IxPort on http://0.0.0.0:${PORT}"
echo "  Dashboard  → http://localhost:${PORT}"
echo "  Swagger UI → http://localhost:${PORT}/docs"
echo ""

exec docker compose up ixport
