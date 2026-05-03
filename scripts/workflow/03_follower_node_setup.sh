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
/opt/aitbc/venv/bin/pip install -r requirements.txt psycopg

# Setup PostgreSQL databases
echo "2.5. Setting up PostgreSQL databases..."
/opt/aitbc/infra/scripts/setup_postgresql_databases.sh

# Check and create required directories if they don't exist
echo "3. Creating required directories..."
mkdir -p /var/lib/aitbc/data /var/lib/aitbc/keystore /etc/aitbc /var/log/aitbc

# Verify directories exist
ls -la /var/lib/aitbc/ || echo "Creating /var/lib/aitbc/ structure..."

# Copy and adapt central .env for aitbc (follower node)
cp /etc/aitbc/.env /etc/aitbc/.env.aitbc.backup 2>/dev/null || true

# Update .env for aitbc follower node configuration
echo "4. Updating environment configuration..."
# Note: Don't overwrite auto-generated proposer_id or p2p_node_id - they must remain unique for P2P networking
set_env() {
    local key="$1"
    local value="$2"

    if grep -q "^${key}=" /etc/aitbc/.env; then
        sed -i "s|^${key}=.*|${key}=${value}|g" /etc/aitbc/.env
    else
        echo "${key}=${value}" >> /etc/aitbc/.env
    fi
}

set_env keystore_path /var/lib/aitbc/keystore
set_env keystore_password_file /var/lib/aitbc/keystore/.password
set_env db_path /var/lib/aitbc/data/ait-mainnet/chain.db
set_env enable_block_production false
set_env gossip_backend broadcast
set_env gossip_broadcast_url redis://10.1.223.40:6379
set_env default_peer_rpc_url http://aitbc1:8006
set_env p2p_bind_port 7070
set_env trusted_proposers ait1apmaugx6csz50q07m99z8k44llry0zpl0yurl23hygarcey8z85qy4zr96

# Ensure p2p_node_id exists in node.env (preserve if already set)
if ! grep -q "^p2p_node_id=" /etc/aitbc/node.env; then
    echo "p2p_node_id=node-$(cat /proc/sys/kernel/random/uuid | tr -d '-')" >> /etc/aitbc/node.env
fi

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
