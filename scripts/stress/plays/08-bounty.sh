#!/usr/bin/env bash
# LANE: parallel
# MODE: loop
# Bounty lifecycle: deploy (BOUNTY_LOCK) -> expire (BOUNTY_REFUND), plus
# submit -> verify legs for BOUNTY_PAYOUT (Refs #740).
# The rpc/bounty/* endpoints take operator-signed envelopes —
# `aitbc bounty deploy`'s CLI signature doesn't satisfy
# require_operator_signature (403 Invalid operator signature) so the
# play signs directly.  Pins to STRESS_OPERATOR_WALLET_<host>.
# Usage: ./08-bounty.sh                          deploy leg
#        ./08-bounty.sh <bounty-id>              expire leg
#        ./08-bounty.sh submit <bounty-id>       submission leg
#        ./08-bounty.sh verify <bounty-id> [sid] verify->BOUNTY_PAYOUT leg
set -euo pipefail
. "$(dirname "$0")/../lib.sh"
serial_check || exit 75

# Operator-signed plays pin to the host wallet named by
# STRESS_OPERATOR_WALLET_<host> (operator decision: node1 -> agent-econ-operator).
_opw_var="STRESS_OPERATOR_WALLET_$HOST"
WALLET="${!_opw_var:-$WALLET}"
WFILE="${OPERATOR_WALLET_PATH:-${STRESS_WALLET_PATH:-/var/lib/aitbc/wallets/${WALLET}.json}}"
[ -f "$WFILE" ] || fail resolve "wallet file $WFILE not found"
LEG="expire"; BOUNTY_ID="${1:-}"; SUBMISSION_ID=""
case "${1:-}" in
  submit|verify) LEG="$1"; BOUNTY_ID="${2:-}"; SUBMISSION_ID="${3:-}";;
esac

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

if [ -z "$BOUNTY_ID" ]; then
  spend_guard "$AMOUNT" || true
  BOUNTY_ID="stress-bounty-$(hostname -s)-$(date +%s)"
  resp=$(call /rpc/bounty/deploy \
    "{\"bounty_id\":\"$BOUNTY_ID\",\"user_address\":\"$addr\",\"reward_amount\":${STRESS_REWARD:-360000},\"chain_id\":\"$CHAIN\"}" 2>&1) \
    || fail deploy "bounty deploy refused: $resp"
  tx=$(printf '%s' "$resp" | python3 -c 'import re,sys
m=re.search(r"0x[0-9a-fA-F]{64}", sys.stdin.read()); print(m.group(0) if m else "")')
  [ -n "$tx" ] && wait_seal "$tx" >/dev/null || true
  echo "deployed $BOUNTY_ID — expire leg re-runnable as ./08-bounty.sh $BOUNTY_ID"
  ok "${tx:-}"; exit 0
fi

if [ "$LEG" = "submit" ]; then
  SUBMISSION_ID="${SUBMISSION_ID:-sub-$(hostname -s)-$(date +%s)}"
  resp=$(call "/rpc/bounty/$BOUNTY_ID/submit" \
    "{\"submission_id\":\"$SUBMISSION_ID\",\"user_address\":\"$addr\",\"chain_id\":\"$CHAIN\"}" 2>&1) \
    || fail submit "bounty submit failed: $resp"
  echo "submitted $SUBMISSION_ID on $BOUNTY_ID — verify leg: ./08-bounty.sh verify $BOUNTY_ID $SUBMISSION_ID"
  ok ""; exit 0
fi

if [ "$LEG" = "verify" ]; then
  [ -n "$SUBMISSION_ID" ] || fail args "verify needs a submission_id: ./08-bounty.sh verify <bounty-id> <submission-id>"
  resp=$(call "/rpc/bounty/$BOUNTY_ID/verify" \
    "{\"bounty_id\":\"$BOUNTY_ID\",\"submission_id\":\"$SUBMISSION_ID\",\"user_address\":\"$addr\",\"verified\":true,\"chain_id\":\"$CHAIN\"}" 2>&1) \
    || fail verify "bounty verify failed: $resp"
  pay_tx=$(printf '%s' "$resp" | python3 -c 'import re,sys
m=re.search(r"0x[0-9a-fA-F]{64}", sys.stdin.read()); print(m.group(0) if m else "")')
  [ -n "$pay_tx" ] && wait_seal "$pay_tx" >/dev/null || true
  echo "verified -> BOUNTY_PAYOUT $pay_tx"
  ok "${pay_tx:-}"; exit 0
fi

# Expire leg needs the lock fully confirmed — a 409 'not fully confirmed'
# is a maturity skip, not a failure.
resp=$(call "/rpc/bounty/$BOUNTY_ID/expire" "{\"user_address\":\"$addr\",\"chain_id\":\"$CHAIN\"}" 2>&1) || {
  printf '%s' "$resp" | grep -qiE "not fully confirmed|not.*expired|deadline" \
    && skip_mature "expire not ready: $resp" || fail expire "expire failed: $resp"
}
exp_tx=$(printf '%s' "$resp" | python3 -c 'import re,sys
m=re.search(r"0x[0-9a-fA-F]{64}", sys.stdin.read()); print(m.group(0) if m else "")')
[ -n "$exp_tx" ] && wait_seal "$exp_tx" >/dev/null || true
ok "${exp_tx:-}"
