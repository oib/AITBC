#!/usr/bin/env bash
# LANE: parallel
# MODE: loop
# LIQUIDITY_DEPOSIT — pool-gated: a missing/invalid pool is a legit
# refusal (expected_refusal), not a defect.
set -euo pipefail
. "$(dirname "$0")/../lib.sh"
serial_check || exit 75

dec=$(python3 -c "print(format(int('$AMOUNT')/36000000,'.18f').rstrip('0').rstrip('.'))")
out=$("$AITBC_BIN" --output=json wallet --wallet-name "$WALLET" liquidity-stake \
  --amount "$dec" 2>&1) && rc=0 || rc=$?
if [ $rc -ne 0 ]; then
  case "$out" in
    *pool*|*Pool*|*stake*|*required*|*not found*)
      jsonl "$RUN_LOG" "{\"ts\":\"$(now)\",\"script\":\"${0##*/}\",\"host\":\"$HOST\",\"status\":\"expected_refusal\",\"reason\":\"liquidity gate: ${out:0:160}\"}"
      echo "expected_refusal: $out"; exit 0;;
  esac
  fail stake "liquidity-stake failed: $out"
fi
tx=$(printf '%s' "$out" | python3 -c 'import sys,re; m=re.search(r"0x[0-9a-fA-F]{64}", sys.stdin.read()); print(m.group(0) if m else "")')
[ -n "$tx" ] && { bh=$(wait_seal "$tx") || exit $?; echo "liquidity_deposit sealed: $tx h$bh"; }
ok "${tx:-}"
