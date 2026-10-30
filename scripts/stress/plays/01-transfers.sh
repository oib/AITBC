#!/usr/bin/env bash
# LANE: parallel
# MODE: loop
# TRANSFER to self — cheapest sealed record, proves wallet+rpc+seal path.
set -euo pipefail
. "$(dirname "$0")/../lib.sh"
serial_check || exit 75

addr=$(cli wallet --wallet-name "$WALLET" balance 2>/dev/null | python3 -c 'import json,sys;print(json.load(sys.stdin).get("address",""))' 2>/dev/null || true)
[ -n "$addr" ] || fail resolve "no address for wallet $WALLET"
spend_guard "$AMOUNT" || true
out=$(cli transactions send --from "$WALLET" --to "$addr" --amount "$AMOUNT" 2>&1) || fail send "transactions send failed: $out"
tx=$(printf '%s' "$out" | python3 -c 'import json,sys,re
try:
  d=json.loads(sys.stdin.read()); print(d.get("tx_hash",""))
except Exception:
  m=re.search(r"0x[0-9a-fA-F]{64}", sys.stdin.read()); print(m.group(0) if m else "")' <<<"$out")
[ -n "$tx" ] || fail send "no tx_hash in response"
bh=$(wait_seal "$tx") || exit $?
echo "sealed $tx at height $bh"
ok "$tx"
