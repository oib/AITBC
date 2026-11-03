#!/bin/bash
set -euo pipefail
# Load AITBC secrets from credentials directory
# This script is called by systemd services before main process starts
# Enhanced with encryption, versioning, and audit logging

CREDENTIALS_DIR="${AITBC_CREDENTIALS_DIR:-/etc/aitbc/credentials}"
RUN_DIR="${AITBC_SECRETS_RUN_DIR:-/run/aitbc/secrets}"
AUDIT_LOG="${AITBC_SECRETS_AUDIT_LOG:-/var/log/aitbc/secrets-audit.log}"
ENCRYPTION_KEY_FILE="$CREDENTIALS_DIR/encryption_key"
BLOCKCHAIN_ENV="${AITBC_BLOCKCHAIN_ENV:-/etc/aitbc/blockchain.env}"

# Create runtime directory (tmpfs, cleared on reboot)
# Note: May fail on read-only filesystems, continue if directory exists
mkdir -p "$RUN_DIR" || {
    if [ ! -d "$RUN_DIR" ]; then
        echo "Error: Cannot create secrets directory $RUN_DIR"
        exit 1
    fi
}
# Skip chmod on read-only filesystems (common in containers)
chmod 700 "$RUN_DIR" 2>/dev/null || true

# Create audit log directory
mkdir -p "$(dirname "$AUDIT_LOG")" 2>/dev/null || true
touch "$AUDIT_LOG" 2>/dev/null || {
    echo "Warning: Cannot create audit log at $AUDIT_LOG (read-only filesystem)"
    AUDIT_LOG="/dev/null"
}
chmod 600 "$AUDIT_LOG" 2>/dev/null || true

# Audit logging function
log_audit() {
    local action="$1"
    local secret_name="$2"
    local timestamp
    timestamp=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
    echo "[$timestamp] $action: $secret_name" >> "$AUDIT_LOG"
}

# A credential is encrypted when its NAME says so (<name>.enc) or its body
# carries the openssl 'Salted__' magic. file(1) never says "encrypted" for
# openssl enc output, so the old `file | grep -q encrypted` check never
# matched and ciphertext was written into the env file.
is_encrypted_file() {
    local f="$1"
    [[ "$f" == *.enc ]] && return 0
    [[ -f "$f" && "$(head -c 8 "$f" 2>/dev/null)" == "Salted__" ]] && return 0
    return 1
}

# Check if encryption key exists, create if not
if [ ! -f "$ENCRYPTION_KEY_FILE" ]; then
    echo "Generating encryption key..."
    mkdir -p "$CREDENTIALS_DIR" 2>/dev/null || true
    openssl rand -hex 32 > "$ENCRYPTION_KEY_FILE"
    chmod 600 "$ENCRYPTION_KEY_FILE"
    log_audit "CREATE" "encryption_key"
fi

# Load encryption key
ENCRYPTION_KEY=$(cat "$ENCRYPTION_KEY_FILE")

# Print the plaintext of credential file $1. A decrypt failure is fatal —
# falling back to `cat` would write ciphertext into the env file (or hide a
# wrong key), so there is no silent fallback.
read_secret() {
    local secret_file="$1"
    if is_encrypted_file "$secret_file"; then
        openssl enc -d -aes-256-cbc -pbkdf2 -in "$secret_file" -k "$ENCRYPTION_KEY" || {
            echo "ERROR: cannot decrypt credential $secret_file" >&2
            log_audit "DECRYPT_FAIL" "$secret_file"
            return 1
        }
    else
        cat "$secret_file"
    fi
}

# Resolve the on-disk name of a credential: <name>.enc wins, then <name>.
credential_file() {
    local base="$CREDENTIALS_DIR/$1"
    if [ -f "$base.enc" ]; then
        printf '%s\n' "$base.enc"
    elif [ -f "$base" ]; then
        printf '%s\n' "$base"
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
    local version_file="$CREDENTIALS_DIR/${secret_name}.version"
    local secret_file secret_value version

    secret_file=$(credential_file "$secret_name" || true)
    if [ -n "$secret_file" ]; then
        secret_value=$(read_secret "$secret_file")

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
    secret_file=$(credential_file "postgres_${db_user}_password" || true)
    if [ -n "$secret_file" ]; then
        db_password=$(read_secret "$secret_file")
        echo "POSTGRES_${db_user^^}_PASSWORD=$db_password" >> "$ENV_FILE"
        log_audit "LOAD" "postgres_${db_user}_password"
    fi
done

# Add non-sensitive config from main blockchain.env
if [ -f "$BLOCKCHAIN_ENV" ]; then
    # Skip lines that are comments or contain migrated secrets
    grep -v '^#' "$BLOCKCHAIN_ENV" | grep -v 'API_KEY_HASH_SECRET' | grep -v 'proposer_id' >> "$ENV_FILE" || true
fi

chmod 600 "$ENV_FILE" 2>/dev/null || true

log_audit "COMPLETE" "secrets_loaded_to_$ENV_FILE"
