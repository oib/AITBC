#!/bin/bash
# Load AITBC secrets from credentials directory
# This script is called by systemd services before main process starts

set -e

CREDENTIALS_DIR="/etc/aitbc/credentials"
RUN_DIR="/run/aitbc/secrets"

# Create runtime directory (tmpfs, cleared on reboot)
mkdir -p "$RUN_DIR"
chmod 700 "$RUN_DIR"

# Create .env file from credentials
ENV_FILE="$RUN_DIR/.env"

if [ -f "$CREDENTIALS_DIR/api_hash_secret" ]; then
    echo "API_KEY_HASH_SECRET=$(cat $CREDENTIALS_DIR/api_hash_secret)" >> "$ENV_FILE"
fi

if [ -f "$CREDENTIALS_DIR/proposer_id" ]; then
    echo "proposer_id=$(cat $CREDENTIALS_DIR/proposer_id)" >> "$ENV_FILE"
fi

if [ -f "$CREDENTIALS_DIR/keystore_password" ]; then
    echo "KEYSTORE_PASSWORD=$(cat $CREDENTIALS_DIR/keystore_password)" >> "$ENV_FILE"
fi

# Add non-sensitive config from main .env
if [ -f "/etc/aitbc/.env" ]; then
    # Skip lines that are comments or contain migrated secrets
    grep -v '^#' /etc/aitbc/.env | grep -v 'API_KEY_HASH_SECRET' | grep -v 'proposer_id' >> "$ENV_FILE" || true
fi

chmod 600 "$ENV_FILE"

echo "Secrets loaded to $ENV_FILE"
