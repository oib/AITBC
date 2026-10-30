#!/usr/bin/env bash
# LANE: parallel
# MODE: loop
# Bounty lifecycle: deploy (BOUNTY_LOCK seal) -> expire (BOUNTY_EXPIRE/
# refund to creator).  `expire` is an operator-side command on the
# same wallet — the legs run in sequence inside one iteration when
# --ttl is short.  --bounty-id <id> runs only the expire leg.
set -euo pipefail
. "$(dirname "$0")/../lib.sh"
serial_check || exit 75

addr=$(python3 -c "import json;print(json.load(open('${OPERATOR_WALLET_PATH:-/var/lib/aitbc/wallets/${WALLET}.json}')).get('address',''))" 2>/dev/null || true)
[ -n "$addr" ] || fail resolve "no address for wallet $WALLET"
BOUNTY_ID="${1:-}"

if [ -z "$BOUNTY_ID" ]; then
  spend_guard "$AMOUNT" || true
  BOUNTY_ID="stress-bounty-$(date +%s)"
  out=$(cli bounty deploy --bounty-id "$BOUNTY_ID" --amount "${STRESS_REWARD:-0.01}" \
        --user-address "$addr" --wallet-name "$WALLET" 2>&1) \
      || fail deploy "bounty deploy failed: $out"
  tx=$(printf '%s' "$out" | python3 -c 'import re,sys
m=re.search(r"0x[0-9a-fA-F]{64}", sys.stdin.read()); print(m.group(0) if m else "")')
  [ -n "$tx" ] && wait_seal "$tx" >/dev/null || true
  echo "deployed $BOUNTY_ID — expire leg re-runnable as ./08-bounty.sh $BOUNTY_ID"
  ok "${tx:-}"; exit 0
fi

out=$(cli bounty expire --bounty-id "$BOUNTY_ID" --wallet-name "$WALLET" 2>&1) || {
  printf '%s' "$out" | grep -qiE "not.*expired|deadline|active" \
    && skip_mature "expire refused: $out" || fail expire "bounty expire failed: $out"
}
exp_tx=$(printf '%s' "$out" | python3 -c 'import re,sys
m=re.search(r"0x[0-9a-fA-F]{64}", sys.stdin.read()); print(m.group(0) if m else "")')
[ -n "$exp_tx" ] && wait_seal "$exp_tx" >/dev/null || true
ok "${exp_tx:-}"
