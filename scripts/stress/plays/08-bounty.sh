#!/usr/bin/env bash
# LANE: parallel
# MODE: loop
# Bounty deploy — emits BOUNTY_LOCK via the operator-signed
# /rpc/bounty/deploy surface (aitbc bounty, 3465dc438).
set -euo pipefail
. "$(dirname "$0")/../lib.sh"
serial_check || exit 75

spend_guard "$AMOUNT" || true
bid="stress-${HOST}-$(date +%s)"
dec=$(python3 -c "print(format(int('$AMOUNT')/36000000,'.18f').rstrip('0').rstrip('.'))")
out=$(cli bounty deploy --bounty-id "$bid" --amount "$dec" --memo "stress play" --wallet-name "$WALLET" 2>&1) || fail deploy "bounty deploy failed: $out"
tx=$(printf '%s' "$out" | python3 -c 'import json,sys,re; s=sys.stdin.read(); m=re.search(r"0x[0-9a-fA-F]{64}", s); print(m.group(0) if m else "")')
[ -n "$tx" ] || fail deploy "no tx_hash in response"
bh=$(wait_seal "$tx") || exit $?
echo "sealed $tx at height $bh (bounty $bid)"
ok "$tx"
