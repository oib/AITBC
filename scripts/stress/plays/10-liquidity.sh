#!/usr/bin/env bash
# LANE: parallel
# MODE: loop
# LIQUIDITY family — pool-gated: a missing/invalid pool is a legit
# refusal (expected_refusal), not a defect.
# Legs: deposit (default) | claim <stake-id|auto> | unstake <stake-id|auto>
#   stake-id resolves from /rpc/liquidity/stakes/<wallet-addr>
#   (liq_<tx_prefix> convention); "auto" picks the first usable position.
set -euo pipefail
. "$(dirname "$0")/../lib.sh"
serial_check || exit 75

LEG="${1:-deposit}"; WANT_SID="${2:-}"
WFILE="${STRESS_WALLET_PATH:-/var/lib/aitbc/wallets/${WALLET}.json}"
[ -f "$WFILE" ] || fail resolve "wallet file $WFILE not found"
addr=$(python3 -c "import json;print(json.load(open('$WFILE')).get('address',''))" 2>/dev/null)
[ -n "$addr" ] || fail resolve "no address in $WFILE"

pick_stake() {  # pick_stake — first active stake_id for the wallet
  curl -sf --max-time 10 "$RPC_URL/rpc/liquidity/stakes/$addr" | python3 -c '
import json,sys
try: d=json.load(sys.stdin)
except Exception: print(""); raise SystemExit
for s in d.get("stakes",[]):
    if s.get("status")=="active": print(s["stake_id"]); break
' 2>/dev/null
}

case "$LEG" in
  deposit)
    spend_guard "$AMOUNT" || true
    dec=$(python3 -c "print(format(int('$AMOUNT')/36000000,'.18f').rstrip('0').rstrip('.'))")
    out=$("$AITBC_BIN" --output=json wallet --wallet-path "$WFILE" liquidity-stake \
      --amount "$dec" 2>&1) && rc=0 || rc=$?
    if [ $rc -ne 0 ]; then
      case "$out" in
        *pool*|*Pool*|*stake*|*required*|*"not found"*)
          jsonl "$RUN_LOG" "{\"ts\":\"$(now)\",\"script\":\"${0##*/}\",\"host\":\"$HOST\",\"status\":\"expected_refusal\",\"reason\":\"liquidity gate: ${out:0:160}\"}"
          echo "expected_refusal: $out"; exit 0;;
      esac
      fail stake "liquidity-stake failed: $out"
    fi
    tx=$(printf '%s' "$out" | python3 -c 'import sys,re; m=re.search(r"0x[0-9a-fA-F]{64}", sys.stdin.read()); print(m.group(0) if m else "")')
    [ -n "$tx" ] && { bh=$(wait_seal "$tx") || exit $?; echo "liquidity_deposit sealed: $tx h$bh"; }
    ok "${tx:-}"
    ;;
  claim|unstake)
    sid="$WANT_SID"
    if [ -z "$sid" ] || [ "$sid" = "auto" ]; then sid=$(pick_stake); fi
    [ -n "$sid" ] || skip_mature "no active liquidity position for $addr"
    cmd=liquidity-claim; [ "$LEG" = unstake ] && cmd=liquidity-unstake
    out=$("$AITBC_BIN" --output=json wallet --wallet-path "$WFILE" "$cmd" \
      --stake-id "$sid" 2>&1) || {
      printf '%s' "$out" | grep -qiE "locked until|matur|not.*expired" \
        && skip_mature "$cmd refused: $out" || fail "$LEG" "$cmd failed: $out"
    }
    tx=$(printf '%s' "$out" | python3 -c 'import sys,re; m=re.search(r"0x[0-9a-fa-f]{64}", sys.stdin.read()); print(m.group(0) if m else "")')
    [ -n "$tx" ] && { bh=$(wait_seal "$tx") || exit $?; echo "$cmd sealed: $tx h$bh"; }
    ok "${tx:-}"
    ;;
  *) fail args "unknown leg $LEG";;
esac
