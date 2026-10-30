#!/usr/bin/env bash
# preflight.sh — fleet readiness check. rpc checks work from any host via
# fleet URLs; wallet/systemd checks need ssh (IDE-side) or run locally.
set -euo pipefail
cd "$(dirname "$0")"; . ./lib.sh
HOSTS="${STRESS_HOSTS:-hub hub1 node0 node1 node2}"
WALLET="${STRESS_WALLET:-default}"
MIN_BAL="${STRESS_MIN_BAL:-50000}"
OUT="$STATE_DIR/stress-preflight.json"
rows=(); rc=0
for h in $HOSTS; do
  url=$(stress_rpc_url "$h")
  ht=$(curl -sf --max-time 10 "$url/rpc/status" | python3 -c 'import json,sys;print(json.load(sys.stdin).get("height",-1))' 2>/dev/null || echo -1)
  led=$(curl -sf --max-time 10 -o /dev/null -w '%{http_code}' -H "X-API-Key: ${BRIDGE_LEDGER_API_KEY:-x}" "https://hub.aitbc.bubuit.net/rpc/bridge/ledger/pending" 2>/dev/null || echo 000)
  if [ "$(hostname -s)" = "$h" ] || ssh -o ConnectTimeout=5 -o BatchMode=yes "$h" true 2>/dev/null; then
    row=$(stress_ssh "$h" 'a=$(systemctl is-active aitbc-blockchain-node 2>/dev/null||echo ?); b=$(/usr/local/bin/aitbc --output=json wallet balance "'"$WALLET"'" 2>/dev/null|python3 -c "import json,sys;print(json.load(sys.stdin).get(\"balance\",\"0\"))" 2>/dev/null||echo 0); printf "{\"node\":\"%s\",\"balance\":%s}" "$a" "$b"' 2>/dev/null || echo '{"node":"unreachable","balance":0}')
  else row='{"node":"no-ssh","balance":-1}'; fi
  chk=$(printf '%s' "$row" | python3 -c 'import json,sys
d=json.loads(sys.stdin.read()); ok=d["node"]=="active" and float(d["balance"])>'"$MIN_BAL"'-1
print("ok" if ok else "FAIL")' 2>/dev/null || echo FAIL)
  [ "$ht" -gt 0 ] || chk=FAIL; [ "$led" != "000" ] || chk=FAIL
  [ "$chk" = ok ] || rc=1
  rows+=("{\"host\":\"$h\",\"check\":\"$chk\",\"height\":$ht,\"ledger_http\":$led,\"local\":$row}")
done
printf '{"ts":"%s","checks":[%s]}\n' "$(now)" "$(IFS=,; echo "${rows[*]}")" | tee "$OUT"
[ $rc -eq 0 ] && echo "PREFLIGHT OK" || echo "PREFLIGHT FAIL"
exit $rc
