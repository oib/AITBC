#!/usr/bin/env bash
# LANE: parallel
# MODE: loop
# Agent-stake lifecycle: lock (STAKE_LOCK) -> unbond -> complete
# (STAKE_RELEASE).  Driven over /rpc/agent-stake/* (the v17 shape —
# `aitbc agent` has no stake subcommands; `aitbc stake` is the
# consensus family, a different type).  Legs after lock are
# maturity-gated: unbond refuses until locked_until passes,
# complete until the unbond window + height target.
# Usage: ./07-agent-staking.sh [lock|unbond|complete]
set -euo pipefail
. "$(dirname "$0")/../lib.sh"
serial_check || exit 75

AGENT_ID="${STRESS_AGENT_ID:-stress-agent-$(hostname -s)}"
STAKE_AMT="${STRESS_STAKE_AMT:-36000}"
LEG="${1:-lock}"

addr=$(python3 -c "import json;print(json.load(open('${OPERATOR_WALLET_PATH:-/var/lib/aitbc/wallets/${WALLET}.json}')).get('address',''))" 2>/dev/null || true)
[ -n "$addr" ] || fail resolve "no address for wallet $WALLET"

case "$LEG" in
  lock)
    spend_guard "$AMOUNT" || true
    resp=$(rpc_post /rpc/agent-stake/stake \
      "{\"agent_id\":\"$AGENT_ID\",\"address\":\"$addr\",\"amount\":$STAKE_AMT,\"lock_days\":${STRESS_LOCK_DAYS:-1}}" 2>&1) \
      || fail lock "agent-stake lock refused: $resp"
    tx=$(printf '%s' "$resp" | python3 -c 'import json,sys,re
m=re.search(r"0x[0-9a-fA-F]{64}", sys.stdin.read()); print(m.group(0) if m else "")')
    [ -n "$tx" ] && wait_seal "$tx" >/dev/null || true
    ok "${tx:-}"
    ;;
  unbond)
    resp=$(rpc_post /rpc/agent-stake/unbond "{\"agent_id\":\"$AGENT_ID\",\"address\":\"$addr\"}" 2>&1) || {
      printf '%s' "$resp" | grep -qiE "not.*expired|locked until" \
        && skip_mature "unbond refused: $resp" || fail unbond "agent-stake unbond failed: $resp"
    }
    ok ""
    ;;
  complete)
    resp=$(rpc_post /rpc/agent-stake/complete "{\"agent_id\":\"$AGENT_ID\",\"address\":\"$addr\"}" 2>&1) || {
      printf '%s' "$resp" | grep -qiE "not.*unbond|window|mature|height" \
        && skip_mature "complete refused: $resp" || fail complete "agent-stake complete failed: $resp"
    }
    ok ""
    ;;
  *) fail args "unknown leg $LEG";;
esac
