#!/usr/bin/env bash
# LANE: parallel
# MODE: loop
# Bond release leg — create a bond then release it; BOND_RELEASE is the
# committed-table record. Requires the coordinator JWT (auth login).
set -euo pipefail
. "$(dirname "$0")/../lib.sh"
serial_check || exit 75

spend_guard "$AMOUNT" || true
pid="stress-rel-${HOST}-$(date +%s)"
dec=$(python3 -c "print(format(int('$AMOUNT')/36000000,'.18f').rstrip('0').rstrip('.'))")
# coordinator JWT — idempotent login
echo x | "$AITBC_BIN" auth login --wallet "$WALLET" --password-stdin >/dev/null 2>&1 || true
# create leg — BOND_LOCK
out=$("$AITBC_BIN" --output=json bond create --provider-id "$pid" --amount "$dec" 2>&1) || fail bond "bond create failed: $out"
# lock leg — release only un-locks LOCKED bonds
out=$("$AITBC_BIN" --output=json bond lock --provider-id "$pid" 2>&1) || fail lock "bond lock failed: $out"
# release leg — BOND_RELEASE
out=$("$AITBC_BIN" --output=json bond release --provider-id "$pid" 2>&1) || fail release "bond release failed: $out"
# bond release transitions the coordinator record back to active —
# status is the honest signal for this coordinator-state surface.
for i in $(seq 1 24); do
  st=$("$AITBC_BIN" --output=json bond status --provider-id "$pid" 2>/dev/null | python3 -c 'import json,sys;print(json.load(sys.stdin).get("status",""))' 2>/dev/null || true)
  [ "$st" = "active" ] && { echo "bond $pid released->active"; ok "$pid"; exit 0; }
  [ -z "$st" ] && fail status "bond status unreadable for $pid"
  sleep 10
done
fail seal "bond $pid stayed ${st:-?} after 4min"
