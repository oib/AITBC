#!/usr/bin/env bash
# LANE: parallel
# MODE: loop
# Agent-staking stake lock — emits STAKE_LOCK via the operator-signed
# /rpc/agent-staking/stake surface (aitbc agent-staking, 3465dc438).
set -euo pipefail
. "$(dirname "$0")/../lib.sh"
serial_check || exit 75

addr=$("$AITBC_BIN" --output=json wallet --wallet-name "$WALLET" balance 2>/dev/null | python3 -c 'import json,sys;print(json.load(sys.stdin).get("address",""))' 2>/dev/null || true)
[ -n "$addr" ] || fail resolve "no address for wallet $WALLET"
spend_guard "$AMOUNT" || true
sid="stress-${HOST}-$(date +%s)"
dec=$(python3 -c "print(format(int('$AMOUNT')/36000000,'.18f').rstrip('0').rstrip('.'))")
out=$(cli agent-staking stake --stake-id "$sid" --agent-wallet "$addr" --amount "$dec" --lock-days 1 --wallet-name "$WALLET" 2>&1) || fail stake "agent-staking stake failed: $out"
tx=$(printf '%s' "$out" | python3 -c 'import json,sys,re; s=sys.stdin.read(); m=re.search(r"0x[0-9a-fA-F]{64}", s); print(m.group(0) if m else "")')
[ -n "$tx" ] || fail stake "no tx_hash in response"
bh=$(wait_seal "$tx") || exit $?
echo "sealed $tx at height $bh (stake $sid)"
ok "$tx"
