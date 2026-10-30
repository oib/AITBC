#!/usr/bin/env bash
# LANE: parallel
# MODE: loop
# TRANSFER to self — cheapest sealed record. --amount is UNITS (converted
# to AIT-decimal for the CLI: 1 AIT = 36,000,000 units).
set -euo pipefail
. "$(dirname "$0")/../lib.sh"
serial_check || exit 75

addr=$("$AITBC_BIN" --output=json wallet --wallet-name "$WALLET" balance 2>/dev/null | python3 -c 'import json,sys;print(json.load(sys.stdin).get("address",""))' 2>/dev/null || true)
[ -n "$addr" ] || fail resolve "no address for wallet $WALLET"
spend_guard "$AMOUNT" || true
dec=$(python3 -c "print('{:.18f}'.rstrip('0').rstrip('.') or '0'.format and format(int('$AMOUNT')/36000000,'.18f').rstrip('0').rstrip('.'))")
out=$(cli transactions send --from "$WALLET" --to "$addr" --amount "$dec" 2>&1) || fail send "transactions send failed: $out"
tx=$(printf '%s' "$out" | python3 -c 'import json,sys,re
try:
  d=json.loads(sys.stdin.read()); print(d.get("tx_hash",""))
except Exception:
  m=re.search(r"0x[0-9a-fA-F]{64}", sys.stdin.read()); print(m.group(0) if m else "")' <<<"$out")
[ -n "$tx" ] || fail send "no tx_hash in response"
bh=$(wait_seal "$tx") || exit $?
echo "sealed $tx at height $bh"
ok "$tx"
