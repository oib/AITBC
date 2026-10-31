#!/usr/bin/env bash
# LANE: parallel
# MODE: loop
# EXCHANGE anchor — `aitbc exchange-island buy` posts a signed EXCHANGE tx
# (open limit order) then `cancel` seals a second EXCHANGE record. Needs
# island credentials (/var/lib/aitbc/island_credentials.json) — island
# members only (node1/node2 today); elsewhere logs expected_refusal.
set -euo pipefail
. "$(dirname "$0")/../lib.sh"
serial_check || exit 75

if [ ! -f /var/lib/aitbc/island_credentials.json ]; then
  jsonl "$RUN_LOG" "{\"ts\":\"$(now)\",\"script\":\"${0##*/}\",\"host\":\"$HOST\",\"status\":\"expected_refusal\",\"reason\":\"no island credentials\"}"
  echo "no island credentials — exchange anchor skipped"; ok ""; exit 0
fi

# exchange-island resolves rpc from island credentials — no --rpc-url flag;
# bypass cli() which appends one.
out=$("$AITBC_BIN" --output=json exchange-island buy --ait-amount "${STRESS_EX_AMOUNT:-0.000001}" \
  --quote-currency ETH --max-price "${STRESS_EX_PRICE:-0.00000001}" \
  --wallet "$WALLET" 2>&1) || fail buy "exchange-island buy failed: $out"
tx=$(printf '%s' "$out" | python3 -c 'import sys,re; m=re.search(r"0x[0-9a-fA-F]{64}", sys.stdin.read()); print(m.group(0) if m else "")')
order_id=$(printf '%s' "$out" | python3 -c 'import sys,re; m=re.search(r"exchange_(buy|sell)_[0-9]+_[0-9a-f]+", sys.stdin.read()); print(m.group(0) if m else "")')
[ -n "$tx" ] || fail buy "no tx_hash in buy output"
[ -n "$order_id" ] || fail buy "no order_id in buy output"
bh=$(wait_seal "$tx") || exit $?
echo "exchange buy sealed: $tx h$bh ($order_id)"

out=$("$AITBC_BIN" --output=json exchange-island cancel --order-id "$order_id" --wallet "$WALLET" 2>&1) \
  || fail cancel "exchange-island cancel failed: $out"
tx=$(printf '%s' "$out" | python3 -c 'import sys,re; m=re.search(r"0x[0-9a-fA-F]{64}", sys.stdin.read()); print(m.group(0) if m else "")')
[ -n "$tx" ] || fail cancel "no tx_hash in cancel output"
bh=$(wait_seal "$tx") || exit $?
echo "exchange cancel sealed: $tx h$bh"
ok "$tx"
