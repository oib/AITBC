#!/bin/bash
# #1290: weekly-ish hole scan for bridge_block_header.
#
# The header mirror is a derived cache of the block table; a persisted hole
# (missing height in 0..max) means batches were dropped, not merely lagged.
# Tip lag is transient — this scan checks sequence completeness, which only
# breaks on real loss. Exits 1 on any hole so the failed unit IS the alert
# (same convention as aitbc-chain-isolation-monitor).
#
# Read-only: opens each chain.db with sqlite3 in immutable-ish mode? No —
# plain read queries; WAL readers do not block the writer.

set -euo pipefail

TAG="aitbc-bridge-hole-scan"
DATA_DIR="${AITBC_DATA_DIR:-/var/lib/aitbc/data}"

log() { logger -t "$TAG" -p "user.$1" -- "$2"; echo "[$1] $2"; }

rc=0
shopt -s nullglob
for db in "$DATA_DIR"/*/chain.db; do
    [ -f "$db" ] || continue
    # One row per chain_id: count vs contiguous range. uix_bridge_block_
    # chain_height guarantees no duplicate heights, so count < hi-lo+1
    # (or lo != 0) means a persisted hole.
    out=$(sqlite3 "$db" "
        SELECT chain_id, COUNT(*), MIN(height), MAX(height)
        FROM bridge_block_header GROUP BY chain_id;" 2>/dev/null) || {
        log err "cannot read $db"
        rc=1
        continue
    }
    [ -n "$out" ] || log warning "empty bridge_block_header in $db (pre-bridge era or wiped?)"
    while IFS='|' read -r chain_id n lo hi; do
        [ -n "$chain_id" ] || continue
        missing=$((hi + 1 - lo - n))
        if [ "$lo" != "0" ] || [ "$missing" != "0" ]; then
            log err "HOLE $db chain=$chain_id rows=$n range=$lo..$hi missing=$missing"
            rc=1
        else
            log info "ok $db chain=$chain_id rows=$n range=0..$hi"
        fi
    done <<< "$out"
done
exit "$rc"
