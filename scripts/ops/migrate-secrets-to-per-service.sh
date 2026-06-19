#!/bin/bash
# AITBC Secret Migration Script — v0.5.1
# Migrates shared /run/aitbc/secrets/.env to per-service /etc/aitbc/%N.env files
#
# Run as root during deployment

set -e

SECRETS_SOURCE="/run/aitbc/secrets/.env"
ETC_DIR="/etc/aitbc"

echo "=== AITBC Secret Migration ==="
echo "Source: $SECRETS_SOURCE"
echo "Target: $ETC_DIR/%N.env"
echo

# Ensure /etc/aitbc exists
mkdir -p "$ETC_DIR"
chmod 755 "$ETC_DIR"

# Function to extract a value from the source file
extract_value() {
    local key="$1"
    grep "^${key}=" "$SECRETS_SOURCE" 2>/dev/null | head -1 | cut -d= -f2-
}

# --- Coordinator API secrets ---
COORD_API_ENV="$ETC_DIR/aitbc-coordinator-api.env"
cat > "$COORD_API_ENV" << EOFCOORD
# AITBC Coordinator API — service-specific secrets
# Migrated from $SECRETS_SOURCE on $(date -Iseconds)
# Permissions: root:root 600

API_KEY_HASH_SECRET=$(extract_value API_KEY_HASH_SECRET)
JWT_SECRET=$(extract_value JWT_SECRET)
SECRET_KEY=$(extract_value SECRET_KEY)
COORDINATOR_API_KEY=$(extract_value COORDINATOR_API_KEY)
EOFCOORD
chmod 600 "$COORD_API_ENV"
echo "Created: $COORD_API_ENV"

# --- Blockchain Node secrets ---
BC_NODE_ENV="$ETC_DIR/aitbc-blockchain-node.env"
cat > "$BC_NODE_ENV" << EOFBC
# AITBC Blockchain Node — service-specific secrets
# Migrated from $SECRETS_SOURCE on $(date -Iseconds)
# Permissions: root:root 600

KEYSTORE_PASSWORD=$(extract_value KEYSTORE_PASSWORD)
proposer_id=$(extract_value proposer_id)
MEMPOOL_DB_URL=$(extract_value MEMPOOL_DB_URL)
EOFBC
chmod 600 "$BC_NODE_ENV"
echo "Created: $BC_NODE_ENV"

# --- Create empty .env files for services that reference %N.env ---
for svc in exchange gpu blockchain-p2p miner edge governance; do
    envfile="$ETC_DIR/aitbc-${svc}.env"
    if [ ! -f "$envfile" ]; then
        cat > "$envfile" << EOFEMPTY
# AITBC ${svc} Service — service-specific secrets
# Created during v0.5.1 secret migration
# Add service-specific secrets here (e.g., DATABASE_URL, API_KEY, etc.)
EOFEMPTY
        chmod 600 "$envfile"
        echo "Created empty: $envfile"
    fi
done

# --- Verify service files use %N.env ---
echo
echo "=== Verifying service files ==="
for svc in coordinator-api blockchain-node; do
    svc_file="/opt/aitbc/apps/${svc}/aitbc-${svc}.service"
    if grep -q "EnvironmentFile=/run/aitbc/secrets/.env" "$svc_file"; then
        echo "WARNING: $svc_file still references /run/aitbc/secrets/.env"
    else
        echo "OK: $svc_file migrated"
    fi
done

echo
echo "=== Migration Complete ==="
echo "Remember to:"
echo "  1. systemctl daemon-reload"
echo "  2. systemctl restart aitbc-coordinator-api aitbc-blockchain-node"
echo "  3. Verify services start correctly"
