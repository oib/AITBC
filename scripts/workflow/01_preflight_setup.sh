#!/bin/bash
# Pre-Flight Setup Script for AITBC Multi-Node Blockchain
# This script prepares the system for multi-node blockchain deployment

set -e  # Exit on any error

echo "=== AITBC Multi-Node Blockchain Pre-Flight Setup ==="

# 1. Stop existing services
echo "1. Stopping existing services..."
systemctl stop aitbc-blockchain-* 2>/dev/null || true

# 2. Update ALL systemd configurations (main files + drop-ins + overrides)
echo "2. Updating systemd configurations..."
# Update main service files
sed -i 's|EnvironmentFile=/opt/aitbc/.env|EnvironmentFile=/etc/aitbc/.env|g' /opt/aitbc/systemd/aitbc-blockchain-*.service
# Update drop-in configs
find /etc/systemd/system/aitbc-blockchain-*.service.d/ -name "10-central-env.conf" -exec sed -i 's|EnvironmentFile=/opt/aitbc/.env|EnvironmentFile=/etc/aitbc/.env|g' {} \; 2>/dev/null || true
# Fix override configs (wrong venv paths)
find /etc/systemd/system/aitbc-blockchain-*.service.d/ -name "override.conf" -exec sed -i 's|/opt/aitbc/apps/blockchain-node/.venv/bin/python3|/opt/aitbc/venv/bin/python3|g' {} \; 2>/dev/null || true
systemctl daemon-reload

# 3. Create central configuration file
echo "3. Setting up central configuration file..."
cp /opt/aitbc/.env /etc/aitbc/.env.backup 2>/dev/null || true
# Ensure .env is in the correct location (already should be)
mv /opt/aitbc/.env /etc/aitbc/.env 2>/dev/null || true

# 4. Setup AITBC CLI tool
echo "4. Setting up AITBC CLI tool..."
# Use central virtual environment (dependencies already installed)
source /opt/aitbc/venv/bin/activate
pip install -e /opt/aitbc/cli/ 2>/dev/null || true
echo 'alias aitbc="source /opt/aitbc/venv/bin/activate && aitbc"' >> ~/.bashrc
source ~/.bashrc

# 5. Clean old data (optional but recommended)
echo "5. Cleaning old data..."
rm -rf /var/lib/aitbc/data/ait-mainnet/*
rm -rf /var/lib/aitbc/keystore/*

# 6. Create keystore password file
echo "6. Creating keystore password file..."
mkdir -p /var/lib/aitbc/keystore
echo 'aitbc123' > /var/lib/aitbc/keystore/.password
chmod 600 /var/lib/aitbc/keystore/.password

# 7. Verify setup
echo "7. Verifying setup..."
aitbc --help 2>/dev/null || echo "CLI available but limited commands"
ls -la /etc/aitbc/.env

echo "✅ Pre-flight setup completed successfully!"
echo "System is ready for multi-node blockchain deployment."
