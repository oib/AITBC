---
description: Multi-node blockchain deployment and setup workflow
---

# Multi-Node Blockchain Deployment Workflow

This workflow sets up a two-node AITBC blockchain network (aitbc1 as genesis authority, aitbc as follower node), creates wallets, and demonstrates cross-node transactions.

## Prerequisites

- SSH access to both nodes (aitbc1 and aitbc)
- Both nodes have the AITBC repository cloned
- Redis available for cross-node gossip
- Python venv at `/opt/aitbc/venv`
- AITBC CLI tool available (aliased as `aitbc`)
- CLI tool configured to use `/etc/aitbc/blockchain.env` by default

## Pre-Flight Setup

Before running the workflow, ensure the following setup is complete:

```bash
# 1. Stop existing services
systemctl stop aitbc-blockchain-* 2>/dev/null || true

# 2. Update systemd services to use standard config location
sed -i 's|EnvironmentFile=/opt/aitbc/.env|EnvironmentFile=/etc/aitbc/blockchain.env|g' /opt/aitbc/systemd/aitbc-blockchain-*.service
systemctl daemon-reload

# 3. Move central config to standard location
cp /opt/aitbc/.env /etc/aitbc/blockchain.env.backup
mv /opt/aitbc/.env /etc/aitbc/blockchain.env

# 4. Setup AITBC CLI tool
python3 -m venv /opt/aitbc/cli/venv
source /opt/aitbc/cli/venv/bin/activate
pip install -e /opt/aitbc/cli/
echo 'alias aitbc="source /opt/aitbc/cli/venv/bin/activate && aitbc"' >> ~/.bashrc
source ~/.bashrc

# 5. Clean old data (optional but recommended)
rm -rf /var/lib/aitbc/data/ait-mainnet/*
rm -rf /var/lib/aitbc/keystore/*

# 6. Verify setup
aitbc --help
ls -la /etc/aitbc/blockchain.env
```

## Directory Structure

- `/opt/aitbc/venv` - Central Python virtual environment
- `/opt/aitbc/requirements.txt` - Python dependencies
- `/etc/aitbc/blockchain.env` - Central environment configuration
- `/var/lib/aitbc/data` - Blockchain database files
- `/var/lib/aitbc/keystore` - Wallet credentials
- `/var/log/aitbc/` - Service logs

## Steps

### Environment Configuration

The workflow uses the central `/etc/aitbc/blockchain.env` file as the configuration for both nodes:

- **Base Configuration**: The central config contains all default settings
- **Node-Specific Adaptation**: Each node adapts the config for its role (genesis vs follower)
- **Path Updates**: Paths are updated to use the standardized directory structure
- **Backup Strategy**: Original config is backed up before modifications
- **Standard Location**: Config moved to `/etc/aitbc/` following system standards
- **CLI Integration**: AITBC CLI tool uses this config file by default

### 1. Prepare aitbc1 (Genesis Authority Node)

