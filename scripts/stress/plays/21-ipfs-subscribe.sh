#!/usr/bin/env bash
# LANE: parallel
# MODE: loop
# IPFS_SUBSCRIPTION anchor — `aitbc ipfs island subscribe` submits a
# value-bearing subscription tx (island_id/duration_blocks/quota_bytes
# payload); the record seals like any other tx. Params default to the
# live island shape (island bc-2-island-1, treasury
# 0x715FC5...BfA60 — the pair observed in sealed subscriptions).
set -euo pipefail
. "$(dirname "$0")/../lib.sh"
serial_check || exit 75

ISLAND_ID="${STRESS_ISLAND_ID:-bc-2-island-1}"
TREASURY="${STRESS_ISLAND_TREASURY:-0x715FC5220972Fc15144A9da539Faa61890dBfA60}"

out=$(cli ipfs island subscribe --wallet "$WALLET" --to "$TREASURY" \
  --island-id "$ISLAND_ID" --duration "${STRESS_SUB_DURATION:-10}" \
  --quota "${STRESS_SUB_QUOTA:-1048576}" --amount "${STRESS_SUB_AMOUNT:-0.001}" 2>&1) \
    || fail subscribe "ipfs island subscribe failed: $out"
tx=$(printf '%s' "$out" | python3 -c 'import sys,re; m=re.search(r"0x[0-9a-fA-F]{64}", sys.stdin.read()); print(m.group(0) if m else "")')
[ -n "$tx" ] || fail subscribe "no tx_hash in response"
bh=$(wait_seal "$tx") || exit $?
echo "ipfs_subscription sealed: $tx h$bh"
ok "$tx"
