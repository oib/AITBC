#!/usr/bin/env bash
# preflight.sh — fleet readiness ×5. rpc checks via fleet URLs (any host);
# balance/ledger/systemd probes run ON-HOST via ssh (IDE-side aliases) or
# locally when invoked on the target host. Never echoes secrets.
set -euo pipefail
cd "$(dirname "$0")"; . ./lib.sh
HOSTS="${STRESS_HOSTS:-hub hub1 node0 node1 node2}"
WALLET="${STRESS_WALLET:-default}"
MIN_BAL="${STRESS_MIN_BAL:-50000}"
OUT="$STATE_DIR/stress-preflight.json"
mkdir -p "$STATE_DIR"
rows=(); rc=0
LEDGER="${STRESS_LEDGER_URL:-https://hub.aitbc.bubuit.net}"
PROBE='b=$(/usr/local/bin/aitbc --output=json wallet --wallet-name "__WALLET__" balance 2>/dev/null | python3 -c "import json,sys;print(json.load(sys.stdin).get(\"balance\",0))" 2>/dev/null || echo 0); a=$(systemctl is-active aitbc-blockchain-node 2>/dev/null||echo ?); k=$( { set -a; . /etc/aitbc/aitbc-blockchain-rpc.env 2>/dev/null; . /etc/aitbc/blockchain-secrets.env 2>/dev/null; set +a; code=$(curl -s -o /dev/null -w "%{http_code}" --max-time 10 -H "X-API-Key: ${BRIDGE_LEDGER_API_KEY:-none}" "__LEDGER__/rpc/bridge/ledger/pending?target_chain=bc-2-island-1"); [ "$code" = 200 ] && echo 200 || echo "$code"; } ); printf "{\"node\":\"%s\",\"balance\":%s,\"ledger\":%s}" "$a" "${b:-0}" "${k:-000}"'
for h in $HOSTS; do
  url=$(stress_rpc_url "$h")
  [ "$h" = "hub" ] && LEDGER=http://127.0.0.1:8202 || LEDGER=https://hub.aitbc.bubuit.net
  wv="STRESS_WALLET_${h//./_}"; w="${!wv:-$WALLET}"
  P="${PROBE//__WALLET__/$w}"; P="${P//__LEDGER__/$LEDGER}"
  ht=$(curl -sf --max-time 10 "$url/rpc/status" | python3 -c 'import json,sys;print(json.load(sys.stdin).get("height",-1))' 2>/dev/null || echo -1)
  if [ "$(hostname -s)" = "$h" ]; then row=$(bash -c "$P" 2>/dev/null || echo '{"node":"probe-fail","balance":0,"ledger":"000"}')
  else row=$(ssh -o ConnectTimeout=8 -o BatchMode=yes "$h" "$P" 2>/dev/null || echo '{"node":"no-ssh","balance":-1,"ledger":"no-ssh"}'); fi
  chk=$(printf '%s' "$row" | python3 -c 'import json,sys
d=json.loads(sys.stdin.read())
ok=(d["node"]=="active" and float(d["balance"])>='"$MIN_BAL"' and str(d["ledger"])=="200")
print("ok" if ok else "FAIL")' 2>/dev/null || echo FAIL)
  [ "$ht" -gt 0 ] || chk=FAIL
  [ "$chk" = ok ] || rc=1
  rows+=("{\"host\":\"$h\",\"wallet\":\"$w\",\"check\":\"$chk\",\"height\":$ht,\"local\":$row}")
done
printf '{"ts":"%s","checks":[%s]}\n' "$(now)" "$(IFS=,; echo "${rows[*]}")" | tee "$OUT"
[ $rc -eq 0 ] && echo "PREFLIGHT OK" || echo "PREFLIGHT FAIL"
exit $rc
