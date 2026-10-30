#!/usr/bin/env bash
# LANE: parallel
# MODE: loop
# GPU_REGISTER — unique gpu-id per iteration; register is the self-serve
# leg (allocate/deregister need job-side handles).
set -euo pipefail
. "$(dirname "$0")/../lib.sh"
serial_check || exit 75

gid="stress-$(date +%s)-$$"
out=$("$AITBC_BIN" --output=json gpu-onchain register --gpu-id "$gid" \
  --miner-id "$WALLET" --model "STRESS-GPU" --memory-gb 8 --price-per-hour 1 \
  --wallet "$WALLET" 2>&1) || fail register "gpu register failed: $out"
tx=$(printf '%s' "$out" | python3 -c 'import sys,re; m=re.search(r"0x[0-9a-fA-F]{64}", sys.stdin.read()); print(m.group(0) if m else "")')
[ -n "$tx" ] || fail register "no tx_hash in response"
bh=$(wait_seal "$tx") || exit $?
echo "gpu_register sealed: $tx h$bh"
ok "$tx"
