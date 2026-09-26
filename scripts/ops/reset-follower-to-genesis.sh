#!/bin/bash
# Reset an AITBC follower to the current fork chain database.
#
# This script is intended for the post-fork AITBC chain. The local chain
# database is replaced with a consistent snapshot of the fork database and the
# follower starts from the fork head (which may already contain the genesis and
# several blocks).
#
# The hub does NOT serve a public /agent/chain.db endpoint (V23-58). The
# snapshot must come from an operator-provided source:
#   - a local file:        CHAIN_DB_FILE=/path/to/chain.db
#   - an authenticated URL: CHAIN_DB_URL=https://operator-endpoint/chain.db
#
# Usage (run as root on the follower):
#   sudo CHAIN_DB_FILE=/path/to/chain.db bash reset-follower-to-genesis.sh
#
# Set STATE_TRANSITION_V2_HEIGHT=0 unless already configured.

set -euo pipefail

CHAIN_ID="${CHAIN_ID:-ait-localnet}"
# No default download URL: the hub does not publish a public chain.db. Set
# CHAIN_DB_URL to an operator-provided (authenticated) snapshot endpoint, or
# pass a local CHAIN_DB_FILE instead.
CHAIN_DB_URL="${CHAIN_DB_URL:-}"
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

# Download the fork chain DB unless a local file is provided.
if [ -z "$CHAIN_DB_FILE" ]; then
    if [ -z "$CHAIN_DB_URL" ]; then
        echo "No chain DB source: set CHAIN_DB_FILE=/path/to/chain.db or" >&2
        echo "CHAIN_DB_URL=<operator-provided snapshot URL>." >&2
        echo "The hub does not serve a public /agent/chain.db (V23-58)." >&2
        exit 1
    fi
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