```bash
# We are already on aitbc1 node (localhost)
# No SSH needed - running locally

# Pull latest code
cd /opt/aitbc
git pull origin main

# Install/update dependencies
/opt/aitbc/venv/bin/pip install -r requirements.txt

# Check and create required directories if they don't exist
mkdir -p /var/lib/aitbc/data /var/lib/aitbc/keystore /etc/aitbc /var/log/aitbc

# Verify directories exist
ls -la /var/lib/aitbc/ || echo "Creating /var/lib/aitbc/ structure..."

# Copy and adapt central .env for aitbc1 (genesis authority)
cp /etc/aitbc/blockchain.env /etc/aitbc/blockchain.env.aitbc1.backup

# Update .env for aitbc1 genesis authority configuration
sed -i 's|proposer_id=.*|proposer_id=aitbc1genesis|g' /etc/aitbc/blockchain.env
sed -i 's|keystore_path=/opt/aitbc/apps/blockchain-node/keystore|keystore_path=/var/lib/aitbc/keystore|g' /etc/aitbc/blockchain.env
sed -i 's|keystore_password_file=/opt/aitbc/apps/blockchain-node/keystore/.password|keystore_password_file=/var/lib/aitbc/keystore/.password|g' /etc/aitbc/blockchain.env
sed -i 's|db_path=./data/ait-mainnet/chain.db|db_path=/var/lib/aitbc/data/ait-mainnet/chain.db|g' /etc/aitbc/blockchain.env
sed -i 's|enable_block_production=true|enable_block_production=true|g' /etc/aitbc/blockchain.env
sed -i 's|gossip_broadcast_url=redis://127.0.0.1:6379|gossip_broadcast_url=redis://localhost:6379|g' /etc/aitbc/blockchain.env
sed -i 's|p2p_bind_port=8005|p2p_bind_port=7070|g' /etc/aitbc/blockchain.env

# Add trusted proposers for follower nodes
echo "trusted_proposers=aitbc1genesis" >> /etc/aitbc/blockchain.env

# Create genesis block with wallets using AITBC CLI
aitbc blockchain setup --chain-id ait-mainnet --total-supply 1000000000

# Copy genesis and allocations to standard location
mkdir -p /var/lib/aitbc/data/ait-mainnet
cp /opt/aitbc/apps/blockchain-node/data/ait-mainnet/genesis.json /var/lib/aitbc/data/ait-mainnet/
cp /opt/aitbc/apps/blockchain-node/data/ait-mainnet/allocations.json /var/lib/aitbc/data/ait-mainnet/
cp /opt/aitbc/apps/blockchain-node/keystore/* /var/lib/aitbc/keystore/

# Note: systemd services should already use /etc/aitbc/blockchain.env
# No need to update systemd if they are properly configured

# Enable and start blockchain services
systemctl daemon-reload
systemctl enable aitbc-blockchain-node aitbc-blockchain-rpc
systemctl start aitbc-blockchain-node aitbc-blockchain-rpc

# Monitor startup
journalctl -f -u aitbc-blockchain-node -u aitbc-blockchain-rpc
```

### 2. Verify aitbc1 Genesis State

```bash
# Check blockchain state
curl -s http://localhost:8006/rpc/head | jq .
curl -s http://localhost:8006/rpc/info | jq .
curl -s http://localhost:8006/rpc/supply | jq .

# Check genesis wallet balance
GENESIS_ADDR=$(cat /var/lib/aitbc/keystore/aitbc1genesis.json | jq -r '.address')
curl -s "http://localhost:8006/rpc/getBalance/$GENESIS_ADDR" | jq .
```

### 3. Prepare aitbc (Follower Node)

```bash
# SSH to aitbc
ssh aitbc

# Pull latest code
cd /opt/aitbc
git pull origin main

# Install/update dependencies
/opt/aitbc/venv/bin/pip install -r requirements.txt

# Check and create required directories if they don't exist
mkdir -p /var/lib/aitbc/data /var/lib/aitbc/keystore /etc/aitbc /var/log/aitbc

# Verify directories exist
ls -la /var/lib/aitbc/ || echo "Creating /var/lib/aitbc/ structure..."

# Copy and adapt central .env for aitbc (follower node)
cp /etc/aitbc/blockchain.env /etc/aitbc/blockchain.env.aitbc.backup

# Update .env for aitbc follower node configuration
sed -i 's|proposer_id=.*|proposer_id=follower-node-aitbc|g' /etc/aitbc/blockchain.env
sed -i 's|keystore_path=/opt/aitbc/apps/blockchain-node/keystore|keystore_path=/var/lib/aitbc/keystore|g' /etc/aitbc/blockchain.env
sed -i 's|keystore_password_file=/opt/aitbc/apps/blockchain-node/keystore/.password|keystore_password_file=/var/lib/aitbc/keystore/.password|g' /etc/aitbc/blockchain.env
sed -i 's|db_path=./data/ait-mainnet/chain.db|db_path=/var/lib/aitbc/data/ait-mainnet/chain.db|g' /etc/aitbc/blockchain.env
sed -i 's|enable_block_production=true|enable_block_production=false|g' /etc/aitbc/blockchain.env
sed -i 's|gossip_broadcast_url=redis://127.0.0.1:6379|gossip_broadcast_url=redis://10.1.223.40:6379|g' /etc/aitbc/blockchain.env
sed -i 's|p2p_bind_port=8005|p2p_bind_port=7070|g' /etc/aitbc/blockchain.env
sed -i 's|trusted_proposers=.*|trusted_proposers=ait1apmaugx6csz50q07m99z8k44llry0zpl0yurl23hygarcey8z85qy4zr96|g' /etc/aitbc/blockchain.env

# Note: aitbc should sync genesis from aitbc1, not copy it
# The follower node will receive the genesis block via blockchain sync

# Note: systemd services should already use /etc/aitbc/blockchain.env
# No need to update systemd if they are properly configured

# Stop any existing services and clear old data
systemctl stop aitbc-blockchain-* 2>/dev/null || true
rm -f /var/lib/aitbc/data/ait-mainnet/chain.db*

# Start follower services
systemctl daemon-reload
systemctl enable aitbc-blockchain-node aitbc-blockchain-rpc
systemctl start aitbc-blockchain-node aitbc-blockchain-rpc

# Monitor sync
journalctl -f -u aitbc-blockchain-node -u aitbc-blockchain-rpc
```

