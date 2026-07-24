#!/usr/bin/env bash
# Start a minimal local AITBC stack for builders (v0.16.1 §B4).
# ponytail: This is a convenience wrapper; production deployments should use
# systemd or a container orchestrator.

set -euo pipefail

REPO_DIR="${REPO_DIR:-/opt/aitbc}"
COORDINATOR_PORT="${COORDINATOR_PORT:-8000}"

cd "$REPO_DIR"

if [[ ! -d venv ]]; then
  echo "Virtual environment not found at $REPO_DIR/venv"
  exit 1
fi

# Source builder .env if present
if [[ -f .env ]]; then
  # shellcheck source=/dev/null
  source .env
fi

# Start coordinator API in the background
echo "Starting coordinator-api on port $COORDINATOR_PORT..."
PYTHONPATH="apps/coordinator-api/src:$REPO_DIR" \
  DATABASE_URL="${DATABASE_URL:-sqlite:///$REPO_DIR/data/coordinator_local.db}" \
  JWT_SECRET="${JWT_SECRET:-local-dev-secret-must-be-32-chars-long}" \
  ./venv/bin/uvicorn coordinator_api.main:app \
  --host 0.0.0.0 \
  --port "$COORDINATOR_PORT" \
  --reload &
COORDINATOR_PID=$!

# Run migrations
PYTHONPATH="apps/coordinator-api/src:$REPO_DIR" \
  DATABASE_URL="${DATABASE_URL:-sqlite:///$REPO_DIR/data/coordinator_local.db}" \
  ./venv/bin/alembic -c apps/coordinator-api/alembic.ini upgrade head

# Print instructions
echo "Coordinator API running at http://localhost:$COORDINATOR_PORT"
echo "PID: $COORDINATOR_PID"
echo "Run 'kill $COORDINATOR_PID' to stop."
