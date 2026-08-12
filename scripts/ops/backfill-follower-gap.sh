#!/bin/bash
# Backfill the unverifiable block range on a follower so it can resume validated sync.
#
# V23-52/V23-54 context. The hub signed blocks 93,275-105,626 with a key that is not the
# proposer they declare, and 105,627 carries no signature at all. A follower that validates
# signatures -- correctly -- can never import that range, so it sits at 93,274 forever while
# the hub advances. Blocks 105,628+ are signed correctly and verify.
#
# This writes exactly the range that cannot verify, straight into the database, and lets
# normal validated sync take everything from 105,628 on. The manual trust decision is
# therefore scoped to the blocks that provably cannot be checked, and nothing else.
#
# It is safe to do here only because the range is empty:
#   - 0 transactions across all 12,353 blocks
#   - state_root identical at 93,274, 105,627 and 105,628
# so no balance moves and the local account state is already correct for the hub's tip.
# The script re-verifies both facts and refuses to write if either stops being true.
#
# Usage:  sudo bash scripts/ops/backfill-follower-gap.sh
#         sudo DRY_RUN=1 bash scripts/ops/backfill-follower-gap.sh   # check only, no write

set -euo pipefail

CHAIN_ID="${CHAIN_ID:-ait-hub.aitbc.bubuit.net}"
DB="${DB:-/var/lib/aitbc/data/${CHAIN_ID}/chain.db}"
HUB="${HUB:-https://hub.aitbc.bubuit.net}"
ANCHOR="${ANCHOR:-105627}"   # last block that cannot verify; sync resumes at ANCHOR+1
DRY_RUN="${DRY_RUN:-0}"
PY="${PY:-/opt/aitbc/venv/bin/python}"

[ -f "$DB" ] || { echo "no such database: $DB" >&2; exit 1; }

echo "database : $DB"
echo "hub      : $HUB"
echo "anchor   : $ANCHOR (validated sync resumes at $((ANCHOR + 1)))"
echo

UNITS="aitbc-blockchain-node aitbc-blockchain-rpc"

# The exit handler restores the *intended* end state, not a diff of what this run changed.
# The first version restarted only units it had stopped itself, which meant that running it
# against services someone else had already stopped left them stopped -- while printing
# "Services restart on exit". That is exactly what happened the first time this ran: the
# backfill succeeded, the node stayed down, and the follower sat at the anchor with the hub
# 27 blocks ahead until someone noticed. After this script completes the node must be
# running, because resuming sync is the entire point of it.
cleanup() {
    local unit
    for unit in $UNITS; do
        if [ "$(systemctl is-enabled "$unit" 2>/dev/null)" = "masked" ]; then
            echo "leaving $unit alone (masked)"
            continue
        fi
        systemctl start "$unit" || echo "  ! failed to start $unit -- start it by hand"
        printf "  %-26s %s\n" "$unit" "$(systemctl is-active "$unit" 2>/dev/null)"
    done
}
trap cleanup EXIT

# A dry run must not touch the running system. It only reads, so it neither stops services
# nor writes a backup -- the first version did both, taking the node down and leaving a 72 MB
# copy behind for a check that changes nothing.
if [ "$DRY_RUN" = "1" ]; then
    trap - EXIT
    echo "DRY_RUN=1 -- not stopping services, not backing up"
    echo
else
    for unit in $UNITS; do
        if systemctl is-active --quiet "$unit"; then
            echo "stopping $unit"
            systemctl stop "$unit"
        else
            echo "$unit already stopped"
        fi
    done

    BACKUP="${DB}.bak-$(date +%Y%m%d-%H%M%S)"
    echo "backing up -> $BACKUP"
    "$PY" - "$DB" "$BACKUP" <<'PYBACKUP'
import sqlite3, sys
src, dst = sqlite3.connect(sys.argv[1]), sqlite3.connect(sys.argv[2])
src.backup(dst)
dst.close(); src.close()
PYBACKUP
    echo "backup size: $(stat -c%s "$BACKUP") bytes"
    echo
fi

DRY_RUN="$DRY_RUN" "$PY" - "$DB" "$CHAIN_ID" "$HUB" "$ANCHOR" <<'PYMAIN'
import json, os, sqlite3, sys, urllib.parse, urllib.request

