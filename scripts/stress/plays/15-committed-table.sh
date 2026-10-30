#!/usr/bin/env bash
# LANE: parallel
# MODE: loop
# Committed-table / aux-root spot-diff across hosts (D family):
# head parity + aux_state_root equality at the common tip.
set -euo pipefail
. "$(dirname "$0")/../lib.sh"
serial_check || exit 75

HOSTS="${STRESS_HOSTS:-hub hub1 node0 node1 node2}"
declare -A aux head
for h in $HOSTS; do
  read -r hh aa <<<"$(ssh "$h" 'curl -sf --max-time 10 http://127.0.0.1:8202/rpc/status | python3 -c "import json,sys; d=json.load(sys.stdin); print(d.get(\"height\",-1), d.get(\"aux_state_root\",d.get(\"state_root\",\"?\")))" 2>/dev/null || echo "-1 ?"')"
  head[$h]=$hh; aux[$h]=$aa
done
ref="${aux[hub]:-?}"; min=${head[hub]:-0}
bad=""
for h in $HOSTS; do
  [ "${head[$h]:--1}" -lt 0 ] && fail parity "host $h unreachable"
  [ "${aux[$h]}" != "$ref" ] && bad="$bad $h(${aux[$h]} vs hub $ref)"
done
[ -n "$bad" ] && fail aux-root "aux_state_root divergence:$bad"
echo "parity ok: heads ~${min}, aux_root=$ref"
ok ""
