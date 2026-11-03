#!/bin/bash
# Create unified aitbc user for all AITBC services
# This script should be run during deployment as part of the setup process

set -euo pipefail

# Paths are env-overridable so non-standard layouts — and tests — never
# touch the real /var, /etc or /run (#882).
LIB_DIR="${AITBC_LIB_DIR:-/var/lib/aitbc}"
LOG_DIR="${AITBC_LOG_DIR:-/var/log/aitbc}"
RUN_DIR="${AITBC_RUN_DIR:-/run/aitbc}"
ETC_DIR="${AITBC_ETC_DIR:-/etc/aitbc}"

echo "Creating unified aitbc user for AITBC services..."

# Check if running as root
if [ "$EUID" -ne 0 ]; then
    echo "This script must be run as root"
    exit 1
fi

# Create aitbc group if it doesn't exist
if ! getent group aitbc > /dev/null 2>&1; then
    echo "Creating aitbc group..."
    groupadd --system aitbc
else
    echo "aitbc group already exists"
fi

# Create aitbc user if it doesn't exist
if ! id aitbc > /dev/null 2>&1; then
    echo "Creating aitbc user..."
    useradd --system \
        --home-dir "$LIB_DIR" \
        --create-home \
        --shell /usr/sbin/nologin \
        --gid aitbc \
        aitbc
else
    echo "aitbc user already exists"
fi

# Add aitbc user to relevant supplementary groups
echo "Adding aitbc user to supplementary groups..."
usermod -aG aitbc-services aitbc 2>/dev/null || true
usermod -aG video aitbc 2>/dev/null || true  # For GPU access
usermod -aG render aitbc 2>/dev/null || true  # For GPU access

# Set up proper permissions.
#
# Non-recursive everywhere (#882): on an installed node /var/lib/aitbc
# already holds chain databases and the keystore — chowning the directory
# itself fixes service access without rewriting the owner of every byte of
# existing data. The keystore stays root-owned.
echo "Setting up directory permissions..."
mkdir -p "$LIB_DIR" "$LOG_DIR" "$RUN_DIR"
chown aitbc:aitbc "$LIB_DIR" "$LOG_DIR" "$RUN_DIR"
chmod 755 "$LIB_DIR" "$LOG_DIR" "$RUN_DIR"

# Keystore exists (or is created) root-owned; aitbc services read it through
# load-keystore-secrets, they do not own it.
mkdir -p "$LIB_DIR/keystore"
chown root:root "$LIB_DIR/keystore"
chmod 700 "$LIB_DIR/keystore"

# /etc/aitbc: restrict only when this script creates it. On an installed
# node the directory — and its deliberately chosen mode/owner — predates
# us; leave both alone.
if [ ! -d "$ETC_DIR" ]; then
    mkdir -p "$ETC_DIR"
    chmod 750 "$ETC_DIR"
    chown root:aitbc "$ETC_DIR"
else
    echo "$ETC_DIR already exists — leaving mode and ownership untouched"
fi

echo "aitbc user and group setup complete"
echo "User: aitbc (UID: $(id -u aitbc))"
echo "Group: aitbc (GID: $(getent group aitbc | cut -d: -f3))"
echo ""
echo "Next steps:"
echo "1. Update systemd service files to use User=aitbc"
echo "2. Restart services to apply changes"
