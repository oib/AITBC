#!/usr/bin/env bash
# LANE: parallel
# MODE: loop
# Liquidity deposit — wallet-signed liquidity-stake submission
# (LIQUIDITY_DEPOSIT on the committed-table family).
set -euo pipefail
. "$(dirname "$0")/../lib.sh"
serial_check || exit 75

spend_guard "$AMOUNT" || true
dec=$(python3 -c "print(format(int('$AMOUNT')/36000000,'.18f').rstrip('0').rstrip('.'))")
out=$(cli wallet liquidity-stake --wallet-name "$WALLET" --amount "$dec" --pool main --lock-days 1 2>&1) || fail deposit "liquidity-stake failed: $out"
tx=$(printf '%s' "$out" | python3 -c 'import json,sys,re; s=sys.stdin.read(); m=re.search(r"0x[0-9a-fA-F]{64}", s); print(m.group(0) if m else "")')
[ -n "$tx" ] || fail deposit "no tx_hash in response"
bh=$(wait_seal "$tx") || exit $?
echo "sealed $tx at height $bh"
ok "$tx"
