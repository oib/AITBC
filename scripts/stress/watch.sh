#!/usr/bin/env bash
# watch.sh — finding collector. --sweep (one pass) | --follow (continuous).
set -euo pipefail
cd "$(dirname "$0")"; . ./lib.sh 2>/dev/null || true
HOSTS="${STRESS_HOSTS:-hub hub1 node0 node1 node2}"
BASE="${STRESS_STATE_DIR:-/var/lib/aitbc/stress-state}/stress-baseline.json"
KNOWN="$(dirname "$0")/KNOWN.md"
OUT="${STRESS_STATE_DIR:-/var/lib/aitbc/stress-state}/stress-findings.jsonl"
INTERVAL="${WATCH_INTERVAL:-60}"
MODE="${1:---sweep}"

sweep_once() {
  for h in $HOSTS; do
    ssh "$h" 'journalctl -u "aitbc-*" --since "-2 min" -p warning --no-pager -o cat 2>/dev/null | sort | uniq -c | sort -rn | head -10 | while read -r n line; do
      unit=$(journalctl -u "aitbc-*" --since "-2 min" --no-pager -o cat -g "$line" -n1 --field=_SYSTEMD_UNIT 2>/dev/null | head -1)
      printf "{\"host\":\"'"$h"'\",\"unit\":\"%s\",\"count\":%s,\"pattern\":%s}\n" "${unit:-?}" "$n" "$(printf "%s" "$line" | python3 -c "import json,sys;print(json.dumps(sys.stdin.read()[:200]))")"
    done' >> "$OUT" 2>/dev/null
    ssh "$h" 'curl -sf --max-time 10 "http://127.0.0.1:9090/api/v1/alerts" | python3 -c "import json,sys;[print(json.dumps({\"host\":\"'"$h"'\",\"alert\":a[\"labels\"][\"alertname\"],\"sev\":a[\"labels\"].get(\"severity\")})) for a in json.load(sys.stdin)[\"data\"][\"alerts\"] if a[\"state\"]==\"firing\"]" 2>/dev/null' >> "$OUT" 2>/dev/null
  done
}
case "$MODE" in
  --sweep) sweep_once; tail -5 "$OUT" 2>/dev/null || true;;
  --follow) while :; do sweep_once; sleep "$INTERVAL"; done;;
  *) echo "usage: watch.sh --sweep|--follow"; exit 64;;
esac
