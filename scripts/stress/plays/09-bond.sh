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
req="${STRESS_BOND_REQUIRED:-$AMOUNT}"
req_dec=$(python3 -c "print(format(int('$req')/36000000,'.18f').rstrip('0').rstrip('.'))")
out=$("$AITBC_BIN" --output=json bond create --provider-id "$pid" --amount "$dec" --required-amount "$req_dec" 2>&1) || fail bond "bond create failed: $out"
# pending->active: create under required_amount leaves the bond pending.
# The coordinator can CLAMP required_amount to its configured minimum
# (default_bond_min_amount, observed 1.0 AIT), and the top-up route is an
# UPSERT (bond.amount := value, not +=) — so the value must be the stored
# required_amount itself, read back from the record.
topup=$("$AITBC_BIN" --output=json bond status --provider-id "$pid" 2>/dev/null | python3 -c '
import json,sys
from decimal import Decimal
d=json.load(sys.stdin)
try:
    req=Decimal(str(d.get("required_amount","0")))
    amt=Decimal(str(d.get("amount","0")))
    print(req if amt<req else 0)
except Exception: print(0)' 2>/dev/null || echo 0)
[ "$topup" != "0" ] && out=$("$AITBC_BIN" --output=json bond top-up --provider-id "$pid" --amount "$topup" 2>&1) || true
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
