#!/usr/bin/env bash
# LANE: parallel
# MODE: loop
# AI_JOB lifecycle: submit (buyer) -> provider executes -> accept ->
# ESCROW_RELEASE -> RECEIPT_CLAIM (honest emitter, post-#687).
# Iteration submits a real paid job; the ESCROW_LOCK seals on the next
# proposer slot.  When the provider completes fast (llama3.2:3b ~seconds)
# the same run drives the accept leg.  --job-id <id> skips submit and
# only drives accept.
set -euo pipefail
. "$(dirname "$0")/../lib.sh"
serial_check || exit 75

PROVIDER_ADDR="${STRESS_PROVIDER_ADDR:-0x4A5b3bf95aa06072c568cfcb7392b4e86608b5d2}"
MODEL="${STRESS_MODEL:-llama3.2:3b}"
PAYMENT="${STRESS_PAYMENT:-0.01}"
COORD="${STRESS_COORD_URL:-https://hub.aitbc.bubuit.net/c}"
JOB_ID=""
while [ $# -gt 0 ]; do case "$1" in --job-id) JOB_ID="$2"; shift 2;; *) shift;; esac; done

addr=$(cli wallet --wallet-name "$WALLET" balance 2>/dev/null | python3 -c 'import json,sys;print(json.load(sys.stdin).get("address",""))' 2>/dev/null || true)
[ -n "$addr" ] || fail resolve "no address for wallet $WALLET"

if [ -z "$JOB_ID" ]; then
  out=$(cli ai submit --prompt "stress-1 $(date +%s)" --model "$MODEL" \
        --provider-address "$PROVIDER_ADDR" --buyer-address "$addr" \
        --payment "$PAYMENT" --wallet "$WALLET" --format json 2>&1) \
      || fail submit "ai submit failed: $out"
  JOB_ID=$(printf '%s' "$out" | python3 -c 'import re,sys
m=re.search(r"[0-9a-f]{32}", sys.stdin.read())
print(m.group(0) if m else "")')
  [ -n "$JOB_ID" ] || fail submit "no job id in submit output"
fi

# ESCROW_LOCK leg: poll the newest lock txs for this job's payload.
lock_tx=""
for i in $(seq 1 40); do
  lock_tx=$(rpc_get "/rpc/transactions?transaction_type=ESCROW_LOCK&limit=5" 2>/dev/null | python3 -c 'import json,sys
d=json.load(sys.stdin)
txs=d.get("transactions",d if isinstance(d,list) else [])
print(next((t["tx_hash"] for t in txs if "'"$JOB_ID"'" in json.dumps(t.get("payload",{}))), ""))' 2>/dev/null || true)
  [ -n "$lock_tx" ] && break
  sleep 10
done
[ -n "$lock_tx" ] || fail lock "no ESCROW_LOCK sealed carrying job $JOB_ID"

# Accept leg when the job already completed (provider fast-path).
state=$(curl -sf --max-time 15 "$COORD/v1/jobs/$JOB_ID" 2>/dev/null | python3 -c 'import json,sys;print(json.load(sys.stdin).get("state",""))' 2>/dev/null || true)
if [ "$state" = "COMPLETED" ]; then
  acc=$(cli ai accept --job-id "$JOB_ID" --format json 2>&1) || fail accept "ai accept failed: $acc"
  echo "accepted $JOB_ID — release/claim seal on next slots"
fi
ok "$lock_tx"
