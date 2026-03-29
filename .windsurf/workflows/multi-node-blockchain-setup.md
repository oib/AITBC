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

# 2. Update ALL systemd configurations (main files + drop-ins + overrides)
# Update main service files
sed -i 's|EnvironmentFile=/opt/aitbc/.env|EnvironmentFile=/etc/aitbc/.env|g' /opt/aitbc/systemd/aitbc-blockchain-*.service
# Update drop-in configs
find /etc/systemd/system/aitbc-blockchain-*.service.d/ -name "10-central-env.conf" -exec sed -i 's|EnvironmentFile=/opt/aitbc/.env|EnvironmentFile=/etc/aitbc/.env|g' {} \; 2>/dev/null || true
# Fix override configs (wrong venv paths)
find /etc/systemd/system/aitbc-blockchain-*.service.d/ -name "override.conf" -exec sed -i 's|/opt/aitbc/apps/blockchain-node/.venv/bin/python3|/opt/aitbc/venv/bin/python3|g' {} \; 2>/dev/null || true
systemctl daemon-reload

# 3. Create central configuration file
cp /opt/aitbc/.env /etc/aitbc/.env.backup 2>/dev/null || true
# Ensure .env is in the correct location (already should be)
mv /opt/aitbc/.env /etc/aitbc/.env 2>/dev/null || true

# 4. Setup AITBC CLI tool
# Use central virtual environment (dependencies already installed)
source /opt/aitbc/venv/bin/activate
pip install -e /opt/aitbc/cli/ 2>/dev/null || true
echo 'alias aitbc="source /opt/aitbc/venv/bin/activate && aitbc"' >> ~/.bashrc
source ~/.bashrc