### 4. Watch Blockchain Sync

```bash
# On aitbc, monitor sync progress
watch -n 2 'curl -s http://localhost:8006/rpc/head | jq .height'

# Compare with aitbc1
ssh aitbc1 'curl -s http://localhost:8006/rpc/head | jq .height'
```

### 5. Create Wallet on aitbc

```bash
# On aitbc, create a new wallet using AITBC CLI
aitbc wallet create --name aitbc-user --password $(cat /var/lib/aitbc/keystore/.password)

# Note the new wallet address
WALLET_ADDR=$(cat /var/lib/aitbc/keystore/aitbc-user.json | jq -r '.address')
echo "New wallet: $WALLET_ADDR"
```

### 6. Send 1000 AIT from Genesis to aitbc Wallet

```bash
# On aitbc1, send 1000 AIT using AITBC CLI
aitbc transaction send \
  --from aitbc1genesis \
  --to $WALLET_ADDR \
  --amount 1000 \
  --fee 10

# Wait for transaction to be mined
sleep 15

# Verify balance on aitbc
curl -s "http://localhost:8006/rpc/getBalance/$WALLET_ADDR" | jq .
```

### 7. Final Verification

```bash
# Check both nodes are in sync
echo "=== aitbc1 height (localhost) ==="
curl -s http://localhost:8006/rpc/head | jq .height

echo "=== aitbc height (remote) ==="
ssh aitbc 'curl -s http://localhost:8006/rpc/head | jq .height'

echo "=== aitbc wallet balance (remote) ==="
ssh aitbc "curl -s \"http://localhost:8006/rpc/getBalance/$WALLET_ADDR\" | jq ."
```

## Environment Management

### Central .env Configuration

The workflow uses `/etc/aitbc/blockchain.env` as the central configuration file:

```bash
# View current configuration
cat /etc/aitbc/blockchain.env

# Restore from backup if needed
cp /etc/aitbc/blockchain.env.backup /etc/aitbc/blockchain.env  # aitbc1
cp /etc/aitbc/blockchain.env.backup /etc/aitbc/blockchain.env   # aitbc

# Key configuration differences:
# aitbc1: proposer_id=aitbc1genesis, enable_block_production=true
# aitbc: proposer_id=follower-node-aitbc, enable_block_production=false
```

### Service Configuration

- **Environment File**: All services use `/etc/aitbc/blockchain.env` (standard config location)
- **Virtual Environment**: Central venv at `/opt/aitbc/venv`
- **Database Files**: `/var/lib/aitbc/data`
- **Wallet Credentials**: `/var/lib/aitbc/keystore`
- **Service Logs**: `/var/log/aitbc/` via journald
- **Standardized Paths**: All paths use `/var/lib/aitbc/` structure
- **Config Location**: Central config moved to `/etc/aitbc/` following standards

## Troubleshooting

- **Services won't start**: Check `/var/log/aitbc/` for service logs
- **Sync issues**: Verify Redis connectivity between nodes
- **Transaction failures**: Check wallet nonce and balance
- **Permission errors**: Ensure `/var/lib/aitbc/` is owned by root with proper permissions
- **Configuration issues**: Verify `/etc/aitbc/blockchain.env` file contents and systemd service EnvironmentFile paths
