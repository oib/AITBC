#!/usr/bin/env bash
# LANE: parallel
# MODE: loop
set -euo pipefail
. "$(dirname "$0")/../lib.sh"
serial_check || exit 75
addr=$("$AITBC_BIN" --output=json wallet --wallet-name "$WALLET" balance 2>/dev/null | python3 -c 'import json,sys;print(json.load(sys.stdin).get("address",""))' 2>/dev/null || true)
[ -n "$addr" ] || fail resolve "no address for wallet $WALLET"
# Stub body — fill per family with the real leg sequence (see 01/12/13/14/15
# for proven shapes: bare aitbc for no-rpc-url commands, --wallet signing,
# wait_seal, expected_refusal on gated legs).
ok ""
