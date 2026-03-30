#!/bin/bash
# Follower Node Setup Script for AITBC Node (aitbc)
# This script configures aitbc as a follower node

set -e  # Exit on any error

echo "=== AITBC Follower Node Setup (aitbc) ==="

# Pull latest code
echo "1. Pulling latest code..."
cd /opt/aitbc
git pull origin main

# Install/update dependencies
echo "2. Installing/updating dependencies..."
/opt/aitbc/venv/bin/pip install -r requirements.txt

# Check and create required directories if they don't exist
echo "3. Creating required directories..."
mkdir -p /var/lib/aitbc/data /var/lib/aitbc/keystore /etc/aitbc /var/log/aitbc

# Verify directories exist
ls -la /var/lib/aitbc/ || echo "Creating /var/lib/aitbc/ structure..."

# Copy and adapt central .env for aitbc (follower node)
cp /etc/aitbc/.env /etc/aitbc/.env.aitbc.backup 2>/dev/null || true

# Update .env for aitbc follower node configuration
echo "4. Updating environment configuration..."
sed -i 's|proposer_id=.*|proposer_id=follower-node-aitbc|g' /etc/aitbc/.env
sed -i 's|keystore_path=/opt/aitbc/apps/blockchain-node/keystore|keystore_path=/var/lib/aitbc/keystore|g' /etc/aitbc/.env
sed -i 's|keystore_password_file=/opt/aitbc/apps/blockchain-node/keystore/.password|keystore_password_file=/var/lib/aitbc/keystore/.password|g' /etc/aitbc/.env
sed -i 's|db_path=./data/ait-mainnet/chain.db|db_path=/var/lib/aitbc/data/ait-mainnet/chain.db|g' /etc/aitbc/.env
sed -i 's|enable_block_production=true|enable_block_production=false|g' /etc/aitbc/.env
sed -i 's|gossip_broadcast_url=redis://127.0.0.1:6379|gossip_broadcast_url=redis://10.1.223.40:6379|g' /etc/aitbc/.env
sed -i 's|p2p_bind_port=8005|p2p_bind_port=7070|g' /etc/aitbc/.env
sed -i 's|trusted_proposers=.*|trusted_proposers=ait1apmaugx6csz50q07m99z8k44llry0zpl0yurl23hygarcey8z85qy4zr96|g' /etc/aitbc/.env

# Note: aitbc should sync genesis from aitbc1, not copy it
# The follower node will receive the genesis block via blockchain sync
# ⚠️  DO NOT: scp aitbc1:/var/lib/aitbc/data/ait-mainnet/genesis.json /var/lib/aitbc/data/ait-mainnet/
# ✅ INSTEAD: Wait for automatic sync via blockchain protocol

# Stop any existing services and clear old data
echo "5. Stopping existing services and clearing old data..."
systemctl stop aitbc-blockchain-* 2>/dev/null || true
rm -f /var/lib/aitbc/data/ait-mainnet/chain.db*

# Start follower services
echo "6. Starting follower services..."
systemctl daemon-reload
systemctl enable aitbc-blockchain-node aitbc-blockchain-rpc
systemctl start aitbc-blockchain-node aitbc-blockchain-rpc

echo "✅ Follower node setup completed successfully!"
echo "aitbc is now configured as a follower node."
echo "Waiting for blockchain sync from aitbc1..."
