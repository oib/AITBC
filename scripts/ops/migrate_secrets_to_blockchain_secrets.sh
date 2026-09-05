#!/bin/bash
# AITBC cluster-wide secrets migration
# Run as root on a live node after updating the systemd service files.
# This script moves cluster-wide secret variables from the public blockchain.env
# into blockchain-secrets.env without touching node-specific private keys.

set -euo pipefail

SECRETS_FILE=/etc/aitbc/blockchain-secrets.env
PUBLIC_FILE=/etc/aitbc/blockchain.env
BACKUP_DIR=/etc/aitbc/.secret-migration-backup-$(date +%s)

mkdir -p "$BACKUP_DIR"
[ -f "$PUBLIC_FILE" ] && cp -a "$PUBLIC_FILE" "$BACKUP_DIR/"
[ -f "/etc/aitbc/node.env" ] && cp -a /etc/aitbc/node.env "$BACKUP_DIR/"
for f in /etc/aitbc/*.env; do
    [ -f "$f" ] && cp -a "$f" "$BACKUP_DIR/"
done

migrate_var() {
    local var="$1"
    local src="$2"
    if [ -f "$src" ] && grep -qE "^${var}=" "$src" 2>/dev/null; then
        local val
        val=$(grep -E "^${var}=" "$src" | head -n1 | cut -d= -f2-)
        if ! grep -qE "^${var}=" "$SECRETS_FILE" 2>/dev/null; then
            echo "${var}=${val}" >> "$SECRETS_FILE"
            echo "Migrated ${var} from ${src} -> ${SECRETS_FILE}"
        else
            echo "Skipped ${var} (already in ${SECRETS_FILE})"
        fi
        # Remove from the public file or per-service file.
        sed -i "/^${var}=/d" "$src"
        echo "Removed ${var} from ${src}"
    fi
}

umask 077
touch "$SECRETS_FILE"
chown root:aitbc "$SECRETS_FILE"
chmod 600 "$SECRETS_FILE"

# Always remove cluster-wide secrets from the public blockchain.env.
for var in REDIS_URL GOSSIP_BROADCAST_URL SYNC_REDIS_URL API_KEY_HASH_SECRET BLOCKCHAIN_RPC_API_KEY; do
    migrate_var "$var" "$PUBLIC_FILE"
done

# Optionally remove duplicates from node.env / %N.env when the user passes -f.
FORCE=false
if [ "${1:-}" = "-f" ]; then
    FORCE=true
fi

if [ "$FORCE" = true ]; then
    for var in REDIS_URL GOSSIP_BROADCAST_URL SYNC_REDIS_URL API_KEY_HASH_SECRET BLOCKCHAIN_RPC_API_KEY; do
        migrate_var "$var" /etc/aitbc/node.env
    done
    for f in /etc/aitbc/aitbc-*.env; do
        [ -f "$f" ] || continue
        for var in REDIS_URL GOSSIP_BROADCAST_URL SYNC_REDIS_URL API_KEY_HASH_SECRET BLOCKCHAIN_RPC_API_KEY; do
            migrate_var "$var" "$f"
        done
    done
fi

# The public file should be world-readable once the secrets are gone.
chmod 644 "$PUBLIC_FILE"

echo "Migration complete. Backups saved to ${BACKUP_DIR}"
