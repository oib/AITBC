#!/bin/bash
# AITBC cluster-wide secrets migration
# Run as root on a live node after updating the systemd service files.
# This script moves cluster-wide secret variables from the public blockchain.env
# into blockchain-secrets.env without touching node-specific private keys.

set -euo pipefail

SECRETS_FILE=/etc/aitbc/blockchain-secrets.env
VALIDATOR_SECRETS_FILE=/etc/aitbc/validator-secrets.env
PUBLIC_FILE=/etc/aitbc/blockchain.env

# Consensus-signing keys are scoped to the blockchain services only
# (blockchain-node, -rpc, -p2p). Everything else is cluster-shared.
SIGNING_VARS="PROPOSER_KEY VALIDATOR_KEYS"
SHARED_VARS="REDIS_URL GOSSIP_BROADCAST_URL SYNC_REDIS_URL API_KEY_HASH_SECRET BLOCKCHAIN_RPC_API_KEY COORDINATOR_API_KEY SECRET_KEY JWT_SECRET GENESIS_PRIVATE_KEY BLOCKCHAIN_API_KEY"
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
    local dest="${3:-$SECRETS_FILE}"
    if [ -f "$src" ] && grep -qE "^${var}=" "$src" 2>/dev/null; then
        local val
        val=$(grep -E "^${var}=" "$src" | head -n1 | cut -d= -f2-)
        if ! grep -qE "^${var}=" "$dest" 2>/dev/null; then
            echo "${var}=${val}" >> "$dest"
            echo "Migrated ${var} from ${src} -> ${dest}"
        else
            echo "Skipped ${var} (already in ${dest})"
        fi
        # Remove from the public file or per-service file.
        sed -i "/^${var}=/d" "$src"
        echo "Removed ${var} from ${src}"
    fi
}

umask 077
touch "$SECRETS_FILE"
# The service runs as a non-root user in the aitbc group; 640 keeps
# the file private but readable to the service.
chown root:aitbc "$SECRETS_FILE"
chmod 640 "$SECRETS_FILE"

# Signing secrets are stricter: root-only, loaded only by the blockchain
# units (EnvironmentFile=-/etc/aitbc/validator-secrets.env).
touch "$VALIDATOR_SECRETS_FILE"
chown root:root "$VALIDATOR_SECRETS_FILE"
chmod 600 "$VALIDATOR_SECRETS_FILE"

# Always remove cluster-wide secrets from the public blockchain.env.
for var in $SHARED_VARS; do
    migrate_var "$var" "$PUBLIC_FILE"
done
for var in $SIGNING_VARS; do
    migrate_var "$var" "$PUBLIC_FILE" "$VALIDATOR_SECRETS_FILE"
done

# Re-scope signing keys that already landed in the shared file.
for var in $SIGNING_VARS; do
    migrate_var "$var" "$SECRETS_FILE" "$VALIDATOR_SECRETS_FILE"
done

# Optionally remove duplicates from node.env / %N.env when the user passes -f.
FORCE=false
if [ "${1:-}" = "-f" ]; then
    FORCE=true
fi

if [ "$FORCE" = true ]; then
    for var in $SHARED_VARS; do
        migrate_var "$var" /etc/aitbc/node.env
    done
    for var in $SIGNING_VARS; do
        migrate_var "$var" /etc/aitbc/node.env "$VALIDATOR_SECRETS_FILE"
    done
    for f in /etc/aitbc/aitbc-*.env; do
        [ -f "$f" ] || continue
        for var in $SHARED_VARS; do
            migrate_var "$var" "$f"
        done
        for var in $SIGNING_VARS; do
            migrate_var "$var" "$f" "$VALIDATOR_SECRETS_FILE"
        done
    done
fi

# The public file should be world-readable once the secrets are gone.
chmod 644 "$PUBLIC_FILE"

echo "Migration complete. Backups saved to ${BACKUP_DIR}"
