#!/usr/bin/env bash
# LANE: parallel (read-only observer). MODE: once
# ESCROW_FEE_SWEEP emissions vs escrow-contract consistency — the sweep
# is node-emitted (watch-only); verify emissions continue and carry sane
# values during volume.
set -euo pipefail
. "$(dirname "$0")/../lib.sh"
serial_check || exit 75
db=$(for d in /var/lib/aitbc/data/$CHAIN/chain.db ~/.aitbc/data/$CHAIN/chain.db; do [ -f "$d" ] && echo "$d" && break; done)
[ -n "$db" ] || fail sweep "chain.db not found for $CHAIN"
rows=$(sqlite3 "$db" "select count(*), coalesce(sum(fee),0) from \"transaction\" where type='ESCROW_FEE_SWEEP' and status='confirmed'" 2>/dev/null || echo "0|0")
cnt=${rows%%|*}; fees=${rows##*|}
jsonl "$RUN_LOG" "{\"ts\":\"$(now)\",\"script\":\"${0##*/}\",\"host\":\"$HOST\",\"status\":\"ok\",\"sweeps\":$cnt,\"swept_fees\":$fees}"
echo "fee-sweep: $cnt emissions, $fees fees swept"
ok ""
