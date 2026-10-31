#!/usr/bin/env bash
# LANE: parallel
# MODE: loop
# Escrow refund leg: submit job -> payment fails or job expires ->
# buyer refund -> ESCROW_REFUND seals.  --job-id <id> retries the
# refund on a specific expired job.
#
# Adversarial refund timing (stress-3): set STRESS_REFUND_OFFSET=0|1|2 —
# the play submits a dead-provider job, waits for its ESCROW_LOCK seal,
# then attempts `ai refund` at lock_height+OFFSET. Refusal is the
# expected outcome (expected_refusal row, exit 0); an admitted refund
# that early is the #703-class defect and fails the play.
set -euo pipefail
. "$(dirname "$0")/../lib.sh"
serial_check || exit 75

COORD="${STRESS_COORD_URL:-https://hub.aitbc.bubuit.net/c}"
OFFSET="${STRESS_REFUND_OFFSET:-}"
JOB_ID=""
while [ $# -gt 0 ]; do case "$1" in --job-id) JOB_ID="$2"; shift 2;; *) shift;; esac; done

addr=$(wallet_addr || true)
[ -n "$addr" ] || fail resolve "no address for wallet $WALLET"

if [ -z "$JOB_ID" ]; then
  # A job to an unreachable provider locks escrow but never executes;
  # after TTL expiry the refund path opens.
  out=$(cli ai submit --prompt "stress-1 refund leg $(date +%s)" --model "${STRESS_MODEL:-llama3.2:3b}" \
        --provider-address "0xdeaddeaddeaddeaddeaddeaddeaddeaddeaddead" \
        --buyer-address "$addr" --payment "${STRESS_PAYMENT:-0.01}" --wallet "$WALLET" --format json 2>&1) \
      || fail submit "ai submit failed: $out"
  JOB_ID=$(printf '%s' "$out" | python3 -c 'import re,sys
m=re.search(r"[0-9a-f]{32}", sys.stdin.read())
print(m.group(0) if m else "")')
  [ -n "$JOB_ID" ] || fail submit "no job id"
  if [ -z "$OFFSET" ]; then
    echo "queued $JOB_ID — refund re-runnable with --job-id after expiry"
    ok ""; exit 0
  fi
fi

# Adversarial leg: wait for this job's ESCROW_LOCK seal, then refund at
# lock_height + OFFSET.
if [ -n "$OFFSET" ]; then
  lock_h=""
  for i in $(seq 1 "${STRESS_LOCK_WAIT:-90}"); do
    row=$(rpc_get "/rpc/transactions?transaction_type=ESCROW_LOCK&limit=5" 2>/dev/null | python3 -c 'import json,sys
d=json.load(sys.stdin)
txs=d.get("transactions",d if isinstance(d,list) else [])
m=next((t for t in txs if "'"$JOB_ID"'" in json.dumps(t.get("payload",{}))), None)
print(m["block_height"] if m else "")' 2>/dev/null || true)
    [ -n "$row" ] && { lock_h="$row"; break; }
    sleep 10
  done
  [ -n "$lock_h" ] || fail lock "no ESCROW_LOCK sealed carrying job $JOB_ID"
  target=$(( lock_h + OFFSET ))
  echo "lock sealed h$lock_h — refund attempt at h$target (offset $OFFSET)"
  for i in $(seq 1 60); do
    [ "$(height)" -ge "$target" ] && break; sleep 10
  done
  out=$(cli ai refund --job-id "$JOB_ID" --reason "stress-3 adversarial refund t+$OFFSET" --format json 2>&1) && {
    tx=$(printf '%s' "$out" | python3 -c 'import re,sys
m=re.search(r"0x[0-9a-fA-F]{64}", sys.stdin.read())
print(m.group(0) if m else "")')
    fail refund "premature ESCROW_REFUND admitted at lock+$OFFSET (job $JOB_ID tx ${tx:-none})" "${tx:-null}"
  }
  printf '%s' "$out" | grep -qiE "awaiting|expire|not.*eligible|operator|delivered|refund" \
    || fail refund "adversarial refund failed unexpectedly: $out"
  jsonl "$RUN_LOG" "{\"ts\":\"$(now)\",\"script\":\"${0##*/}\",\"host\":\"$HOST\",\"status\":\"expected_refusal\",\"reason\":\"refund refused at lock+$OFFSET\",\"job\":\"$JOB_ID\",\"lock_height\":$lock_h}"
  echo "refund refused at lock+$OFFSET as expected"
  ok ""; exit 0
fi

out=$(cli ai refund --job-id "$JOB_ID" --reason "stress-1 escrow refund" --format json 2>&1) || {
  printf '%s' "$out" | grep -qiE "awaiting|expire|not.*eligible|operator|delivered" \
    && skip_mature "refund refused: $out" || fail refund "ai refund failed: $out"
}
ref_tx=$(printf '%s' "$out" | python3 -c 'import re,sys
m=re.search(r"0x[0-9a-fA-F]{64}", sys.stdin.read())
print(m.group(0) if m else "")')
[ -n "$ref_tx" ] && wait_seal "$ref_tx" >/dev/null || true
ok "${ref_tx:-}"
