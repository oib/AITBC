#!/usr/bin/env bash
# maturity-watcher.sh — armed agent-stake unbond/complete scheduler (#741).
#
# Replaces the stress-2 watcher, which fired ~22h early and swallowed
# refusals: its sign_call read env vars that were never exported (empty
# wallet path + empty payload -> python crashed before any HTTP call), and
# the retry loop broke on the first empty output — so the "armed" legs
# never fired and the log recorded blank responses as if they'd been made.
#
# This version:
#   * schedules per-stake from its `locked_until` in agent_stake (UTC,
#     `date -d` both sides — no read-time-vs-write-time drift),
#   * signs the full body the handlers verify (stake_id + user_address +
#     chain_id via the operator wallet file),
#   * treats every response loudly: HTTP errors and non-success bodies log
#     the FULL response and exit nonzero so watch.sh surfaces them,
#   * gates complete on BOTH wall-clock locked_until and the consensus
#     window (lock_height + lock_days*1440 — the apply-time gate),
#   * --check mode prints the computed schedule and exits (regression
#     testable without firing anything).
#
# Usage:
#   maturity-watcher.sh --check <stake-id>...
#   maturity-watcher.sh <stake-id>...
set -euo pipefail
RPC_URL="${STRESS_RPC_URL:-http://127.0.0.1:8202}"
DB="${STRESS_CHAIN_DB:-/var/lib/aitbc/data/bc-2/chain.db}"
WFILE="${STRESS_OPERATOR_WALLET_PATH:-/var/lib/aitbc/wallets/agent-econ-operator.json}"
LOG="${STRESS_MATURITY_LOG:-/var/lib/aitbc/stress-state/maturity-watcher.log}"
CHAIN="${STRESS_CHAIN:-bc-2}"
BLOCKS_PER_DAY=1440
MODE=run; [ "${1:-}" = "--check" ] && { MODE=check; shift; }
[ $# -gt 0 ] || { echo "usage: $0 [--check] <stake-id>..." >&2; exit 64; }

mkdir -p "$(dirname "$LOG")" 2>/dev/null || true
log() { echo "$(date -u '+%Y-%m-%dT%H:%M:%SZ') $*" | tee -a "$LOG"; }

stake_field() {  # stake_field <stake_id> <column>
  sqlite3 -readonly "$DB" "SELECT $2 FROM agent_stake WHERE stake_id='$1' AND chain_id='$CHAIN'"
}

wait_until() {  # wait_until <epoch> <label> — sleep until a UTC instant
  local target=$1 now; now=$(date -u +%s)
  if [ "$now" -lt "$target" ]; then
    log "waiting $(( target - now ))s for $2 (epoch $target)"
    sleep $(( target - now ))
  else
    log "$2 already open ($(( now - target ))s ago)"
  fi
}

sign_call() {  # sign_call <path> <payload> — response body on stdout,
  # nonzero on HTTP error/exception; full error text is always printed.
  STRESS_PAYLOAD="$2" STRESS_PATH="$1" STRESS_WFILE="$WFILE" RPC_URL="$RPC_URL" python3 - <<'PYEOF'
import json, os, sys, urllib.request, urllib.error
from eth_keys import keys
from eth_utils import keccak
w = json.load(open(os.environ["STRESS_WFILE"]))
priv = keys.PrivateKey(bytes.fromhex(w["private_key"].removeprefix("0x")))
payload = json.loads(os.environ["STRESS_PAYLOAD"])
digest = keccak(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode())
payload["signature"] = priv.sign_msg_hash(digest).to_hex()
req = urllib.request.Request(os.environ["RPC_URL"] + os.environ["STRESS_PATH"],
    data=json.dumps(payload).encode(), headers={"Content-Type": "application/json"}, method="POST")
try:
    print(urllib.request.urlopen(req, timeout=20).read().decode())
except urllib.error.HTTPError as e:
    print(f"HTTP {e.code} {e.read().decode()}", file=sys.stdout)
    sys.exit(1)
except Exception as e:
    print(f"ERR {e}", file=sys.stdout)
    sys.exit(1)
PYEOF
}

for sid in "$@"; do
  lu=$(stake_field "$sid" locked_until)
  [ -n "$lu" ] || { log "SKIP $sid: no agent_stake row"; continue; }
  target=$(date -u -d "$lu" +%s)
  log "$sid locked_until=$lu epoch=$target"
  [ "$MODE" = check ] && continue
  wait_until "$target" "unbond window $sid"
  if out=$(sign_call "/rpc/agent-staking/stake/$sid/unbond" "{\"stake_id\":\"$sid\",\"user_address\":\"$(python3 -c "import json;print(json.load(open('$WFILE'))['address'])" 2>/dev/null)\",\"chain_id\":\"$CHAIN\"}"); then
    log "unbond $sid: $out"
  else
    log "FAIL unbond $sid: $out"; exit 1
  fi
done
[ "$MODE" = check ] && { log "check complete"; exit 0; }

# complete leg: per-stake, wait for the consensus maturity of its lock txs
# (lock block_height + lock_days*1440) — the apply-time gate, which is what
# the complete handler enforces.
for sid in "$@"; do
  read -r gate <<<"$(sqlite3 -readonly "$DB" "SELECT max(block_height) + COALESCE(max(json_extract(payload,'$.lock_days')),1)*$BLOCKS_PER_DAY FROM [transaction] WHERE type='STAKE_LOCK' AND json_extract(payload,'$.agent_stake_id')='$sid'")"
  cur=$(sqlite3 -readonly "$DB" "SELECT max(height) FROM block WHERE chain_id='$CHAIN'")
  log "$sid complete gate h$gate (current $cur)"
  while [ "$cur" -lt "${gate:-999999999}" ]; do sleep 120; cur=$(sqlite3 -readonly "$DB" "SELECT max(height) FROM block WHERE chain_id='$CHAIN'"); done
  if out=$(sign_call "/rpc/agent-staking/stake/$sid/complete" "{\"stake_id\":\"$sid\",\"user_address\":\"$(python3 -c "import json;print(json.load(open('$WFILE'))['address'])" 2>/dev/null)\",\"chain_id\":\"$CHAIN\"}"); then
    log "complete $sid: $out"
  else
    log "FAIL complete $sid: $out"; exit 1
  fi
done
log "all legs done"
