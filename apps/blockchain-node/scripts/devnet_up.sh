#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"
export PYTHONPATH="${ROOT_DIR}/src:${ROOT_DIR}/scripts:${PYTHONPATH:-}"

GENESIS_PATH="data/devnet/genesis.json"
ALLOCATIONS_PATH="data/devnet/allocations.json"
PROPOSER_ADDRESS="ait15v2cdlz5a3uy3wfurgh6m957kahnhhprdq7fy9m6eay05mvrv4jsyx4sks"
python "scripts/make_genesis.py" \
  --output "$GENESIS_PATH" \
  --force \
  --allocations "$ALLOCATIONS_PATH" \
  --authorities "$PROPOSER_ADDRESS" \
  --chain-id "ait-devnet"

echo "[devnet] Generated genesis at ${GENESIS_PATH}"

# Set environment for devnet
export chain_id="ait-devnet"
export supported_chains="ait-devnet"
export proposer_id="${PROPOSER_ADDRESS}"
export mint_per_unit=0
export coordinator_ratio=0.05
export db_path="./data/${chain_id}/chain.db"
export trusted_proposers="${PROPOSER_ADDRESS}"
export gossip_backend="memory"

# Optional: if you have a proposer private key for block signing (future), set PROPOSER_KEY
# export PROPOSER_KEY="..."

echo "[devnet] Environment configured: chain_id=${chain_id}, proposer_id=${proposer_id}"

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

python -m uvicorn aitbc_chain.app:app --host 127.0.0.1 --port 8026 --log-level info &
CHILD_PIDS+=($!)
echo "[devnet] RPC API serving at http://127.0.0.1:8026"

# Optional: mock coordinator for devnet only
# python -m uvicorn mock_coordinator:app --host 127.0.0.1 --port 8090 --log-level info &
# CHILD_PIDS+=($!)
# echo "[devnet] Mock coordinator serving at http://127.0.0.1:8090"

wait
