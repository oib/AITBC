#!/usr/bin/env bash
# LANE: parallel
# MODE: loop
# Bond slash leg — create -> lock -> slash via the coordinator admin
# endpoint (`aitbc bond slash`). Refs #740 (stress-2 carry-over).
#
# SCOPE NOTE: the admin slash route flips coordinator-side status to
# LIQUIDATED — the honest confirmation for this surface, same convention as
# plays 09/11. The on-chain BOND_SLASH transaction is emitted only by
# BondSlashingService on a bonded-job failure/dispute/downtime path (no
# direct HTTP trigger); that full leg needs a job lifecycle against a
# bonded provider and is out of scope for this play — flagged to the round
# plan as a gap.
set -euo pipefail
. "$(dirname "$0")/../lib.sh"
serial_check || exit 75

spend_guard "$AMOUNT" || true
pid="stress-slash-${HOST}-$(date +%s)"
dec=$(python3 -c "print(format(int('$AMOUNT')/36000000,'.18f').rstrip('0').rstrip('.'))")
# coordinator JWT — idempotent login
echo x | "$AITBC_BIN" auth login --wallet "$WALLET" --password-stdin >/dev/null 2>&1 || true
req="${STRESS_BOND_REQUIRED:-$AMOUNT}"
req_dec=$(python3 -c "print(format(int('$req')/36000000,'.18f').rstrip('0').rstrip('.'))")
# create + fund to required so the bond can go active (same shape as 09)
out=$("$AITBC_BIN" --output=json bond create --provider-id "$pid" --amount "$dec" --required-amount "$req_dec" 2>&1) || fail bond "bond create failed: $out"
out=$("$AITBC_BIN" --output=json bond top-up --provider-id "$pid" --amount "$req_dec" 2>&1) || true
# lock leg — only LOCKED/ACTIVE bonds are slash candidates
out=$("$AITBC_BIN" --output=json bond lock --provider-id "$pid" 2>&1) || fail lock "bond lock failed: $out"
# slash leg — admin route -> LIQUIDATED
out=$("$AITBC_BIN" --output=json bond slash --provider-id "$pid" --reason "stress-3 slash leg" 2>&1) || fail slash "bond slash failed: $out"
for i in $(seq 1 24); do
  st=$("$AITBC_BIN" --output=json bond status --provider-id "$pid" 2>/dev/null | python3 -c 'import json,sys;print(json.load(sys.stdin).get("status",""))' 2>/dev/null || true)
  [ "$st" = "liquidated" ] && { echo "bond $pid slashed->liquidated"; ok "$pid"; exit 0; }
  [ -z "$st" ] && fail status "bond status unreadable for $pid"
  sleep 10
done
fail seal "bond $pid stayed ${st:-?} after slash (4min)"
