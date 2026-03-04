#!/usr/bin/env bash
set -euo pipefail

HEALTH_URL="http://127.0.0.1:18000/v1/health"
MAX_RETRIES=10
RETRY_DELAY=2

for ((i=1; i<=MAX_RETRIES; i++)); do
  if curl -fsS --max-time 5 "$HEALTH_URL" >/dev/null 2>&1; then
    echo "Coordinator proxy healthy: $HEALTH_URL"
    exit 0
  fi
  echo "Attempt $i/$MAX_RETRIES: Coordinator proxy not ready yet, waiting ${RETRY_DELAY}s..."
  sleep $RETRY_DELAY
done

echo "Coordinator proxy health check FAILED: $HEALTH_URL" >&2
exit 1
