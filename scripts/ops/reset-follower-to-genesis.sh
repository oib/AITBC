#!/bin/bash
# Reset an AITBC follower to the current fork chain database.
#
# This script is intended for the post-fork AITBC chain. The hub exposes a
# consistent, read-only SQLite snapshot of the fork database at /agent/chain.db.
# The local chain database is replaced with that snapshot and the follower starts
# from the fork head (which may already contain the genesis and several blocks).
#
# Usage (run as root on the follower):
#   sudo bash reset-follower-to-genesis.sh
#
# Override the source with CHAIN_DB_URL or a local CHAIN_DB_FILE:
#   CHAIN_DB_FILE=/path/to/chain.db bash reset-follower-to-genesis.sh
#
# Set STATE_TRANSITION_V2_HEIGHT=0 unless already configured.

set -euo pipefail

CHAIN_ID="${CHAIN_ID:-ait-hub.aitbc.bubuit.net}"
HUB="${HUB:-hub.aitbc.bubuit.net}"
CHAIN_DB_URL="${CHAIN_DB_URL:-http://${HUB}/agent/chain.db}"
CHAIN_DB_FILE="${CHAIN_DB_FILE:-}"
DB_DIR="${DB_DIR:-/var/lib/aitbc/data}"
DB="${DB_DIR}/${CHAIN_ID}/chain.db"
UNITS="aitbc-blockchain-node aitbc-blockchain-rpc"
ENV_FILE="/etc/aitbc/blockchain.env"

# Stop the local blockchain services before touching the database.
for unit in $UNITS; do
    if systemctl is-active --quiet "$unit"; then
        echo "Stopping $unit"
        systemctl stop "$unit" || true
    fi
done

# Download the fork chain DB from the hub unless a local file is provided.
if [ -z "$CHAIN_DB_FILE" ]; then
    CHAIN_DB_FILE="/tmp/aitbc-chain-${CHAIN_ID}.db"
    echo "Downloading fork chain DB from $CHAIN_DB_URL"
    if ! curl -fsSL "$CHAIN_DB_URL" -o "$CHAIN_DB_FILE"; then
        echo "Failed to download fork chain DB from $CHAIN_DB_URL" >&2
        exit 1
    fi
fi

[ -f "$CHAIN_DB_FILE" ] || { echo "No chain DB file: $CHAIN_DB_FILE" >&2; exit 1; }

# Preserve the old chain DB in case the operator needs to revert.
timestamp=$(date +%Y%m%d-%H%M%S)
if [ -f "$DB" ]; then
    backup="${DB}.pre-reset.${timestamp}"
    cp -p "$DB" "$backup"
    echo "Old chain DB saved to $backup"
    rm -f "$DB"
fi

# Remove stale WAL/SHM files from the previous database, if any.
rm -f "${DB}"-wal "${DB}"-shm

# Install the fork chain DB.
install -D -m 0640 -o aitbc -g aitbc "$CHAIN_DB_FILE" "$DB"
echo "Installed fork chain DB for $CHAIN_ID"

# Ensure the version gate is configured for the v2 fork.
if [ -f "$ENV_FILE" ]; then
    if ! grep -qE '^STATE_TRANSITION_V2_HEIGHT=' "$ENV_FILE"; then
        echo "STATE_TRANSITION_V2_HEIGHT=0" >> "$ENV_FILE"
        echo "Set STATE_TRANSITION_V2_HEIGHT=0 in $ENV_FILE"
    fi
fi

for unit in $UNITS; do
    echo "Starting $unit"
    systemctl start "$unit" || true
    printf "  %-26s %s\n" "$unit" "$(systemctl is-active "$unit" 2>/dev/null)"
done

echo "Follower reset complete. Watch the sync:"
echo "  journalctl -u aitbc-blockchain-node -f | grep -E 'imported|rejected|head'"
