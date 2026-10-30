#!/usr/bin/env bash
# preflight.sh — one pass verifying the fleet is ready for gameplay.
set -euo pipefail
HOSTS="${STRESS_HOSTS:-hub hub1 node0 node1 node2}"
WALLET="${STRESS_WALLET:-default}"
MIN_BAL="${STRESS_MIN_BAL:-50000}"
OUT="${STRESS_STATE_DIR:-/var/lib/aitbc/stress-state}/stress-preflight.json"
mkdir -p "$(dirname "$OUT")" 2>/dev/null || true
rows=(); rc=0
for h in $HOSTS; do
  row=$(ssh "$h" 'bash -s' "$WALLET" "$MIN_BAL" <<'IN' 2>&1
    W="$1"; MB="$2"
    rpc="http://127.0.0.1:8202"
    h=$(curl -sf --max-time 10 "$rpc/rpc/status" | python3 -c 'import json,sys;print(json.load(sys.stdin).get("height",-1))' 2>/dev/null || echo -1)
    active=$(systemctl is-active aitbc-blockchain-node 2>/dev/null || echo unknown)
    ledger=$(tr "\0" "\n" </proc/$(systemctl show aitbc-blockchain-rpc -p MainPID --value)/environ 2>/dev/null | grep -c '^BRIDGE_LEDGER_URL=' || true)
    bal=$(/usr/local/bin/aitbc --output=json wallet balance "$W" 2>/dev/null | python3 -c 'import json,sys;print(json.load(sys.stdin).get("balance","0"))' 2>/dev/null || echo 0)
    printf '{"height":%s,"node":"%s","ledger_env":%s,"balance":%s,"min_bal":%s}' "$h" "$active" "$ledger" "$bal" "$MB"
IN
)
  okhost=$(printf '%s' "$row" | tail -1 | python3 -c 'import json,sys
try:
  d=json.loads(sys.stdin.read())
  ok = d["height"]>0 and d["node"]=="active" and d["ledger_env"]>=1 and float(d["balance"])>=d["min_bal"]
  print("ok" if ok else "FAIL")
except Exception: print("FAIL")' 2>/dev/null || echo FAIL)
  [ "$okhost" = "ok" ] || rc=1
  rows+=("{\"host\":\"$h\",\"check\":\"$okhost\",\"detail\":$(printf '%s' "$row" | tail -1)}")
done
printf '{"ts":"%s","checks":[%s]}\n' "$(date -u +%FT%TZ)" "$(IFS=,; echo "${rows[*]}")" | tee "$OUT"
[ $rc -eq 0 ] && echo "PREFLIGHT OK" || echo "PREFLIGHT FAIL"
exit $rc
