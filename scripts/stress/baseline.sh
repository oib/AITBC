#!/usr/bin/env bash
# baseline.sh — snapshot heads/mempool/alerts/journal errs → stress-baseline.json
set -euo pipefail
HOSTS="${STRESS_HOSTS:-hub hub1 node0 node1 node2}"
OUT="${STRESS_STATE_DIR:-/var/lib/aitbc/stress-state}/stress-baseline.json"
mkdir -p "$(dirname "$OUT")" 2>/dev/null || true
rows=()
for h in $HOSTS; do
  row=$(ssh "$h" 'h=$(curl -sf --max-time 10 http://127.0.0.1:8202/rpc/status|python3 -c "import json,sys;print(json.load(sys.stdin).get(\"height\",-1))" 2>/dev/null||echo -1); mp=$(curl -sf --max-time 10 http://127.0.0.1:8202/rpc/mempool|python3 -c "import json,sys;print(len(json.load(sys.stdin).get(\"transactions\",json.load(sys.stdin) if isinstance(json.load(sys.stdin),list) else [])))" 2>/dev/null||echo -1); al=$(curl -sf --max-time 10 "http://127.0.0.1:9090/api/v1/alerts"|python3 -c "import json,sys;print(len(json.load(sys.stdin)[\"data\"][\"alerts\"]))" 2>/dev/null||echo -1); je=$(journalctl -u "aitbc-*" --since "1 hour ago" -p err --no-pager 2>/dev/null|wc -l); printf "{\"height\":%s,\"mempool\":%s,\"alerts\":%s,\"journal_err_1h\":%s}" "$h" "$mp" "$al" "$je"' 2>/dev/null || echo '{"error":"unreachable"}')
  rows+=("{\"host\":\"$h\",\"baseline\":$row}")
done
printf '{"ts":"%s","hosts":[%s]}\n' "$(date -u +%FT%TZ)" "$(IFS=,; echo "${rows[*]}")" | tee "$OUT"
