#!/bin/bash
# Reset an AITBC follower to a recent snapshot from the hub.
#
# This is the recommended recovery path for a diverged follower. It is safer
# than `reset-follower-to-genesis.sh` because it does not replay the entire
# chain from genesis under current state-transition rules.
#
# Usage (run as root on the follower):
#   sudo bash /opt/aitbc/scripts/ops/reset-follower-to-snapshot.sh
#
# Environment:
#   CHAIN_ID   - chain id (default: ait-localnet)
#   HUB        - hub host for snapshot (default: hub.aitbc.invalid)
#   SSH_USER   - ssh user on hub (default: root)
#   DB_DIR     - local data directory (default: /var/lib/aitbc/data)

set -euo pipefail

CHAIN_ID="${CHAIN_ID:-ait-localnet}"
HUB="${HUB:-hub.aitbc.invalid}"
SSH_USER="${SSH_USER:-root}"
DB_DIR="${DB_DIR:-/var/lib/aitbc/data}"
DB="${DB_DIR}/${CHAIN_ID}/chain.db"
UNITS="aitbc-blockchain-node aitbc-blockchain-rpc"
SNAPSHOT_REMOTE="/tmp/aitbc-follower-snapshot-${CHAIN_ID}.db"
TIMESTAMP=$(date +%Y%m%d-%H%M%S)

# Stop local blockchain services before touching the database.
for unit in $UNITS; do
    if systemctl is-active --quiet "$unit"; then
        echo "Stopping $unit"
        systemctl stop "$unit"
    fi
done

# Back up the local DB in case the operator needs to revert. `sqlite3 .backup` reads through the
# WAL, so the copy is whole even if a service was killed instead of stopped cleanly: on a host
# running with DB_KEEPER_CONNECTION the recent commits can sit in chain.db-wal, and a bare cp of
# chain.db alone would drop them. The raw-copy fallback keeps the WAL files next to the copy.
if [ -f "$DB" ]; then
    backup="${DB}.pre-snapshot.${TIMESTAMP}"
    if sqlite3 "$DB" ".backup '${backup}'"; then
        chown --reference="$DB" "$backup" || true
        chmod --reference="$DB" "$backup" || true
    else
        echo "sqlite3 .backup failed; keeping a raw copy of the database and its WAL files" >&2
        cp -p "$DB" "$backup"
        for suffix in -wal -shm; do
            if [ -f "${DB}${suffix}" ]; then cp -p "${DB}${suffix}" "${backup}${suffix}"; fi
        done
    fi
    echo "Local chain DB saved to $backup"
fi

# Create a consistent online backup on the hub without stopping its RPC.
echo "Creating online backup on $HUB ..."
if ! ssh "${SSH_USER}@${HUB}" "sqlite3 /var/lib/aitbc/data/${CHAIN_ID}/chain.db \".backup ${SNAPSHOT_REMOTE}\"" ; then
    echo "Failed to create online backup on $HUB" >&2
    exit 1
fi

# Verify the snapshot head before copying.
echo "Verifying snapshot head on $HUB ..."
hub_head=$(ssh "${SSH_USER}@${HUB}" "sqlite3 ${SNAPSHOT_REMOTE} 'SELECT height, hash FROM block WHERE chain_id=\"${CHAIN_ID}\" ORDER BY height DESC LIMIT 1'")
if [ -z "$hub_head" ]; then
    echo "Snapshot has no blocks for chain ${CHAIN_ID}" >&2
    exit 1
fi
echo "Hub snapshot head: $hub_head"

# Copy the snapshot to the follower.
mkdir -p "$(dirname "$DB")"
if command -v rsync >/dev/null 2>&1; then
    rsync -avz --progress "${SSH_USER}@${HUB}:${SNAPSHOT_REMOTE}" "${DB}.tmp"
else
    scp "${SSH_USER}@${HUB}:${SNAPSHOT_REMOTE}" "${DB}.tmp"
fi

# Clean up the remote temporary snapshot.
ssh "${SSH_USER}@${HUB}" "rm -f ${SNAPSHOT_REMOTE}" || true

# Verify the local copy has the same head as the remote snapshot.
local_head=$(sqlite3 "${DB}.tmp" "SELECT height, hash FROM block WHERE chain_id=\"${CHAIN_ID}\" ORDER BY height DESC LIMIT 1")
if [ "$hub_head" != "$local_head" ]; then
    echo "Snapshot copy head mismatch: remote=$hub_head local=$local_head" >&2
    rm -f "${DB}.tmp"
    exit 1
fi

# Atomically replace the local chain DB. The services are stopped, so any chain.db-wal / chain.db-shm
# on disk belongs to the OLD database: a killed process leaves them, and a host running with
# DB_KEEPER_CONNECTION keeps its WAL on disk by design. SQLite would replay those frames onto the
# new file and corrupt it, so they go first.
rm -f "${DB}-wal" "${DB}-shm"
mv -f "${DB}.tmp" "$DB"
chown aitbc:aitbc "$DB"
chmod 0640 "$DB"
echo "Installed snapshot at $DB (head $local_head)"

# Start services back up.
for unit in $UNITS; do
    echo "Starting $unit"
    systemctl start "$unit" || true
    printf "  %-26s %s\n" "$unit" "$(systemctl is-active "$unit" 2>/dev/null)"
done

echo "Follower snapshot reset complete. Watch the catch-up:"
echo "  journalctl -u aitbc-blockchain-node -f | grep -E 'imported|head|divergence'"
