#!/bin/bash
# MyPy pre-commit hook for clean apps

set -e

cd /opt/aitbc

OUTPUT=$(./venv/bin/python -m mypy \
  --show-error-codes \
  --ignore-missing-imports \
  apps/coordinator-api \
  apps/blockchain-node \
  apps/pool-hub \
  apps/edge \
  apps/wallet \
  apps/agent-coordinator \
  apps/agent-management \
  apps/agent \
  apps/marketplace \
  apps/api-gateway \
  apps/blockchain-event-bridge \
  apps/blockchain-explorer \
  2>&1 || true)

# Filter only errors and warnings, exclude summary lines
ERRORS=$(echo "$OUTPUT" | grep -E "(error:|warning:)" || true)

if [ -n "$ERRORS" ]; then
    echo "$ERRORS" | head -20
    exit 1
fi

echo "✅ MyPy: All clean apps pass"
exit 0
