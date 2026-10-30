#!/usr/bin/env bash
# LANE: parallel
# MODE: loop
# STAKE_LOCK via the wallet-signed consensus lane (aitbc wallet stake).
# The agent-staking operator surface needs the env-held operator key —
# STRESS-OPERATOR-KEY-1 (#709) — so the consensus lane is the
# exercisable path for the committed-table STAKE family.
set -euo pipefail
. "$(dirname "$0")/../lib.sh"
serial_check || exit 75

spend_guard "$AMOUNT" || true
dec=$(python3 -c "print(format(int('$AMOUNT')/36000000,'.18f').rstrip('0').rstrip('.'))")
[ "$dec" = "0" ] || [ -z "$dec" ] && dec="0.001"
out=$(echo x | "$AITBC_BIN" wallet stake --wallet-path "/var/lib/aitbc/wallets/${WALLET}.json" --amount "$dec" --duration 1 --password-stdin 2>&1) || fail stake "wallet stake failed: $out"
tx=$(printf '%s' "$out" | python3 -c 'import json,sys,re; s=sys.stdin.read(); m=re.search(r"0x[0-9a-fA-F]{64}", s); print(m.group(0) if m else "")')
[ -n "$tx" ] || fail stake "no tx_hash in response"
bh=$(wait_seal "$tx") || exit $?
echo "sealed $tx at height $bh (consensus STAKE_LOCK)"
ok "$tx"
