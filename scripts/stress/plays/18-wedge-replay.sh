#!/usr/bin/env bash
# LANE: serial. MODE: once
# Regression guard for #712/#716/#717: a rejected writeback tombstone
# must not poison the sender's next legitimate nonce — submit a tx that
# lands rejected-writeback, then a corrected next-nonce tx, assert seal.
set -euo pipefail
. "$(dirname "$0")/../lib.sh"
serial_check || exit 75
addr=0x00000000000000000000000000000000000000d9
PW_ARGS=(); [ -n "${STRESS_WALLET_PASSWORD_FILE:-}" ] && PW_ARGS=(--password-file "$STRESS_WALLET_PASSWORD_FILE")

# Poison leg: a RECEIPT_CLAIM for a nonexistent lock → rejected writeback.
out=$("$AITBC_BIN" --output=json transactions send --from "$WALLET" --to "$addr" \
  --amount 0 --fee 0.000001 --type RECEIPT_CLAIM "${PW_ARGS[@]}" \
  --payload "{\"claim\":\"nonexistent-$(date +%s)\"}" ${RPC_URL:+--rpc-url "$RPC_URL"} 2>&1 || true)
jsonl "$RUN_LOG" "{\"ts\":\"$(now)\",\"script\":\"${0##*/}\",\"host\":\"$HOST\",\"status\":\"poison\",\"reason\":\"${out:0:160}\"}"

# Recovery leg: a normal next-nonce TRANSFER must seal.
tx=$("$AITBC_BIN" --output=json transactions send --from "$WALLET" --to "$addr" \
  --amount 0.000001 --fee 0.02 "${PW_ARGS[@]}" ${RPC_URL:+--rpc-url "$RPC_URL"} 2>&1 | python3 -c 'import sys,re; m=re.search(r"0x[0-9a-fA-F]{64}", sys.stdin.read()); print(m.group(0) if m else "")')
[ -n "$tx" ] || fail wedge "recovery send rejected: tombstone poisoned next nonce"
bh=$(wait_seal "$tx") || exit $?
echo "wedge-replay ok: recovery tx sealed $tx h$bh"
ok "$tx"
