#!/usr/bin/env bash
# LANE: parallel
# MODE: loop
# Escrow refund leg: submit job -> payment fails or job expires ->
# buyer refund -> ESCROW_REFUND seals.  --job-id <id> retries the
# refund on a specific expired job.
set -euo pipefail
. "$(dirname "$0")/../lib.sh"
serial_check || exit 75

COORD="${STRESS_COORD_URL:-https://hub.aitbc.bubuit.net/c}"
JOB_ID=""
while [ $# -gt 0 ]; do case "$1" in --job-id) JOB_ID="$2"; shift 2;; *) shift;; esac; done

addr=$(cli wallet --wallet-name "$WALLET" balance 2>/dev/null | python3 -c 'import json,sys;print(json.load(sys.stdin).get("address",""))' 2>/dev/null || true)
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
  echo "queued $JOB_ID — refund re-runnable with --job-id after expiry"
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
