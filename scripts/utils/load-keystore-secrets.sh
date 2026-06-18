#!/bin/bash
# Load AITBC secrets from credentials directory
# This script is called by systemd services before main process starts
# Enhanced with encryption, versioning, and audit logging

set -e

CREDENTIALS_DIR="/etc/aitbc/credentials"
RUN_DIR="/run/aitbc/secrets"
AUDIT_LOG="/var/log/aitbc/secrets-audit.log"
ENCRYPTION_KEY_FILE="/etc/aitbc/credentials/encryption_key"

# Create runtime directory (tmpfs, cleared on reboot)
mkdir -p "$RUN_DIR"
chmod 700 "$RUN_DIR"

# Create audit log directory
mkdir -p "$(dirname "$AUDIT_LOG")"
touch "$AUDIT_LOG"
chmod 600 "$AUDIT_LOG"

# Audit logging function
log_audit() {
    local action="$1"
    local secret_name="$2"
    local timestamp=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
    echo "[$timestamp] $action: $secret_name" >> "$AUDIT_LOG"
}

# Check if encryption key exists, create if not
if [ ! -f "$ENCRYPTION_KEY_FILE" ]; then
    echo "Generating encryption key..."
    openssl rand -hex 32 > "$ENCRYPTION_KEY_FILE"
    chmod 600 "$ENCRYPTION_KEY_FILE"
    log_audit "CREATE" "encryption_key"
fi

# Load encryption key
ENCRYPTION_KEY=$(cat "$ENCRYPTION_KEY_FILE")

# Decrypt function using AES-256-CBC
decrypt_secret() {
    local encrypted_file="$1"
    if [ -f "$encrypted_file" ]; then
        openssl enc -d -aes-256-cbc -pbkdf2 -in "$encrypted_file" -k "$ENCRYPTION_KEY" 2>/dev/null || cat "$encrypted_file"
    fi
}

# Create .env file from credentials
ENV_FILE="$RUN_DIR/.env"

# Clear existing file to avoid duplicate entries
> "$ENV_FILE"

# Function to load secret with versioning
load_secret() {
    local secret_name="$1"
    local env_var="$2"
    local secret_file="$CREDENTIALS_DIR/$secret_name"
    local version_file="$CREDENTIALS_DIR/${secret_name}.version"

    if [ -f "$secret_file" ]; then
        # Check if secret is encrypted
        if file "$secret_file" | grep -q "encrypted"; then
            secret_value=$(decrypt_secret "$secret_file")
        else
            secret_value=$(cat "$secret_file")
        fi

        # Get version if exists
        version="1"
        if [ -f "$version_file" ]; then
            version=$(cat "$version_file")
        fi

        echo "$env_var=$secret_value" >> "$ENV_FILE"
        log_audit "LOAD" "$secret_name (version $version)"
    fi
}

# Load secrets with versioning
load_secret "api_hash_secret" "API_KEY_HASH_SECRET"
load_secret "proposer_id" "proposer_id"
load_secret "keystore_password" "KEYSTORE_PASSWORD"
load_secret "coordinator_api_key" "COORDINATOR_API_KEY"
load_secret "jwt_secret" "JWT_SECRET"
load_secret "secret_key" "SECRET_KEY"

# Load PostgreSQL database passwords
for db_user in aitbc_user aitbc_marketplace aitbc_governance aitbc_trading aitbc_gpu aitbc_ai aitbc_mempool; do
    secret_file="$CREDENTIALS_DIR/postgres_${db_user}_password"
    if [ -f "$secret_file" ]; then
        if file "$secret_file" | grep -q "encrypted"; then
            db_password=$(decrypt_secret "$secret_file")
        else
            db_password=$(cat "$secret_file")
        fi
        echo "POSTGRES_${db_user^^}_PASSWORD=$db_password" >> "$ENV_FILE"
        log_audit "LOAD" "postgres_${db_user}_password"
    fi
done

# Add non-sensitive config from main blockchain.env
if [ -f "/etc/aitbc/blockchain.env" ]; then
    # Skip lines that are comments or contain migrated secrets
    grep -v '^#' /etc/aitbc/blockchain.env | grep -v 'API_KEY_HASH_SECRET' | grep -v 'proposer_id' >> "$ENV_FILE" || true
fi

chmod 600 "$ENV_FILE"

log_audit "COMPLETE" "secrets_loaded_to_$ENV_FILE"
