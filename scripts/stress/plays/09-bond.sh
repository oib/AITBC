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
# Bond emissions land as BOND_LOCK rows; confirm within the seal window.
h0=$(height); deadline=$(( h0 + 40 ))
for i in $(seq 1 60); do
  hit=$(rpc_get "/rpc/transactions?tx_type=BOND_LOCK&limit=20" 2>/dev/null | python3 -c "
import json,sys
rows=json.load(sys.stdin)
rows=rows if isinstance(rows,list) else rows.get('transactions',rows.get('items',[]))
print(1 if any('$pid' in json.dumps(r) for r in rows) else '')" 2>/dev/null || true)
  [ "$hit" = "1" ] && { echo "BOND_LOCK for $pid visible at height $(height)"; ok "$pid"; exit 0; }
  [ "$(height)" -gt "$deadline" ] && fail seal "BOND_LOCK for $pid not sealed by $deadline"
  sleep 10
done
fail seal "BOND_LOCK for $pid seal wait exhausted"
