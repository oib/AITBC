#!/bin/bash
# Create unified aitbc user for all AITBC services
# This script should be run during deployment as part of the setup process

set -e

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
        --home-dir /var/lib/aitbc \
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

# Set up proper permissions
echo "Setting up directory permissions..."
mkdir -p /var/lib/aitbc /var/log/aitbc /run/aitbc /etc/aitbc
chown -R aitbc:aitbc /var/lib/aitbc
chown -R aitbc:aitbc /var/log/aitbc
chown -R aitbc:aitbc /run/aitbc
chmod 755 /var/lib/aitbc /var/log/aitbc /run/aitbc

# Ensure secrets directory has restricted permissions
mkdir -p /etc/aitbc
chmod 750 /etc/aitbc
chown root:aitbc /etc/aitbc

echo "aitbc user and group setup complete"
echo "User: aitbc (UID: $(id -u aitbc))"
echo "Group: aitbc (GID: $(getent group aitbc | cut -d: -f3))"
echo ""
echo "Next steps:"
echo "1. Update systemd service files to use User=aitbc"
echo "2. Restart services to apply changes"
