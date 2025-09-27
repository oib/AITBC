#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
export PYTHONPATH="${ROOT_DIR}/src:${ROOT_DIR}/scripts:${PYTHONPATH:-}"

GENESIS_PATH="${ROOT_DIR}/data/devnet/genesis.json"
python "${ROOT_DIR}/scripts/make_genesis.py" --output "${GENESIS_PATH}" --force

echo "[devnet] Generated genesis at ${GENESIS_PATH}"

declare -a CHILD_PIDS=()
cleanup() {
  for pid in "${CHILD_PIDS[@]}"; do
    if kill -0 "$pid" 2>/dev/null; then
      kill "$pid" 2>/dev/null || true
    fi
  done
}
trap cleanup EXIT

python -m aitbc_chain.main &
CHILD_PIDS+=($!)
echo "[devnet] Blockchain node started (PID ${CHILD_PIDS[-1]})"

sleep 1

python -m uvicorn aitbc_chain.app:app --host 127.0.0.1 --port 8080 --log-level info &
CHILD_PIDS+=($!)
echo "[devnet] RPC API serving at http://127.0.0.1:8080" 

python -m uvicorn mock_coordinator:app --host 127.0.0.1 --port 8090 --log-level info &
CHILD_PIDS+=($!)
echo "[devnet] Mock coordinator serving at http://127.0.0.1:8090" 

wait
