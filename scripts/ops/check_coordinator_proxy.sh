#!/usr/bin/env bash
set -euo pipefail

HEALTH_URL="http://127.0.0.1:18000/v1/health"

if curl -fsS --max-time 5 "$HEALTH_URL" >/dev/null; then
  echo "Coordinator proxy healthy: $HEALTH_URL"
  exit 0
fi

echo "Coordinator proxy health check FAILED: $HEALTH_URL" >&2
exit 1