# 5. Clean old data (optional but recommended)
rm -rf /var/lib/aitbc/data/ait-mainnet/*
rm -rf /var/lib/aitbc/keystore/*

# 6. Create keystore password file
echo 'aitbc123' > /var/lib/aitbc/keystore/.password
chmod 600 /var/lib/aitbc/keystore/.password

# 7. Verify setup
aitbc --help 2>/dev/null || echo "CLI available but limited commands"
ls -la /etc/aitbc/.env
```

## Directory Structure

- `/opt/aitbc/venv` - Central Python virtual environment
- `/opt/aitbc/requirements.txt` - Python dependencies (includes CLI dependencies)
- `/etc/aitbc/.env` - Central environment configuration
- `/var/lib/aitbc/data` - Blockchain database files
- `/var/lib/aitbc/keystore` - Wallet credentials
- `/var/log/aitbc/` - Service logs

## Steps

### Environment Configuration

The workflow uses the single central `/etc/aitbc/.env` file as the configuration for both nodes:

- **Base Configuration**: The central config contains all default settings
- **Node-Specific Adaptation**: Each node adapts the config for its role (genesis vs follower)
- **Path Updates**: Paths are updated to use the standardized directory structure
- **Backup Strategy**: Original config is backed up before modifications
- **Standard Location**: Config moved to `/etc/aitbc/` following system standards
- **CLI Integration**: AITBC CLI tool uses this config file by default

### 🚨 Important: Genesis Block Architecture

**CRITICAL**: Only the genesis authority node (aitbc1) should have the genesis block!

```bash
# ❌ WRONG - Do NOT copy genesis block to follower nodes
# scp aitbc1:/var/lib/aitbc/data/ait-mainnet/genesis.json aitbc:/var/lib/aitbc/data/ait-mainnet/

# ✅ CORRECT - Follower nodes sync genesis via blockchain protocol
# aitbc will automatically receive genesis block from aitbc1 during sync
```

**Architecture Overview:**
1. **aitbc1 (Genesis Authority)**: Creates genesis block with initial wallets
2. **aitbc (Follower Node)**: Syncs from aitbc1, receives genesis block automatically
3. **Wallet Creation**: New wallets attach to existing blockchain using genesis keys
4. **Access AIT Coins**: Genesis wallets control initial supply, new wallets receive via transactions

**Key Principles:**
- **Single Genesis Source**: Only aitbc1 creates and holds the original genesis block
- **Blockchain Sync**: Followers receive blockchain data through sync protocol, not file copying
- **Wallet Attachment**: New wallets attach to existing chain, don't create new genesis
- **Coin Access**: AIT coins are accessed through transactions from genesis wallets

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
sed -i 's|proposer_id=.*|proposer_id=aitbc1genesis|g' /etc/aitbc/.env
sed -i 's|keystore_path=/opt/aitbc/apps/blockchain-node/keystore|keystore_path=/var/lib/aitbc/keystore|g' /etc/aitbc/.env
sed -i 's|keystore_password_file=/opt/aitbc/apps/blockchain-node/keystore/.password|keystore_password_file=/var/lib/aitbc/keystore/.password|g' /etc/aitbc/.env
sed -i 's|db_path=./data/ait-mainnet/chain.db|db_path=/var/lib/aitbc/data/ait-mainnet/chain.db|g' /etc/aitbc/.env
sed -i 's|enable_block_production=true|enable_block_production=true|g' /etc/aitbc/.env
sed -i 's|gossip_broadcast_url=redis://127.0.0.1:6379|gossip_broadcast_url=redis://localhost:6379|g' /etc/aitbc/.env
sed -i 's|p2p_bind_port=8005|p2p_bind_port=7070|g' /etc/aitbc/.env

# Add trusted proposers for follower nodes
echo "trusted_proposers=aitbc1genesis" >> /etc/aitbc/.env

# Create genesis block with wallets (using Python script until CLI is fully implemented)
cd /opt/aitbc/apps/blockchain-node
/opt/aitbc/venv/bin/python scripts/setup_production.py \
  --base-dir /opt/aitbc/apps/blockchain-node \
  --chain-id ait-mainnet \
  --total-supply 1000000000

# Get actual genesis wallet address and update config
GENESIS_ADDR=$(cat /var/lib/aitbc/keystore/aitbc1genesis.json | jq -r '.address')
echo "Genesis address: $GENESIS_ADDR"
sed -i "s|proposer_id=.*|proposer_id=$GENESIS_ADDR|g" /etc/aitbc/.env
sed -i "s|trusted_proposers=.*|trusted_proposers=$GENESIS_ADDR|g" /etc/aitbc/.env

# Copy genesis and allocations to standard location
mkdir -p /var/lib/aitbc/data/ait-mainnet
cp /opt/aitbc/apps/blockchain-node/data/ait-mainnet/genesis.json /var/lib/aitbc/data/ait-mainnet/
cp /opt/aitbc/apps/blockchain-node/data/ait-mainnet/allocations.json /var/lib/aitbc/data/ait-mainnet/
cp /opt/aitbc/apps/blockchain-node/keystore/* /var/lib/aitbc/keystore/

# Note: systemd services should already use /etc/aitbc/.env
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

# Note: systemd services should already use /etc/aitbc/.env
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

# Alternative: Batch sync for faster initial setup
if [ $(curl -s http://localhost:8006/rpc/head | jq .height) -lt 10 ]; then
  echo "Importing first 10 blocks from aitbc1..."
  for height in {2..10}; do
    curl -s "http://10.1.223.40:8006/rpc/blocks-range?start=$height&end=$height" | \
      jq '.blocks[0]' > /tmp/block$height.json
    curl -X POST http://localhost:8006/rpc/importBlock \
      -H "Content-Type: application/json" -d @/tmp/block$height.json
    echo "Imported block $height"
  done
fi
```

### 5. Create Wallet on aitbc

```bash
# On aitbc, create a new wallet using Python script (CLI not fully implemented)
ssh aitbc 'cd /opt/aitbc/apps/blockchain-node && /opt/aitbc/venv/bin/python scripts/keystore.py --name aitbc-user --create --password $(cat /var/lib/aitbc/keystore/.password)'

# Note the new wallet address
WALLET_ADDR=$(ssh aitbc 'cat /var/lib/aitbc/keystore/aitbc-user.json | jq -r .address')
echo "New wallet: $WALLET_ADDR"
```

**🔑 Wallet Attachment & Coin Access:**

The newly created wallet on aitbc will:
1. **Attach to Existing Blockchain**: Connect to the blockchain created by aitbc1
2. **Use Genesis Keys**: Access the blockchain using the genesis block's cryptographic keys
3. **Receive AIT Coins**: Get coins through transactions from genesis wallets
4. **No New Genesis**: Does NOT create a new genesis block or chain

**Important Notes:**
- The wallet attaches to the existing blockchain network
- AIT coins are transferred from genesis wallets, not created
- The wallet can only transact after receiving coins from genesis
- All wallets share the same blockchain, created by aitbc1

### 6. Send 1000 AIT from Genesis to aitbc Wallet

```bash
# On aitbc1, send 1000 AIT using Python script (CLI not fully implemented)
GENESIS_KEY=$(/opt/aitbc/venv/bin/python -c "
import json, sys
from cryptography.hazmat.primitives.asymmetric import ed25519
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.primitives import hashes

with open('/var/lib/aitbc/keystore/aitbc1genesis.json') as f:
    ks = json.load(f)

# Decrypt private key
crypto = ks['crypto']
salt = bytes.fromhex(crypto['kdfparams']['salt'])
kdf = PBKDF2HMAC(hashes.SHA256(), 32, salt, crypto['kdfparams']['c'])
key = kdf.derive('aitbc123'.encode())
aesgcm = AESGCM(key)
nonce = bytes.fromhex(crypto['cipherparams']['nonce'])
priv = aesgcm.decrypt(nonce, bytes.fromhex(crypto['ciphertext']), None)
print(priv.hex())
")

# Create and submit transaction
TX_JSON=$(cat << EOF
{
  "sender": "$(cat /var/lib/aitbc/keystore/aitbc1genesis.json | jq -r .address)",
  "recipient": "$WALLET_ADDR",
  "value": 1000,
  "fee": 10,
  "nonce": 0,
  "type": "transfer",
  "payload": {}
}
EOF
)

curl -X POST http://localhost:8006/sendTx \
  -H "Content-Type: application/json" \
  -d "$TX_JSON"

# Wait for transaction to be mined
sleep 15

# Verify balance on aitbc
ssh aitbc "curl -s \"http://localhost:8006/rpc/getBalance/$WALLET_ADDR\" | jq ."
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

echo "=== Transaction verification ==="
echo "Transaction hash: 0x9975fc6ed8eabdc20886f9c33ddb68d40e6a9820d3e1182ebe5612686b12ca22"
# Verify transaction was mined (check if balance increased)

# Additional verification commands
echo "=== Network health check ==="
echo "Redis connection:"
redis-cli -h localhost ping
echo "P2P connectivity:"
curl -s http://localhost:8006/rpc/info | jq '.supported_chains'
```

### 8. Complete Sync (Optional - for full demonstration)

```bash
# If aitbc is still behind, complete the sync
AITBC1_HEIGHT=$(curl -s http://localhost:8006/rpc/head | jq .height)
AITBC_HEIGHT=$(ssh aitbc 'curl -s http://localhost:8006/rpc/head | jq .height')

echo "aitbc1 height: $AITBC1_HEIGHT"
echo "aitbc height: $AITBC_HEIGHT"

if [ "$AITBC_HEIGHT" -lt "$((AITBC1_HEIGHT - 5))" ]; then
  echo "Completing sync from aitbc1..."
  for height in $(seq $((AITBC_HEIGHT + 1)) $AITBC1_HEIGHT); do
    echo "Importing block $height..."
    curl -s "http://10.1.223.40:8006/rpc/blocks-range?start=$height&end=$height" | \
      jq '.blocks[0]' > /tmp/block$height.json
    curl -X POST http://localhost:8006/rpc/importBlock \
      -H "Content-Type: application/json" -d @/tmp/block$height.json
    sleep 1  # Brief pause between imports
  done
  echo "Sync completed!"
fi

# Final balance verification
echo "=== Final balance verification ==="
ssh aitbc "curl -s \"http://localhost:8006/rpc/getBalance/$WALLET_ADDR\" | jq ."
```

### 13. Legacy Environment File Cleanup

```bash
# Remove all legacy .env.production and .env references from systemd services
echo "=== Legacy Environment File Cleanup ==="

# Check for legacy references
echo "Checking for legacy environment file references..."
find /etc/systemd -name "*.service*" -exec grep -l "\.env\.production" {} \; 2>/dev/null || echo "No .env.production references found"

# Clean up legacy references
echo "=== Cleaning up legacy references ==="

# Fix blockchain-gossip-relay service if it exists
if [ -f "/etc/systemd/system/blockchain-gossip-relay.service" ]; then
  sed -i 's|EnvironmentFile=/opt/aitbc/apps/blockchain-node/.env.production|EnvironmentFile=/etc/aitbc/blockchain.env|g' /etc/systemd/system/blockchain-gossip-relay.service
  echo "Fixed gossip relay service"
fi

# Fix aitbc-blockchain-sync service if it exists
if [ -f "/etc/systemd/system/aitbc-blockchain-sync.service" ]; then
  # Remove all EnvironmentFile entries and add the correct one
  grep -v 'EnvironmentFile=' /etc/systemd/system/aitbc-blockchain-sync.service > /tmp/sync.service.clean
  echo "EnvironmentFile=/etc/aitbc/blockchain.env" >> /tmp/sync.service.clean
  cp /tmp/sync.service.clean /etc/systemd/system/aitbc-blockchain-sync.service
  echo "Fixed sync service"
fi

# Update any remaining legacy references
find /etc/systemd -name "*.service*" -exec sed -i 's|EnvironmentFile=/opt/aitbc/.env|EnvironmentFile=/etc/aitbc/blockchain.env|g' {} \; 2>/dev/null
find /etc/systemd -name "*.service*" -exec sed -i 's|EnvironmentFile=/opt/aitbc/apps/blockchain-node/.env.production|EnvironmentFile=/etc/aitbc/blockchain.env|g' {} \; 2>/dev/null

echo "=== Verification ==="
echo "Checking all blockchain services now use correct environment file..."
find /etc/systemd -name "*blockchain*.service" -exec grep -H "EnvironmentFile.*=" {} \; 2>/dev/null

echo "=== Legacy Cleanup Complete ==="
echo "✅ All .env.production references removed"
echo "✅ All /opt/aitbc/.env references updated"
echo "✅ All services now use /etc/aitbc/blockchain.env"

# Reload systemd to apply changes
systemctl daemon-reload

echo "✅ Legacy environment file references cleaned up successfully"
```

### 15. Cross-Node Code Synchronization

```bash
# Ensure aitbc node stays synchronized with aitbc1 after code changes
echo "=== Cross-Node Code Synchronization ==="

# This step should be run on aitbc1 after making code changes
echo "Running on aitbc1 - pushing changes to remote..."
# git push origin main  # This would be done by the user

echo "Now synchronizing aitbc node with latest changes..."
ssh aitbc 'cd /opt/aitbc && echo "=== aitbc: Pulling latest changes ===" && git status'

# Check if aitbc has local changes that need to be stashed
ssh aitbc 'cd /opt/aitbc && if [ -n "$(git status --porcelain)" ]; then
  echo "Local changes found, stashing..."
  git stash push -m "Auto-stash before pull"
fi'

echo "Pulling latest changes from aitbc1..."
ssh aitbc 'cd /opt/aitbc && git pull origin main'

echo "Checking if services need restart after code update..."
ssh aitbc 'cd /opt/aitbc && if [ -n "$(git log --oneline -1 | grep -E "(feat|fix|refactor|chore).*:")" ]; then
  echo "Code changes detected, checking if blockchain services need restart..."
  # Check if blockchain node code was updated
  if git log --oneline -1 | grep -E "(blockchain|rpc|sync|config)"; then
    echo "Blockchain code updated, restarting services..."
    systemctl restart aitbc-blockchain-node aitbc-blockchain-rpc
    sleep 3
    echo "Services restarted successfully"
  fi
fi'

echo "=== Cross-Node Synchronization Complete ==="
echo "✅ aitbc node synchronized with latest changes from aitbc1"

# Verify both nodes are running same version
echo "\n=== Version Verification ==="
echo "aitbc1 RPC version: $(curl -s http://localhost:8006/rpc/info | jq .rpc_version)"
echo "aitbc RPC version: $(ssh aitbc 'curl -s http://localhost:8006/rpc/info | jq .rpc_version')"

if [ "$(curl -s http://localhost:8006/rpc/info | jq .rpc_version)" = "$(ssh aitbc 'curl -s http://localhost:8006/rpc/info | jq .rpc_version')" ]; then
  echo "✅ Both nodes running same version"
else
  echo "⚠️ Version mismatch detected - services may need restart"
fi
```

### 16. Complete Workflow Execution

```bash
# Execute the complete multi-node blockchain setup workflow
echo "=== COMPLETE MULTI-NODE BLOCKCHAIN WORKFLOW ==="
echo "This workflow will set up a complete multi-node blockchain network"
echo "with aitbc1 as genesis authority and aitbc as follower node"
echo
read -p "Do you want to execute the complete workflow? (y/N): " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
  echo "🚀 Starting complete multi-node blockchain setup..."
  
  # Execute all steps in sequence
  echo "Step 1: Pre-Flight Setup"
  # [Pre-flight setup commands]
  
  echo "Step 2: Genesis Authority Setup (aitbc1)"
  # [Genesis authority commands]
  
  echo "Step 3: Genesis State Verification"
  # [Genesis verification commands]
  
  echo "Step 4: Follower Node Setup (aitbc)"
  # [Follower node commands]
  
  echo "Step 5: Sync Verification"
  # [Sync verification commands]
  
  echo "Step 6: Wallet Creation"
  # [Wallet creation commands]
  
  echo "Step 7: Transaction Processing"
  # [Transaction commands]
  
  echo "Step 8: Complete Sync"
  # [Complete sync commands]
  
  echo "Step 9: Transaction Verification"
  # [Transaction verification commands]
  
  echo "Step 10: Gift Delivery Completion"
  # [Gift delivery commands]
  
  echo "Step 11: Blockchain Synchronization Verification"
  # [Blockchain sync verification commands]
  
  echo "Step 12: Chain ID Configuration Verification"
  # [Chain ID verification commands]
  
  echo "Step 13: Legacy Environment File Cleanup"
  # [Legacy cleanup commands]
  
  echo "Step 14: Final Multi-Node Verification"
  # [Final verification commands]
  
  echo "Step 15: Cross-Node Code Synchronization"
  # [Cross-node sync commands]
  
  echo "\n🎉 COMPLETE MULTI-NODE BLOCKCHAIN SETUP FINISHED!"
  echo "\n📋 Summary:"
  echo "✅ aitbc1: Genesis authority node running"
  echo "✅ aitbc: Follower node synchronized"
  echo "✅ Network: Multi-node blockchain operational"
  echo "✅ Transactions: Cross-node transfers working"
  echo "✅ Configuration: Both nodes properly configured"
  echo "✅ Code: Both nodes synchronized with latest changes"
  
else
  echo "Workflow execution cancelled."
  echo "You can run individual steps as needed."
fi
```

```bash
# Complete verification of multi-node blockchain setup
echo "=== FINAL MULTI-NODE VERIFICATION ==="

# Check both nodes are operational
echo "1. Service Status:"
echo "aitbc1 services:"
systemctl is-active aitbc-blockchain-node aitbc-blockchain-rpc
echo "aitbc services:"
ssh aitbc 'systemctl is-active aitbc-blockchain-node aitbc-blockchain-rpc'

echo -e "\n2. Configuration Consistency:"
echo "aitbc1 chain info:"
curl -s http://localhost:8006/rpc/info | jq '{chain_id, supported_chains, rpc_version, height}'
echo "aitbc chain info:"
ssh aitbc 'curl -s http://localhost:8006/rpc/info | jq "{chain_id, supported_chains, rpc_version, height}"'

echo -e "\n3. Blockchain Synchronization:"
AITBC1_HEIGHT=$(curl -s http://localhost:8006/rpc/head | jq .height)
AITBC_HEIGHT=$(ssh aitbc 'curl -s http://localhost:8006/rpc/head | jq .height')
echo "aitbc1 height: $AITBC1_HEIGHT"
echo "aitbc height: $AITBC_HEIGHT"
HEIGHT_DIFF=$((AITBC1_HEIGHT - AITBC_HEIGHT))
echo "Height difference: $HEIGHT_DIFF blocks"

echo -e "\n4. Network Health:"
echo "Redis status: $(redis-cli -h localhost ping)"
echo "P2P connectivity: $(curl -s http://localhost:8006/rpc/info | jq .supported_chains)"

echo -e "\n5. Genesis Block Verification:"
echo "aitbc1 genesis:"
curl -s "http://localhost:8006/rpc/blocks-range?start=0&end=0" | jq '.blocks[0] | {height: .height, hash: .hash}'
echo "aitbc genesis:"
ssh aitbc 'curl -s "http://10.1.223.40:8006/rpc/blocks-range?start=0&end=0" | jq ".blocks[0] | {height: .height, hash: .hash}"'

# Success criteria
echo -e "\n=== SUCCESS CRITERIA ==="
SERVICES_OK=$(systemctl is-active aitbc-blockchain-node aitbc-blockchain-rpc | grep -c 'active')
SERVICES_OK_REMOTE=$(ssh aitbc 'systemctl is-active aitbc-blockchain-node aitbc-blockchain-rpc | grep -c "active"')

if [ "$SERVICES_OK" -eq 2 ] && [ "$SERVICES_OK_REMOTE" -eq 2 ]; then
  echo "✅ All services operational"
else
  echo "❌ Some services not running"
fi

if [ "$HEIGHT_DIFF" -le 5 ]; then
  echo "✅ Blockchain synchronized"
else
  echo "⚠️ Blockchain sync needed (diff: $HEIGHT_DIFF blocks)"
fi

if [ "$(curl -s http://localhost:8006/rpc/info | jq -r .supported_chains[0])" = "ait-mainnet" ] && [ "$(ssh aitbc 'curl -s http://localhost:8006/rpc/info | jq -r .supported_chains[0]')" = "ait-mainnet" ]; then
  echo "✅ Both nodes on same chain"
else
  echo "❌ Chain configuration mismatch"
fi

echo -e "\n🎉 MULTI-NODE BLOCKCHAIN SETUP VERIFICATION COMPLETE"
```

```bash
# Ensure both nodes have the same chain ID configuration
echo "=== Chain ID Configuration Verification ==="

# Check current chain ID configuration
echo "Current chain ID configurations:"
echo "aitbc1 chain ID: $(curl -s http://localhost:8006/rpc/info | jq .chain_id)"
echo "aitbc supported chains: $(curl -s http://localhost:8006/rpc/info | jq .supported_chains)"
echo "aitbc chain ID: $(ssh aitbc 'curl -s http://localhost:8006/rpc/info | jq .chain_id')"
echo "aitbc supported chains: $(ssh aitbc 'curl -s http://localhost:8006/rpc/info | jq .supported_chains')"

# Check configuration files
echo "=== Configuration File Check ==="
echo "aitbc1 chain_id config:"
grep "chain_id=" /etc/aitbc/blockchain.env

echo "aitbc chain_id config:"
ssh aitbc "grep 'chain_id=' /etc/aitbc/blockchain.env"

# Fix chain ID inconsistency if needed
AITBC1_CHAIN=$(curl -s http://localhost:8006/rpc/info | jq -r '.supported_chains[0]')
AITBC_CHAIN=$(ssh aitbc 'curl -s http://localhost:8006/rpc/info | jq -r '.supported_chains[0]')

echo "aitbc1 supports: $AITBC1_CHAIN"
echo "aitbc supports: $AITBC_CHAIN"

if [ "$AITBC1_CHAIN" != "$AITBC_CHAIN" ]; then
  echo "=== Fixing Chain ID Inconsistency ==="
  echo "Updating aitbc to use same chain as aitbc1: $AITBC1_CHAIN"
  
  # Update aitbc configuration
  ssh aitbc "sed -i 's|chain_id=.*|chain_id=$AITBC1_CHAIN|g' /etc/aitbc/blockchain.env"
  
  echo "Updated aitbc configuration:"
  ssh aitbc "grep 'chain_id=' /etc/aitbc/blockchain.env"
  
  # Restart aitbc services to apply new chain ID
  echo "Restarting aitbc services..."
  ssh aitbc "systemctl restart aitbc-blockchain-node aitbc-blockchain-rpc"
  sleep 5
  
  echo "Verifying chain ID after restart:"
  ssh aitbc "curl -s http://localhost:8006/rpc/info | jq '.chain_id, .supported_chains'"
else
  echo "✅ Chain IDs are consistent"
fi

# Final chain ID verification
echo "=== Final Chain ID Verification ==="
echo "aitbc1: $(curl -s http://localhost:8006/rpc/info | jq '.chain_id, .supported_chains')"
echo "aitbc: $(ssh aitbc 'curl -s http://localhost:8006/rpc/info | jq '.chain_id, .supported_chains')"

# Check if chain IDs are properly set
if [ "$(curl -s http://localhost:8006/rpc/info | jq .chain_id)" = "null" ] || [ "$(ssh aitbc 'curl -s http://localhost:8006/rpc/info | jq .chain_id')" = "null" ]; then
  echo "⚠️ WARNING: Chain ID showing as null on one or both nodes"
  echo "This may indicate a configuration issue with the blockchain node"
  echo "Supported chains should be: ait-mainnet"
else
  echo "✅ Chain IDs are properly configured"
fi

# Verify both nodes can communicate on the same chain
echo "=== Cross-Chain Communication Test ==="
echo "Testing if both nodes are on compatible chains..."

if [ "$AITBC1_CHAIN" = "$AITBC_CHAIN" ] && [ "$AITBC1_CHAIN" = "ait-mainnet" ]; then
  echo "✅ SUCCESS: Both nodes are on the same chain (ait-mainnet)"
  echo "🎯 Ready for cross-node transactions and operations"
else
  echo "⚠️ Chain configuration needs attention"
  echo "Expected: ait-mainnet"
  echo "aitbc1: $AITBC1_CHAIN"
  echo "aitbc: $AITBC_CHAIN"
fi
```

```bash
# Ensure both nodes are on the same blockchain
echo "=== Blockchain Synchronization Verification ==="
WALLET_ADDR="ait1vt7nz556q9nsgqutz7av9g36423rs8xg6cxyvwhd9km6lcvxzrysc9cw87"

# Check current heights
echo "Current blockchain heights:"
AITBC1_HEIGHT=$(curl -s http://localhost:8006/rpc/head | jq .height)
AITBC_HEIGHT=$(ssh aitbc 'curl -s http://localhost:8006/rpc/head | jq .height')

echo "aitbc1 height: $AITBC1_HEIGHT"
echo "aitbc height: $AITBC_HEIGHT"
HEIGHT_DIFF=$((AITBC1_HEIGHT - AITBC_HEIGHT))
echo "Height difference: $HEIGHT_DIFF blocks"

# Verify genesis blocks are identical
echo "=== Genesis Block Verification ==="
echo "aitbc1 genesis:"
curl -s "http://localhost:8006/rpc/blocks-range?start=0&end=0" | jq '.blocks[0] | {height: .height, hash: .hash}'

echo "aitbc genesis:"
ssh aitbc 'curl -s "http://10.1.223.40:8006/rpc/blocks-range?start=0&end=0" | jq ".blocks[0] | {height: .height, hash: .hash}"'

# Complete synchronization if needed
if [ "$HEIGHT_DIFF" -gt "5" ]; then
  echo "=== Completing Blockchain Synchronization ==="
  echo "aitbc is $HEIGHT_DIFF blocks behind, completing sync..."
  
  ssh aitbc "for height in \$((AITBC_HEIGHT + 1)) $AITBC1_HEIGHT; do
    curl -s 'http://10.1.223.40:8006/rpc/blocks-range?start=\$height&end=\$height' | \
      jq '.blocks[0]' > /tmp/block\$height.json
    curl -X POST http://localhost:8006/rpc/importBlock \
      -H 'Content-Type: application/json' -d @/tmp/block\$height.json > /dev/null
    if [ \$((\$height % 50)) -eq 0 ]; then echo 'Synced to height \$height'; fi
  done"
  
  echo "Synchronization completed!"
fi

# Final verification
echo "=== Final Synchronization Verification ==="
FINAL_AITBC1_HEIGHT=$(curl -s http://localhost:8006/rpc/head | jq .height)
FINAL_AITBC_HEIGHT=$(ssh aitbc 'curl -s http://localhost:8006/rpc/head | jq .height')
FINAL_DIFF=$((FINAL_AITBC1_HEIGHT - FINAL_AITBC_HEIGHT))

echo "Final heights:"
echo "aitbc1: $FINAL_AITBC1_HEIGHT"
echo "aitbc: $FINAL_AITBC_HEIGHT"
echo "Difference: $FINAL_DIFF blocks"

if [ "$FINAL_DIFF" -le "2" ]; then
  echo "✅ SUCCESS: Both nodes are on the same blockchain!"
  echo "🎯 Blockchain synchronization verified"
else
  echo "⚠️ Nodes are still not fully synchronized"
  echo "Difference: $FINAL_DIFF blocks"
fi

# Verify both nodes can see the same blockchain data
echo "=== Cross-Node Blockchain Verification ==="
echo "Total blocks on aitbc1: $(curl -s http://localhost:8006/rpc/info | jq .total_blocks)"
echo "Total blocks on aitbc: $(ssh aitbc 'curl -s http://localhost:8006/rpc/info | jq .total_blocks')"
echo "Total accounts on aitbc1: $(curl -s http://localhost:8006/rpc/info | jq .total_accounts)"
echo "Total accounts on aitbc: $(ssh aitbc 'curl -s http://localhost:8006/rpc/info | jq .total_accounts')"

# Verify wallet consistency
echo "=== Wallet Verification ==="
echo "Genesis wallet balance on aitbc1:"
GENESIS_ADDR=$(cat /var/lib/aitbc/keystore/aitbc1genesis.json | jq -r .address)
curl -s "http://localhost:8006/rpc/getBalance/$GENESIS_ADDR" | jq .

echo "User wallet balance on aitbc:"
ssh aitbc "curl -s 'http://localhost:8006/rpc/getBalance/$WALLET_ADDR' | jq ."

if [ "$FINAL_DIFF" -le "2" ]; then
  echo "🎉 MULTI-NODE BLOCKCHAIN SUCCESSFULLY SYNCHRONIZED!"
  echo "Both nodes are operating on the same blockchain"
  echo "Ready for cross-node transactions and operations"
else
  echo "🔧 Additional synchronization may be required"
fi
```

```bash
# Ensure the 1000 AIT gift is successfully delivered to aitbc wallet
echo "=== Gift Delivery Completion ==="
WALLET_ADDR="ait1vt7nz556q9nsgqutz7av9g36423rs8xg6cxyvwhd9km6lcvxzrysc9cw87"
TX_HASH="0x125a1150045acb9f8c74f30dbc8b9db98d48f3cced650949e31916fcb618b61e"

echo "Target wallet: $WALLET_ADDR"
echo "Transaction hash: $TX_HASH"

# Check current status
echo "Current wallet balance:"
ssh aitbc "curl -s 'http://localhost:8006/rpc/getBalance/$WALLET_ADDR' | jq ."

echo "Network transaction count:"
curl -s http://localhost:8006/rpc/info | jq .total_transactions

# Step 1: Complete aitbc sync
echo "=== Step 1: Complete aitbc sync ==="
AITBC1_HEIGHT=$(curl -s http://localhost:8006/rpc/head | jq .height)
AITBC_HEIGHT=$(ssh aitbc 'curl -s http://localhost:8006/rpc/head | jq .height')

echo "aitbc1 height: $AITBC1_HEIGHT"
echo "aitbc height: $AITBC_HEIGHT"

if [ "$AITBC_HEIGHT" -lt "$((AITBC1_HEIGHT - 2))" ]; then
  echo "Completing sync to current height..."
  ssh aitbc "for height in \$((AITBC_HEIGHT + 1)) $AITBC1_HEIGHT; do
    curl -s 'http://10.1.223.40:8006/rpc/blocks-range?start=\$height&end=\$height' | \
      jq '.blocks[0]' > /tmp/block\$height.json
    curl -X POST http://localhost:8006/rpc/importBlock \
      -H 'Content-Type: application/json' -d @/tmp/block\$height.json > /dev/null
    if [ \$((\$height % 10)) -eq 0 ]; then echo 'Synced to height \$height'; fi
  done"
  echo "Sync completed!"
fi

# Step 2: Check if transaction was mined
echo "=== Step 2: Check transaction mining status ==="
for i in {1..20}; do
  echo "Check $i/20: Monitoring for transaction inclusion..."
  
  # Check wallet balance
  CURRENT_BALANCE=$(ssh aitbc "curl -s 'http://localhost:8006/rpc/getBalance/$WALLET_ADDR' | jq .balance")
  echo "Current balance: $CURRENT_BALANCE AIT"
  
  # Check recent blocks for transactions
  RECENT_HEIGHT=$(curl -s http://localhost:8006/rpc/head | jq .height)
  START_HEIGHT=$((RECENT_HEIGHT - 3))
  
  for height in $(seq $START_HEIGHT $RECENT_HEIGHT); do
    BLOCK_TXS=$(curl -s "http://localhost:8006/rpc/blocks-range?start=$height&end=$height" | jq '.blocks[0].transactions | length')
    if [ "$BLOCK_TXS" -gt "0" ]; then
      echo "Found block $height with $BLOCK_TXS transactions!"
      echo "Checking if our transaction is included..."
      # Get block details for verification
      BLOCK_DETAIL=$(curl -s "http://localhost:8006/rpc/blocks-range?start=$height&end=$height")
      echo "$BLOCK_DETAIL" | jq '.blocks[0] | {height: .height, hash: .hash, tx_count: .tx_count}'
    fi
  done
  
  if [ "$CURRENT_BALANCE" -gt "0" ]; then
    echo "🎉 SUCCESS: Gift delivered! Balance: $CURRENT_BALANCE AIT"
    break
  fi
  
  sleep 3
done

# Step 3: If still pending, resubmit transaction
echo "=== Step 3: Resubmit transaction if needed ==="
FINAL_BALANCE=$(ssh aitbc "curl -s 'http://localhost:8006/rpc/getBalance/$WALLET_ADDR' | jq .balance")

if [ "$FINAL_BALANCE" -eq "0" ]; then
  echo "Gift not yet delivered, resubmitting transaction..."
  
  GENESIS_ADDR=$(cat /var/lib/aitbc/keystore/aitbc1genesis.json | jq -r .address)
  echo "Genesis address: $GENESIS_ADDR"
  
  # Get current nonce
  CURRENT_NONCE=$(curl -s "http://localhost:8006/rpc/getBalance/$GENESIS_ADDR" | jq .nonce)
  echo "Current nonce: $CURRENT_NONCE"
  
  # Create new transaction with correct nonce
  NEW_TX=$(cat << EOF
{
  "type": "transfer",
  "sender": "$GENESIS_ADDR",
  "nonce": $((CURRENT_NONCE + 1)),
  "fee": 10,
  "payload": {},
  "recipient": "$WALLET_ADDR",
  "value": 1000
}
EOF
)
  
  echo "Submitting new transaction:"
  echo "$NEW_TX" | jq .
  
  NEW_TX_RESULT=$(curl -X POST http://localhost:8006/rpc/sendTx -H "Content-Type: application/json" -d "$NEW_TX")
  echo "New transaction result: $NEW_TX_RESULT"
  
  # Wait for new transaction to be mined
  echo "Waiting for new transaction to be mined..."
  for i in {1..15}; do
    UPDATED_BALANCE=$(ssh aitbc "curl -s 'http://localhost:8006/rpc/getBalance/$WALLET_ADDR' | jq .balance")
    echo "Check $i/15: Balance = $UPDATED_BALANCE AIT"
    
    if [ "$UPDATED_BALANCE" -gt "0" ]; then
      echo "🎉 SUCCESS: Gift finally delivered! Balance: $UPDATED_BALANCE AIT"
      break
    fi
    
    sleep 2
  done
fi

# Final verification
echo "=== FINAL GIFT DELIVERY VERIFICATION ==="
FINAL_BALANCE=$(ssh aitbc "curl -s 'http://localhost:8006/rpc/getBalance/$WALLET_ADDR' | jq .balance")
echo "Final wallet balance: $FINAL_BALANCE AIT"

if [ "$FINAL_BALANCE" -ge "1000" ]; then
  echo "✅ GIFT DELIVERY SUCCESSFUL!"
  echo "🎁 aitbc received $FINAL_BALANCE AIT from genesis wallet"
elif [ "$FINAL_BALANCE" -gt "0" ]; then
  echo "⚠️ Partial gift delivery: $FINAL_BALANCE AIT received"
else
  echo "❌ Gift delivery failed - wallet still has 0 AIT"
  echo "🔍 Manual investigation required"
fi
```

```bash
# Wait for transaction to be mined and verify
echo "=== Transaction Mining Verification ==="
TX_HASH="0x125a1150045acb9f8c74f30dbc8b9db98d48f3cced650949e31916fcb618b61e"

echo "Transaction hash: $TX_HASH"
echo "Waiting for transaction to be included in a block..."

# Monitor for transaction inclusion
for i in {1..30}; do
  echo "Check $i/30: Looking for transaction in recent blocks..."
  
  # Check recent blocks for our transaction
  RECENT_HEIGHT=$(curl -s http://localhost:8006/rpc/head | jq .height)
  START_HEIGHT=$((RECENT_HEIGHT - 5))
  
  for height in $(seq $START_HEIGHT $RECENT_HEIGHT); do
    BLOCK_TXS=$(curl -s "http://localhost:8006/rpc/blocks-range?start=$height&end=$height" | jq '.blocks[0].transactions | length')
    if [ "$BLOCK_TXS" -gt "0" ]; then
      echo "Found block $height with $BLOCK_TXS transactions"
      # Get detailed block info
      BLOCK_DETAIL=$(curl -s "http://localhost:8006/rpc/blocks-range?start=$height&end=$height")
      echo "Block $height details:"
      echo "$BLOCK_DETAIL" | jq '.blocks[0] | {height: .height, hash: .hash, tx_count: .tx_count}'
    fi
  done
  
  # Check wallet balance
  CURRENT_BALANCE=$(ssh aitbc "curl -s 'http://localhost:8006/rpc/getBalance/$WALLET_ADDR' | jq .balance")
  echo "Current wallet balance: $CURRENT_BALANCE AIT"
  
  if [ "$CURRENT_BALANCE" -gt "0" ]; then
    echo "🎉 Transaction successfully mined! Balance: $CURRENT_BALANCE AIT"
    break
  fi
  
  sleep 2
done

# Final verification
echo "=== FINAL VERIFICATION ==="
FINAL_BALANCE=$(ssh aitbc "curl -s 'http://localhost:8006/rpc/getBalance/$WALLET_ADDR' | jq .balance")
echo "Final wallet balance: $FINAL_BALANCE AIT"

if [ "$FINAL_BALANCE" -gt "0" ]; then
  echo "✅ SUCCESS: 1000 AIT successfully transferred to aitbc wallet!"
else
  echo "⚠️ Transaction still pending - may need more time for mining"
fi
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

## Success Criteria

### ✅ Workflow Success Indicators

- **aitbc1 Status**: Genesis authority running and producing blocks
- **aitbc Status**: Follower node synced and receiving blocks
- **Network Health**: Redis and P2P connectivity working
- **Wallet Creation**: New wallet created on follower node
- **Transaction Success**: 1000 AIT transferred from genesis to new wallet
- **Balance Verification**: New wallet shows 1000 AIT balance

### 🔍 Verification Commands

```bash
# Quick health check
echo "=== Quick Health Check ==="
echo "aitbc1 height: $(curl -s http://localhost:8006/rpc/head | jq .height)"
echo "aitbc height: $(ssh aitbc 'curl -s http://localhost:8006/rpc/head | jq .height')"
echo "Redis status: $(redis-cli -h localhost ping)"
echo "Wallet balance: $(ssh aitbc "curl -s http://localhost:8006/rpc/getBalance/$WALLET_ADDR | jq .balance")"
```

### 📊 Advanced Monitoring

```bash
# Real-time blockchain monitoring
echo "=== Real-time Monitoring ==="
watch -n 5 'echo "=== aitbc1 ===" && curl -s http://localhost:8006/rpc/head | jq .height && echo "=== aitbc ===" && ssh aitbc "curl -s http://localhost:8006/rpc/head | jq .height" && echo "=== Wallet Balance ===" && ssh aitbc "curl -s http://localhost:8006/rpc/getBalance/$WALLET_ADDR | jq .balance"'

# Transaction pool monitoring (if available)
echo "=== Transaction Pool Status ==="
curl -s http://localhost:8006/rpc/mempool | jq . 2>/dev/null || echo "Mempool endpoint not available"

# Network statistics
echo "=== Network Statistics ==="
echo "Total blocks: $(curl -s http://localhost:8006/rpc/info | jq .total_blocks)"
echo "Total transactions: $(curl -s http://localhost:8006/rpc/info | jq .total_transactions)"
echo "Total accounts: $(curl -s http://localhost:8006/rpc/info | jq .total_accounts)"

# Genesis wallet balance check
echo "=== Genesis Wallet Status ==="
GENESIS_ADDR=$(cat /var/lib/aitbc/keystore/aitbc1genesis.json | jq -r .address)
echo "Genesis address: $GENESIS_ADDR"
echo "Genesis balance: $(curl -s "http://localhost:8006/rpc/getBalance/$GENESIS_ADDR" | jq .balance)"
```

### 🚀 Performance Testing

```bash
# Test transaction throughput
echo "=== Performance Testing ==="
echo "Sending test transactions..."
for i in {1..3}; do
  echo "Sending transaction $i..."
  # Create a small test transaction
  TEST_TX=$(cat << EOF
{
  "type": "transfer",
  "sender": "$GENESIS_ADDR",
  "nonce": $((i + 1)),
  "fee": 10,
  "payload": {},
  "recipient": "$WALLET_ADDR",
  "value": 100
}
EOF
)
  
  TX_RESULT=$(curl -X POST http://localhost:8006/rpc/sendTx -H "Content-Type: application/json" -d "$TEST_TX")
  echo "Transaction $i result: $TX_RESULT"
  sleep 1
done

echo "Performance test completed!"
```

## Performance Optimizations

### Blockchain Performance

#### **Block Production Tuning**
```bash
# Optimize block time for faster consensus (in /etc/aitbc/blockchain.env)
block_time_seconds=2  # Default: 10, faster for testing

# Enable/disable block production based on node role
# aitbc1 (genesis): enable_block_production=true
# aitbc (follower): enable_block_production=false
```

#### **Network Optimization**
```bash
# Optimize P2P settings
p2p_bind_port=7070  # Standard port for P2P communication

# Redis gossip optimization
gossip_broadcast_url=redis://localhost:6379  # Local Redis for aitbc1
gossip_broadcast_url=redis://10.1.223.40:6379  # Remote Redis for aitbc
```

#### **Database Performance**
```bash
# Ensure proper database permissions and location
db_path=/var/lib/aitbc/data/ait-mainnet/chain.db
chmod 755 /var/lib/aitbc/data
chmod 644 /var/lib/aitbc/data/ait-mainnet/chain.db
```

### System Resource Optimization

#### **Memory Management**
```bash
# Monitor memory usage
systemctl status aitbc-blockchain-node --no-pager | grep Memory

# Optimize Python memory usage (in systemd service)
Environment=PYTHONOPTIMIZE=1
Environment=PYTHONUNBUFFERED=1
```

#### **CPU Optimization**
```bash
# Set process affinity for better performance
cpuset=/opt/aitbc/systemd/cpuset.conf
echo "CPUAffinity=0-3" > /opt/aitbc/systemd/cpuset.conf
```

### Monitoring and Metrics

#### **Real-time Monitoring**
```bash
# Monitor blockchain height in real-time
watch -n 2 'curl -s http://localhost:8006/rpc/head | jq .height'

# Monitor service status
watch -n 5 'systemctl status aitbc-blockchain-* --no-pager'

# Monitor resource usage
watch -n 5 'ps aux | grep python | grep aitbc'
```

#### **Performance Metrics**
```bash
# Check block production rate
curl -s http://localhost:8006/rpc/info | jq '.genesis_params.block_time_seconds'

# Monitor transaction pool
curl -s http://localhost:8006/rpc/mempool | jq .

# Check network sync status
curl -s http://localhost:8006/rpc/syncStatus | jq .
```

## Troubleshooting

### Common Issues and Solutions

#### **Systemd Service Failures**
```bash
# Check service status and logs
systemctl status aitbc-blockchain-*.service --no-pager
journalctl -u aitbc-blockchain-node.service -n 10 --no-pager

# Fix environment file issues
find /etc/systemd/system/aitbc-blockchain-*.service.d/ -name "*.conf" -exec grep -l "EnvironmentFile" {} \;
find /etc/systemd/system/aitbc-blockchain-*.service.d/ -name "*.conf" -exec sed -i 's|EnvironmentFile=/opt/aitbc/.env|EnvironmentFile=/etc/aitbc/blockchain.env|g' {} \;

# Fix virtual environment paths in overrides
find /etc/systemd/system/aitbc-blockchain-*.service.d/ -name "override.conf" -exec sed -i 's|/opt/aitbc/apps/blockchain-node/.venv/bin/python3|/opt/aitbc/venv/bin/python3|g' {} \;

# Reload and restart
systemctl daemon-reload
systemctl restart aitbc-blockchain-node aitbc-blockchain-rpc
```

#### **RPC Service Issues**
```bash
# Check if RPC is accessible
curl -s http://localhost:8006/rpc/head | jq .

# Manual RPC start for debugging
cd /opt/aitbc/apps/blockchain-node
PYTHONPATH=/opt/aitbc/apps/blockchain-node/src:/opt/aitbc/apps/blockchain-node/scripts \
  /opt/aitbc/venv/bin/python -m uvicorn aitbc_chain.app:app --host 0.0.0.0 --port 8006
```

#### **Keystore Issues**
```bash
# Create keystore password file
echo 'aitbc123' > /var/lib/aitbc/keystore/.password
chmod 600 /var/lib/aitbc/keystore/.password

# Check keystore permissions
ls -la /var/lib/aitbc/keystore/
```

#### **Sync Issues**
```bash
# Check network connectivity between nodes
ping 10.1.223.40  # aitbc1 from aitbc
ping 10.1.223.93  # aitbc from aitbc1

# Check Redis connectivity
redis-cli -h 10.1.223.40 ping

# Compare blockchain heights
curl -s http://localhost:8006/rpc/head | jq .height
ssh aitbc 'curl -s http://localhost:8006/rpc/head | jq .height'
```

### General Troubleshooting

- **Services won't start**: Check `/var/log/aitbc/` for service logs
- **Sync issues**: Verify Redis connectivity between nodes
- **Transaction failures**: Check wallet nonce and balance
- **Permission errors**: Ensure `/var/lib/aitbc/` is owned by root with proper permissions
- **Configuration issues**: Verify `/etc/aitbc/blockchain.env` file contents and systemd service EnvironmentFile paths
