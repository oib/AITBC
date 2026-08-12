#!/bin/bash
# Reset an AITBC follower to the hub's new genesis block.
#
# This is a hard-fork reset: the local chain database is deleted and the
# follower starts from height 0 using the provided genesis.json file.
#
# Usage (run as root on the follower):
#   sudo GENESIS_FILE=/path/to/new-genesis.json bash reset-follower-to-genesis.sh
#
# The GENESIS_FILE can be copied from the hub with:
#   scp root@hub.aitbc.bubuit.net:/var/lib/aitbc/data/ait-hub.aitbc.bubuit.net/genesis.json ./new-genesis.json

set -euo pipefail

CHAIN_ID="${CHAIN_ID:-ait-hub.aitbc.bubuit.net}"
GENESIS_FILE="${GENESIS_FILE:-/var/lib/aitbc/data/${CHAIN_ID}/genesis.json}"
DB_DIR="${DB_DIR:-/var/lib/aitbc/data}"
DB="${DB_DIR}/${CHAIN_ID}/chain.db"
UNITS="aitbc-blockchain-node aitbc-blockchain-rpc"

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
