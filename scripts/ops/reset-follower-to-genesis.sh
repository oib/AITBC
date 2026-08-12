#!/bin/bash
# Reset an AITBC follower to the hub's new genesis block.
#
# This is a hard-fork reset: the local chain database is deleted and the
# follower starts from height 0 using the provided genesis.json file.
#
# Usage (run as root on the follower):
#   sudo bash reset-follower-to-genesis.sh
#
# The script can either:
#   - Download the genesis from the public hub URL (default)
#   - Use a local file: GENESIS_FILE=/path/to/genesis.json bash reset-follower-to-genesis.sh
#
# The public genesis URL is:
#   http://hub.aitbc.bubuit.net/agent/genesis.json

set -euo pipefail

CHAIN_ID="${CHAIN_ID:-ait-hub.aitbc.bubuit.net}"
HUB="${HUB:-hub.aitbc.bubuit.net}"
GENESIS_URL="${GENESIS_URL:-http://${HUB}/agent/genesis.json}"
GENESIS_FILE="${GENESIS_FILE:-}"  # set to use a local file instead of downloading
DB_DIR="${DB_DIR:-/var/lib/aitbc/data}"
DB="${DB_DIR}/${CHAIN_ID}/chain.db"
UNITS="aitbc-blockchain-node aitbc-blockchain-rpc"

# Download from the hub unless a local file is provided
if [ -z "$GENESIS_FILE" ]; then
    GENESIS_FILE="/tmp/aitbc-genesis-${CHAIN_ID}.json"
    echo "Downloading genesis from $GENESIS_URL"
    if ! curl -fsSL "$GENESIS_URL" -o "$GENESIS_FILE"; then
        echo "Failed to download genesis from $GENESIS_URL" >&2
        exit 1
    fi
fi

[ -f "$GENESIS_FILE" ] || { echo "No genesis file: $GENESIS_FILE" >&2; exit 1; }

for unit in $UNITS; do
    if systemctl is-active --quiet "$unit"; then
        echo "Stopping $unit"
        systemctl stop "$unit"
    fi
done

# Preserve the old chain DB in case the operator needs to revert
timestamp=$(date +%Y%m%d-%H%M%S)
if [ -f "$DB" ]; then
    backup="${DB}.pre-reset.${timestamp}"
    cp -p "$DB" "$backup"
    echo "Old chain DB saved to $backup"
    rm -f "$DB"
fi

# Install the new genesis file
install -D -m 0640 -o aitbc -g aitbc "$GENESIS_FILE" "${DB_DIR}/${CHAIN_ID}/genesis.json"
echo "Installed new genesis for $CHAIN_ID"

for unit in $UNITS; do
    echo "Starting $unit"
    systemctl start "$unit" || true
    printf "  %-26s %s\n" "$unit" "$(systemctl is-active "$unit" 2>/dev/null)"
done

echo "Follower reset complete. Watch the sync:"
echo "  journalctl -u aitbc-blockchain-node -f | grep -E 'imported|rejected|head'"
