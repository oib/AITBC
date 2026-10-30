#!/usr/bin/env bash
# LANE: parallel
# MODE: loop
set -euo pipefail
. "$(dirname "$0")/../lib.sh"
serial_check || exit 75

spend_guard "$AMOUNT" || true
pid="stress-${HOST}-$(date +%s)"
dec=$(python3 -c "print(format(int('$AMOUNT')/36000000,'.18f').rstrip('0').rstrip('.'))")
# bond needs a stored coordinator JWT — auth login once (idempotent)
echo x | "$AITBC_BIN" auth login --wallet "$WALLET" --password-stdin >/dev/null 2>&1 || true
out=$("$AITBC_BIN" --output=json bond create --provider-id "$pid" --amount "$dec" 2>&1) || fail bond "bond create failed: $out"
# pending->active: create under required_amount leaves the bond pending;
# top-up to meet it transitions to active.
out=$("$AITBC_BIN" --output=json bond top-up --provider-id "$pid" --amount "$dec" 2>&1) || true
# Bond is coordinator-state — verify the record transitions pending->active
# (the BOND_LOCK chain emission may not fire per-create; bond status is the
# honest confirmation signal for this surface).
for i in $(seq 1 24); do
  st=$("$AITBC_BIN" --output=json bond status --provider-id "$pid" 2>/dev/null | python3 -c 'import json,sys;print(json.load(sys.stdin).get("status",""))' 2>/dev/null || true)
  [ "$st" = "active" ] && { echo "bond $pid active"; ok "$pid"; exit 0; }
  [ "$st" = "locked" ] && { echo "bond $pid locked"; ok "$pid"; exit 0; }
  [ -z "$st" ] && fail status "bond status unreadable for $pid"
  sleep 10
done
fail seal "bond $pid stayed ${st:-?} after 4min"
