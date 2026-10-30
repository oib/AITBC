#!/usr/bin/env bash
# LANE: parallel
# MODE: loop
# Market offer lifecycle: create -> GPU_MARKET seal -> offer-cancel ->
# second GPU_MARKET seal.  Runs on the shop host (node2 role).
set -euo pipefail
. "$(dirname "$0")/../lib.sh"
serial_check || exit 75

addr=$(cli wallet --wallet-name "$WALLET" balance 2>/dev/null | python3 -c 'import json,sys;print(json.load(sys.stdin).get("address",""))' 2>/dev/null || true)
[ -n "$addr" ] || fail resolve "no address for wallet $WALLET"
spend_guard "$AMOUNT" || true

desc="stress-1 offer $(date +%s)"
out=$(cli market offer --service-type ollama --model-or-variant "${STRESS_MODEL:-llama3.2:3b}" \
      --price "${STRESS_PRICE:-0.001}" --unit per_1k_tokens --description "$desc" 2>&1) \
    || fail offer "market offer failed: $out"
create_tx=$(printf '%s' "$out" | python3 -c 'import re,sys
m=re.search(r"0x[0-9a-fA-F]{64}", sys.stdin.read())
print(m.group(0) if m else "")')
[ -n "$create_tx" ] || fail offer "no tx_hash in offer output"
wait_seal "$create_tx" >/dev/null

# Resolve the offer id from the market list (id column sw_offer_*).
offer_id=$(cli market list 2>/dev/null | python3 -c 'import re,sys
s=sys.stdin.read()
m=re.findall(r"sw_offer_\d+_[0-9a-f]+", s)
print(m[-1] if m else "")')
[ -n "$offer_id" ] || fail offer "no sw_offer id for $desc"

out=$(cli market offer-cancel --order-ids "$offer_id" 2>&1) \
    || fail cancel "offer-cancel failed: $out"
cancel_tx=$(printf '%s' "$out" | python3 -c 'import re,sys
m=re.search(r"0x[0-9a-fA-F]{64}", sys.stdin.read())
print(m.group(0) if m else "")')
[ -n "$cancel_tx" ] || fail cancel "no tx_hash in cancel output"
wait_seal "$cancel_tx" >/dev/null
ok "$cancel_tx"
