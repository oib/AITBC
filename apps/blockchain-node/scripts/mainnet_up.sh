#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"
VENV_PYTHON="$ROOT_DIR/.venv/bin/python"
if [ ! -x "$VENV_PYTHON" ]; then
  echo "[mainnet] Virtualenv not found at $VENV_PYTHON. Please create it: python -m venv .venv && .venv/bin/pip install -r requirements.txt"
  exit 1
fi
export PYTHONPATH="${ROOT_DIR}/src:${ROOT_DIR}/scripts:${PYTHONPATH:-}"

# Load production environment
if [ -f ".env.production" ]; then
  set -a
  source .env.production
  set +a
fi

CHAIN_ID="${chain_id:-ait-mainnet}"
export chain_id="$CHAIN_ID"
export supported_chains="${supported_chains:-$CHAIN_ID}"

# Proposer ID: should be the genesis wallet address (from keystore/aitbc1genesis.json)
# If not set in env, derive from keystore
if [ -z "${proposer_id:-}" ]; then
  if [ -f "keystore/aitbc1genesis.json" ]; then
    PROPOSER_ID=$(grep -o '"address": "[^"]*"' keystore/aitbc1genesis.json | cut -d'"' -f4)
    if [ -n "$PROPOSER_ID" ]; then
      export proposer_id="$PROPOSER_ID"
    else
      echo "[mainnet] ERROR: Could not derive proposer_id from keystore. Set proposer_id in .env.production"
      exit 1
    fi
  else
    echo "[mainnet] ERROR: keystore/aitbc1genesis.json not found. Run setup_production.py first."
    exit 1
  fi
else
  export proposer_id
fi

# Ensure mint_per_unit=0 for fixed supply
export mint_per_unit=0
export coordinator_ratio=0.05
export db_path="./data/${CHAIN_ID}/chain.db"
export trusted_proposers="${trusted_proposers:-$proposer_id}"
export gossip_backend="${gossip_backend:-memory}"

# Optional: load proposer private key from keystore if block signing is implemented
# export PROPOSER_KEY="..."  # Not yet used; future feature

echo "[mainnet] Starting blockchain node for ${CHAIN_ID}"
echo "  proposer_id: $proposer_id"
echo "  db_path: $db_path"
echo "  gossip: $gossip_backend"

# Check that genesis exists
GENESIS_PATH="data/${CHAIN_ID}/genesis.json"
if [ ! -f "$GENESIS_PATH" ]; then
  echo "[mainnet] Genesis not found at $GENESIS_PATH. Run setup_production.py first."
  exit 1
fi

declare -a CHILD_PIDS=()
cleanup() {
  for pid in "${CHILD_PIDS[@]}"; do
    if kill -0 "$pid" 2>/dev/null; then
      kill "$pid" 2>/dev/null || true
    fi
  done
}
trap cleanup EXIT

"$VENV_PYTHON" -m aitbc_chain.main &
CHILD_PIDS+=($!)
echo "[mainnet] Blockchain node started (PID ${CHILD_PIDS[-1]})"

sleep 2

"$VENV_PYTHON" -m uvicorn aitbc_chain.app:app --host 127.0.0.1 --port 8026 --log-level info &
CHILD_PIDS+=($!)
echo "[mainnet] RPC API serving at http://127.0.0.1:8026"

wait
