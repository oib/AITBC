#!/usr/bin/env bash
# LANE: parallel
# MODE: loop
# Committed-table / aux-root spot-diff across hosts via fleet URLs.
set -euo pipefail
. "$(dirname "$0")/../lib.sh"
serial_check || exit 75

HOSTS="${STRESS_HOSTS:-hub hub1 node0 node1 node2}"
declare -A aux head
for h in $HOSTS; do
  url="$(stress_rpc_url "$h")"
  [ "$(hostname -s)" = "$h" ] || [ "$(hostname)" = "$h" ] && url="http://127.0.0.1:8202"
  read -r hh aa <<<"$(curl -sf --max-time 10 "$url/rpc/status" | python3 -c 'import json,sys; d=json.load(sys.stdin); print(d.get("height",-1), d.get("last_block_hash","?"))' 2>/dev/null || echo "-1 ?")"
  head[$h]=$hh; aux[$h]=$aa
done
ref="${aux[hub]:-?}"; bad=""
for h in $HOSTS; do
  [ "${head[$h]:--1}" -lt 0 ] && fail parity "host $h unreachable"
  [ "${aux[$h]}" != "$ref" ] && bad="$bad $h(${aux[$h]} vs hub $ref)"
done
[ -n "$bad" ] && fail aux-root "last_block_hash divergence:$bad"
echo "parity ok: aux_root=$ref"
ok ""
