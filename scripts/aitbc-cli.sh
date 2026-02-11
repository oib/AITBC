#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CLI_PY="$ROOT_DIR/cli/client.py"

AITBC_URL="${AITBC_URL:-http://127.0.0.1:18000}"
CLIENT_KEY="${CLIENT_KEY:?Set CLIENT_KEY env var}"
ADMIN_KEY="${ADMIN_KEY:?Set ADMIN_KEY env var}"
MINER_KEY="${MINER_KEY:?Set MINER_KEY env var}"

usage() {
  cat <<'EOF'
AITBC CLI wrapper

Usage:
  aitbc-cli.sh submit <type> [--prompt TEXT] [--model NAME] [--ttl SECONDS]
  aitbc-cli.sh status <job_id>
  aitbc-cli.sh browser [--block-limit N] [--tx-limit N] [--receipt-limit N] [--job-id ID]
  aitbc-cli.sh blocks [--limit N]
  aitbc-cli.sh receipts [--limit N] [--job-id ID]
  aitbc-cli.sh cancel <job_id>
  aitbc-cli.sh admin-miners
  aitbc-cli.sh admin-jobs
  aitbc-cli.sh admin-stats
  aitbc-cli.sh admin-cancel-running
  aitbc-cli.sh health

Environment overrides:
  AITBC_URL   (default: http://127.0.0.1:18000)
  CLIENT_KEY  (required)
  ADMIN_KEY   (required)
  MINER_KEY   (required)
EOF
}

if [[ $# -lt 1 ]]; then
  usage
  exit 1
fi

cmd="$1"
shift

case "$cmd" in
  submit)
    python3 "$CLI_PY" --url "$AITBC_URL" --api-key "$CLIENT_KEY" submit "$@"
    ;;
  status)
    python3 "$CLI_PY" --url "$AITBC_URL" --api-key "$CLIENT_KEY" status "$@"
    ;;
  browser)
    python3 "$CLI_PY" --url "$AITBC_URL" --api-key "$CLIENT_KEY" browser "$@"
    ;;
  blocks)
    python3 "$CLI_PY" --url "$AITBC_URL" --api-key "$CLIENT_KEY" blocks "$@"
    ;;
  receipts)
    limit=10
    job_id=""
    while [[ $# -gt 0 ]]; do
      case "$1" in
        --limit)
          limit="$2"
          shift 2
          ;;
        --job-id)
          job_id="$2"
          shift 2
          ;;
        *)
          echo "Unknown option: $1" >&2
          exit 1
          ;;
      esac
    done
    if [[ -n "$job_id" ]]; then
      curl -sS "$AITBC_URL/v1/explorer/receipts?limit=${limit}&job_id=${job_id}"
    else
      curl -sS "$AITBC_URL/v1/explorer/receipts?limit=${limit}"
    fi
    ;;
  cancel)
    if [[ $# -lt 1 ]]; then
      echo "Usage: aitbc-cli.sh cancel <job_id>" >&2
      exit 1
    fi
    job_id="$1"
    curl -sS -X POST -H "X-Api-Key: ${CLIENT_KEY}" "$AITBC_URL/v1/jobs/${job_id}/cancel"
    ;;
  admin-miners)
    curl -sS -H "X-Api-Key: ${ADMIN_KEY}" "$AITBC_URL/v1/admin/miners"
    ;;
  admin-jobs)
    curl -sS -H "X-Api-Key: ${ADMIN_KEY}" "$AITBC_URL/v1/admin/jobs"
    ;;
  admin-stats)
    curl -sS -H "X-Api-Key: ${ADMIN_KEY}" "$AITBC_URL/v1/admin/stats"
    ;;
  admin-cancel-running)
    echo "Fetching running jobs..."
    running_jobs=$(curl -sS -H "X-Api-Key: ${ADMIN_KEY}" "$AITBC_URL/v1/admin/jobs" | jq -r '.[] | select(.state == "running") | .id')
    if [[ -z "$running_jobs" ]]; then
      echo "No running jobs found."
    else
      count=0
      for job_id in $running_jobs; do
        echo "Cancelling job: $job_id"
        curl -sS -X POST -H "X-Api-Key: ${CLIENT_KEY}" "$AITBC_URL/v1/jobs/${job_id}/cancel" > /dev/null
        ((count++))
      done
      echo "Cancelled $count running jobs."
    fi
    ;;
  health)
    curl -sS "$AITBC_URL/v1/health"
    ;;
  help|-h|--help)
    usage
    ;;
  *)
    echo "Unknown command: $cmd" >&2
    usage
    exit 1
    ;;
esac
