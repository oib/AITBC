#!/usr/bin/env bash
# LANE: parallel
# MODE: loop
# Committed-table / aux-root spot-diff across hosts.
#  1. aux_state_root at the min common sealed height via /rpc/blocks/<H>
#     (fleet URLs; local rpc for self — Refs #720).
#  2. Committed-table row-count + digest diff via side-root-probe.py
#     --canonical --block-version 18 over each probe host's chain.db
#     (read-only sqlite). STRESS_PROBE_HOSTS overrides the probe set.
# An aux_state_root or committed-table mismatch is priority-one.
set -euo pipefail
. "$(dirname "$0")/../lib.sh"
serial_check || exit 75

HOSTS="${STRESS_HOSTS:-hub hub1 node0 node1 node2}"
url_for() {  # url_for <host>
  local u; u="$(stress_rpc_url "$1")"
  { [ "$(hostname -s)" = "$1" ] || [ "$(hostname)" = "$1" ]; } && u="http://127.0.0.1:8202"
  echo "$u"
}

# --- leg 1: aux_state_root at min common height ------------------------------
declare -A aux blk
minh=999999999
for h in $HOSTS; do
  hh=$(curl -sf --max-time 10 "$(url_for "$h")/rpc/status" | python3 -c 'import json,sys; print(json.load(sys.stdin).get("height",-1))' 2>/dev/null || echo -1)
  [ "$hh" -lt 0 ] && fail parity "host $h unreachable"
  [ "$hh" -lt "$minh" ] && minh=$hh
done
H="${STRESS_AUX_HEIGHT:-$minh}"
for h in $HOSTS; do
  read -r aa bb <<<"$(curl -sf --max-time 10 "$(url_for "$h")/rpc/blocks/$H" \
    | python3 -c 'import json,sys; d=json.load(sys.stdin); print(d.get("aux_state_root","?"), d.get("hash","?"))' 2>/dev/null || echo "? ?")"
  aux[$h]=$aa; blk[$h]=$bb
done
ref="${aux[hub]:-?}"; bad=""
for h in $HOSTS; do
  [ "${aux[$h]}" != "$ref" ] && bad="$bad $h(aux=${aux[$h]} blk=${blk[$h]:0:14} vs hub $ref)"
done
[ -n "$bad" ] && fail aux-root "aux_state_root@$H divergence:$bad"
echo "aux parity ok @h$H: $ref"

# --- leg 2: committed-table row-count/digest diff ----------------------------
# side-root-probe is read-only by construction (sqlite mode=ro); run it
# on-host via ssh and compare per-table rows:digest across the probe set.
PROBE_HOSTS="${STRESS_PROBE_HOSTS:-hub1 node1 node2}"
PROBE='for d in /var/lib/aitbc/data/bc-2/chain.db /opt/aitbc/data/bc-2/chain.db; do [ -f "$d" ] && break; done; cd /opt/aitbc && venv/bin/python scripts/ops/side-root-probe.py --db "$d" --canonical --block-version 18 --json'
declare -A trows tdig
refhost=""
for h in $PROBE_HOSTS; do
  out=$(stress_ssh "$h" "$PROBE" 2>/dev/null) || fail probe "side-root-probe failed on $h"
  line=$(printf '%s' "$out" | python3 -c '
import json,sys
d=json.loads(sys.stdin.read())
cs=d.get("committed_set",{})
print(";".join(sorted(f"{t}={e.get(\"rows\",\"?\")}:{e.get(\"digest\",e.get(\"status\",\"?\"))}" for t,e in cs.items())))
' 2>/dev/null)
  [ -n "$line" ] || fail probe "no committed_set from $h"
  if [ -z "$refhost" ]; then refhost=$h; refline="$line";
  elif [ "$line" != "$refline" ]; then
    fail aux-root "committed-table divergence $h vs $refhost@h$H: $line != $refline"
  fi
done
echo "row-count/digest parity ok across: $PROBE_HOSTS"
ok ""
