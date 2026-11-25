#!/bin/bash
# Product-side half of the #2950 cold-start race pin: a backup leg must
# survive a chain.db that is still locked while its node recovers.
#
# The original the companion operations coldstart database pin also exercises the
# OPS bridge-header-hole scan and moves with that scan in the repo split.
# This file keeps the PRODUCT backup coverage in the product repo. Everything
# runs in mktemp scratch; no real /var, /etc, PostgreSQL, or systemd path is
# touched. Exits non-zero on any failed assertion.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
BACKUP="$REPO_ROOT/scripts/maintenance/aitbc-backup.sh"
SBX="$(mktemp -d /tmp/backup-coldstart.XXXXXX)"
# The cleanup is best-effort by definition; xargs/kill failure must not turn
# a green pin red in the trap.
trap 'rm -rf "$SBX"; jobs -p | xargs -r kill 2>/dev/null || true' EXIT

FAILS=0
pass() { echo "  PASS: $1"; }
fail() { echo "  FAIL: $1"; FAILS=$((FAILS + 1)); }

make_chain_db() { # path — rollback-journal db with the table the dump asserts
    mkdir -p "$(dirname "$1")"
    sqlite3 "$1" 2>/dev/null <<'SQL'
PRAGMA journal_mode=delete;
CREATE TABLE bridge_block_header(chain_id TEXT, height INTEGER, hash TEXT);
CREATE TABLE block(height INTEGER, hash TEXT);
SQL
    sqlite3 "$1" "INSERT INTO bridge_block_header
        SELECT 'bc-test', value, 'h' || value FROM generate_series(0, 9, 1);" 2>/dev/null \
    || python3 - "$1" <<'PY'
import sqlite3, sys
con = sqlite3.connect(sys.argv[1])
con.executemany("INSERT INTO bridge_block_header VALUES (?,?,?)",
                [("bc-test", i, f"h{i}") for i in range(10)])
con.commit(); con.close()
PY
}

# Hold an exclusive write lock on $1 for $2 seconds. The ready file proves the
# lock is held before the backup starts; without it a fast run can finish
# before python has even opened the db.
lock_db_for() {
    local ready
    ready="$(mktemp -u "$SBX/lockready.XXXXXX")"
    python3 - "$1" "$2" "$ready" <<'PY' &
import sqlite3, sys, time
con = sqlite3.connect(sys.argv[1], timeout=30, isolation_level=None)
con.execute("BEGIN EXCLUSIVE")
con.execute("CREATE TABLE IF NOT EXISTS lockprobe(x)")
open(sys.argv[3], "w").write("held")
time.sleep(float(sys.argv[2]))
con.rollback()
con.close()
PY
    for _ in 1 2 3 4 5 6 7 8 9 10; do
        [ -f "$ready" ] && return 0
        sleep 0.3
    done
    echo "harness error: lock never acquired" >&2
    return 1
}

mkdir -p "$SBX/data/bc-2" "$SBX/svc" "$SBX/base"
make_chain_db "$SBX/data/bc-2/chain.db"
printf 'CHAIN_ID=bc-2\n' > "$SBX/blockchain.env"

run_backup() { # extra-env... — every path the backup touches redirected to scratch
    env \
        BACKUP_BASE="$SBX/base" \
        CHAIN_DB_DIR="$SBX/data" \
        SVC_DB_DIR="$SBX/svc" \
        BLOCKCHAIN_ENV="$SBX/blockchain.env" \
        PGHOST="$SBX/no-pg" \
        BACKUP_DB_SQLITE_TIMEOUT_MS=1000 \
        "$@" bash "$BACKUP"
}

echo "== backup: cold-start race"

# Locked-then-released chain.db inside the retry budget: the chain artifact is
# a valid dump (the fixed behavior).
lock_db_for "$SBX/data/bc-2/chain.db" 6
BACKUP_DB_ATTEMPTS=5 BACKUP_DB_RETRY_SLEEP=2 run_backup >/dev/null 2>&1 || true  # pg/key legs are scratch-host noise; the chain artifact is the assertion
snap=$(ls -d "$SBX/base"/*/ 2>/dev/null | head -1)
if [ -n "$snap" ] && [ -f "${snap}chain_bc-2_chain.db.gz" ] && zcat "${snap}chain_bc-2_chain.db.gz" 2>/dev/null | grep -q "bridge_block_header"; then
    pass "locked-then-released chain.db lands a valid dump artifact"
else
    fail "locked-then-released chain.db lands a valid dump artifact"
fi
wait 2>/dev/null

# Same race pinned to one attempt (the pre-fix behavior): the artifact is
# absent. This mutation control proves the first case covers the retry logic.
rm -rf "$SBX/base"; mkdir -p "$SBX/base"
lock_db_for "$SBX/data/bc-2/chain.db" 6
BACKUP_DB_ATTEMPTS=1 run_backup >/dev/null 2>&1 || true  # pg/key legs are scratch-host noise; the chain artifact is the assertion
snap=$(ls -d "$SBX/base"/*/ 2>/dev/null | head -1)
if [ -n "$snap" ] && [ -f "${snap}chain_bc-2_chain.db.gz" ]; then
    fail "1-attempt budget loses the chain artifact (mutation control)"
else
    pass "1-attempt budget loses the chain artifact (mutation control)"
fi
wait 2>/dev/null

echo
if [ "$FAILS" -gt 0 ]; then
    echo "FAILED: $FAILS assertion(s)"
    exit 1
fi
echo "all assertions passed"
