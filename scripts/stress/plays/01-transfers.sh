#!/usr/bin/env bash
# LANE: parallel
# MODE: loop
# TRANSFER to self — cheapest sealed record, proves wallet+rpc+seal path.
set -euo pipefail
. "$(dirname "$0")/../lib.sh"
serial_check || exit 75

spend_guard "$AMOUNT" 2>/dev/null || true
addr=$(cli wallet address "$WALLET" 2>/dev/null | python3 -c 'import json,sys; d=json.load(sys.stdin); print(d.get("address") or d.get("wallet",""))' 2>/dev/null)
[ -n "$addr" ] || fail resolve "could not resolve address for wallet $WALLET"
out=$(cli transactions send --to "$addr" --amount "$AMOUNT" 2>&1) || fail send "transactions send failed: $out"
tx=$(printf '%s' "$out" | python3 -c 'import json,sys,re
try: print(json.load(sys.stdin).get("tx_hash",""))
except Exception:
  m=re.search(r"0x[0-9a-fA-F]{64}", sys.stdin.read()); print(m.group(0) if m else "")')
[ -n "$tx" ] || fail send "no tx_hash in response: $out"
bh=$(wait_seal "$tx") || exit $?
echo "sealed $tx at height $bh"
ok "$tx"