db, chain_id, hub, anchor = sys.argv[1], sys.argv[2], sys.argv[3], int(sys.argv[4])
dry_run = os.environ.get("DRY_RUN") == "1"

con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
head, head_hash, head_root = con.execute(
    "select height, hash, state_root from block where chain_id = ? order by height desc limit 1",
    (chain_id,),
).fetchone()
con.close()
print(f"  local head: {head}")

if head >= anchor:
    print(f"  nothing to do -- local head is already at or past the anchor ({anchor})")
    raise SystemExit(0)

blocks, start, step = [], head + 1, 2000
while start <= anchor:
    stop = min(start + step - 1, anchor)
    query = urllib.parse.urlencode(
        {"start": start, "end": stop, "chain_id": chain_id, "include_tx": "false"}
    )
    with urllib.request.urlopen(f"{hub}/rpc/blocks-range?{query}", timeout=90) as response:
        blocks.extend(json.load(response).get("blocks", []))
    start = stop + 1

blocks.sort(key=lambda b: b["height"])
print(f"  fetched   : {len(blocks)} blocks")

# Nothing is written unless every one of these holds.
problems = []
if [b["height"] for b in blocks] != list(range(head + 1, anchor + 1)):
    problems.append("heights are not a contiguous run from the local head to the anchor")

parent = head_hash
for block in blocks:
    if block["parent_hash"] != parent:
        problems.append(f"parent linkage breaks at {block['height']}")
        break
    parent = block["hash"]

carrying = [b["height"] for b in blocks if (b.get("tx_count") or 0)]
if carrying:
    problems.append(f"{len(carrying)} block(s) carry transactions, first at {carrying[0]} -- "
                    "state would diverge and this script is not safe")

roots = {b.get("state_root") for b in blocks} | {head_root}
if len(roots) != 1:
    problems.append(f"state_root is not constant across the range ({len(roots)} distinct) -- "
                    "the local account state would not match the hub's")

if problems:
    print("  REFUSING TO WRITE:")
    for problem in problems:
        print(f"    ! {problem}")
    raise SystemExit(1)

print("  checks    : contiguous, linked, 0 transactions, state_root constant")

if dry_run:
    print("  DRY_RUN=1 -- no rows written")
    raise SystemExit(0)

rows = [
    (
        chain_id,
        b["height"],
        b["hash"],
        b["parent_hash"],
        b["proposer"],
        b["timestamp"].replace("T", " "),
        b.get("tx_count") or 0,
        b.get("state_root"),
        None,
        b.get("signature") or "",   # record what the hub served, wrong-key or empty
    )
    for b in blocks
]

con = sqlite3.connect(db)
try:
    with con:
        con.executemany(
            "INSERT INTO block (chain_id, height, hash, parent_hash, proposer, timestamp,"
            " tx_count, state_root, block_metadata, signature) VALUES (?,?,?,?,?,?,?,?,?,?)",
            rows,
        )
finally:
    con.close()
print(f"  inserted  : {len(rows)} rows")

con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
new_head, = con.execute(
    "select max(height) from block where chain_id = ?", (chain_id,)
).fetchone()
dupes, = con.execute(
    "select count(*) from (select height from block where chain_id = ? group by height"
    " having count(*) > 1)", (chain_id,)
).fetchone()
breaks, previous = 0, None
for _, block_hash, parent_hash in con.execute(
    "select height, hash, parent_hash from block where chain_id = ? order by height", (chain_id,)
):
    if previous is not None and parent_hash != previous:
        breaks += 1
    previous = block_hash
con.close()

print(f"  head now  : {new_head}")
print(f"  duplicates: {dupes}")
print(f"  linkage breaks across the whole chain: {breaks}")
if dupes or breaks:
    print("  ! verification failed -- restore the backup printed above")
    raise SystemExit(1)
PYMAIN

echo
if [ "$DRY_RUN" = "1" ]; then
    echo "done (dry run). Nothing was stopped, backed up, or written."
else
    echo "done. Services are started by the exit handler below -- check the state it prints."
    echo "Watch the node pick up from $((ANCHOR + 1)):"
    echo "  journalctl -u aitbc-blockchain-node -f | grep -Ei 'import|rejected'"
fi
