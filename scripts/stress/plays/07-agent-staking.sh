#!/usr/bin/env bash
# LANE: parallel
# MODE: loop
# Agent-stake lifecycle: lock -> unbond -> complete via the operator-signed
# /rpc/agent-staking/* endpoints (require_operator_signature —
# AGENT_ECONOMICS_OPERATOR_ADDRESS wallet).  The play signs the canonical
# envelope with the wallet file's key; WALLET must name the operator wallet
# (agent-econ-operator on node1).
# Usage: ./07-agent-staking.sh [lock|unbond|complete]
set -euo pipefail
. "$(dirname "$0")/../lib.sh"
serial_check || exit 75

STAKE_ID="${STRESS_STAKE_ID:-stress-stake-$(hostname -s)-$(date +%s)}"
STAKE_AMT="${STRESS_STAKE_AMT:-36000}"
LEG="${1:-lock}"
WFILE="${OPERATOR_WALLET_PATH:-${STRESS_WALLET_PATH:-/var/lib/aitbc/wallets/${WALLET}.json}}"
[ -f "$WFILE" ] || fail resolve "wallet file $WFILE not found"

call() {  # call <path> <payload-json>
  STRESS_PAYLOAD="$2" STRESS_PATH="$1" STRESS_WFILE="$WFILE" RPC_URL="$RPC_URL" python3 - <<'PYEOF'
import json, os, urllib.request, urllib.error
from eth_keys import keys
from eth_utils import keccak
w = json.load(open(os.environ["STRESS_WFILE"]))
priv = keys.PrivateKey(bytes.fromhex(w["private_key"].removeprefix("0x")))
payload = json.loads(os.environ["STRESS_PAYLOAD"])
digest = keccak(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode())
payload["signature"] = priv.sign_msg_hash(digest).to_hex()
req = urllib.request.Request(os.environ["RPC_URL"] + os.environ["STRESS_PATH"],
    data=json.dumps(payload).encode(), headers={"Content-Type": "application/json"}, method="POST")
try:
    print(urllib.request.urlopen(req, timeout=20).read().decode())
except urllib.error.HTTPError as e:
    print("HTTP", e.code, e.read().decode()); raise SystemExit(1)
PYEOF
}
addr=$(python3 -c "import json;print(json.load(open('$WFILE')).get('address',''))" 2>/dev/null)
[ -n "$addr" ] || fail resolve "no address in $WFILE"

case "$LEG" in
  lock)
    spend_guard "$AMOUNT" || true
    resp=$(call /rpc/agent-staking/stake \
      "{\"stake_id\":\"$STAKE_ID\",\"user_address\":\"$addr\",\"agent_wallet\":\"$addr\",\"amount\":$STAKE_AMT,\"chain_id\":\"$CHAIN\",\"lock_days\":${STRESS_LOCK_DAYS:-1}}" 2>&1) \
      || fail lock "agent-stake lock refused: $resp"
    tx=$(printf '%s' "$resp" | python3 -c 'import re,sys
m=re.search(r"0x[0-9a-fA-F]{64}", sys.stdin.read()); print(m.group(0) if m else "")')
    [ -n "$tx" ] && wait_seal "$tx" >/dev/null || true
    echo "stake_id=$STAKE_ID"
    ok "${tx:-}"
    ;;
  unbond)
    resp=$(call "/rpc/agent-staking/stake/${STRESS_STAKE_ID:-$STAKE_ID}/unbond" "{\"chain_id\":\"$CHAIN\"}" 2>&1) || {
      printf '%s' "$resp" | grep -qiE "not.*expired|locked until" \
        && skip_mature "unbond refused: $resp" || fail unbond "unbond failed: $resp"
    }
    ok ""
    ;;
  complete)
    resp=$(call "/rpc/agent-staking/stake/${STRESS_STAKE_ID:-$STAKE_ID}/complete" "{\"chain_id\":\"$CHAIN\"}" 2>&1) || {
      printf '%s' "$resp" | grep -qiE "not.*unbond|window|mature|height" \
        && skip_mature "complete refused: $resp" || fail complete "complete failed: $resp"
    }
    ok ""
    ;;
  *) fail args "unknown leg $LEG";;
esac
