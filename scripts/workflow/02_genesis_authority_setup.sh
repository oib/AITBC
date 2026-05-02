#!/bin/bash
# Genesis Authority Setup Script for AITBC Node (aitbc1)
# This script configures aitbc1 as the genesis authority node

set -e  # Exit on any error

echo "=== AITBC Genesis Authority Setup (aitbc1) ==="

# We are already on aitbc1 node (localhost)
# No SSH needed - running locally

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

# Copy and adapt central .env for aitbc1 (genesis authority)
cp /etc/aitbc/blockchain.env /etc/aitbc/blockchain.env.aitbc1.backup 2>/dev/null || true

# Update .env for aitbc1 genesis authority configuration
echo "4. Updating environment configuration..."
# Note: Don't overwrite auto-generated proposer_id - it will be updated with actual genesis address after wallet generation
# Note: Don't overwrite auto-generated p2p_node_id - it must remain unique for P2P networking
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
set_env enable_block_production true
set_env gossip_backend broadcast
set_env gossip_broadcast_url redis://localhost:6379
set_env default_peer_rpc_url http://aitbc:8006
set_env p2p_bind_port 7070

# Ensure p2p_node_id exists in node.env (preserve if already set)
if ! grep -q "^p2p_node_id=" /etc/aitbc/node.env; then
    echo "p2p_node_id=node-$(cat /proc/sys/kernel/random/uuid | tr -d '-')" >> /etc/aitbc/node.env
fi

# Create genesis block with wallets (using Python script until CLI is fully implemented)
echo "5. Creating genesis block with wallets..."
cd /opt/aitbc/apps/blockchain-node
/opt/aitbc/venv/bin/python scripts/setup_production.py \
  --base-dir /opt/aitbc/apps/blockchain-node \
  --chain-id ait-mainnet \
  --total-supply 1000000000

# Get actual genesis wallet address and update config
echo "6. Updating genesis address configuration..."
GENESIS_ADDR=$(cat /var/lib/aitbc/keystore/aitbc1genesis.json | jq -r '.address')
echo "Genesis address: $GENESIS_ADDR"
# Update proposer_id with actual genesis address (this is the correct proposer_id for genesis authority)
sed -i "s|proposer_id=.*|proposer_id=$GENESIS_ADDR|g" /etc/aitbc/.env
# Update trusted_proposers with actual genesis address
sed -i "s|trusted_proposers=.*|trusted_proposers=$GENESIS_ADDR|g" /etc/aitbc/.env

# Copy genesis and allocations to standard location
echo "7. Copying genesis and allocations to standard location..."
mkdir -p /var/lib/aitbc/data/ait-mainnet
cp /opt/aitbc/apps/blockchain-node/data/ait-mainnet/genesis.json /var/lib/aitbc/data/ait-mainnet/
cp /opt/aitbc/apps/blockchain-node/data/ait-mainnet/allocations.json /var/lib/aitbc/data/ait-mainnet/
cp /opt/aitbc/apps/blockchain-node/keystore/* /var/lib/aitbc/keystore/

# Note: systemd services should already use /etc/aitbc/.env
# No need to update systemd if they are properly configured

# Enable and start blockchain services
echo "8. Starting blockchain services..."
systemctl daemon-reload
systemctl enable aitbc-blockchain-node aitbc-blockchain-rpc
systemctl start aitbc-blockchain-node aitbc-blockchain-rpc

echo "✅ Genesis authority setup completed successfully!"
echo "aitbc1 is now configured as the genesis authority node."
echo "Genesis address: $GENESIS_ADDR"
