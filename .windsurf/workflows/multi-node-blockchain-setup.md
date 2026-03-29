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
sed -i 's|EnvironmentFile=/opt/aitbc/.env|EnvironmentFile=/etc/aitbc/blockchain.env|g' /opt/aitbc/systemd/aitbc-blockchain-*.service
# Update drop-in configs
find /etc/systemd/system/aitbc-blockchain-*.service.d/ -name "10-central-env.conf" -exec sed -i 's|EnvironmentFile=/opt/aitbc/.env|EnvironmentFile=/etc/aitbc/blockchain.env|g' {} \; 2>/dev/null || true
# Fix override configs (wrong venv paths)
find /etc/systemd/system/aitbc-blockchain-*.service.d/ -name "override.conf" -exec sed -i 's|/opt/aitbc/apps/blockchain-node/.venv/bin/python3|/opt/aitbc/venv/bin/python3|g' {} \; 2>/dev/null || true
systemctl daemon-reload

# 3. Move central config to standard location
cp /opt/aitbc/.env /etc/aitbc/blockchain.env.backup 2>/dev/null || true
mv /opt/aitbc/.env /etc/aitbc/blockchain.env 2>/dev/null || true

# 4. Setup AITBC CLI tool
python3 -m venv /opt/aitbc/cli/venv 2>/dev/null || true
source /opt/aitbc/cli/venv/bin/activate
pip install -e /opt/aitbc/cli/ 2>/dev/null || true
echo 'alias aitbc="source /opt/aitbc/cli/venv/bin/activate && aitbc"' >> ~/.bashrc
source ~/.bashrc

# 5. Clean old data (optional but recommended)
rm -rf /var/lib/aitbc/data/ait-mainnet/*
rm -rf /var/lib/aitbc/keystore/*

# 6. Create keystore password file
echo 'aitbc123' > /var/lib/aitbc/keystore/.password
chmod 600 /var/lib/aitbc/keystore/.password

# 7. Verify setup
aitbc --help 2>/dev/null || echo "CLI available but limited commands"
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
sed -i 's|proposer_id=.*|proposer_id=aitbc1genesis|g' /etc/aitbc/blockchain.env
sed -i 's|keystore_path=/opt/aitbc/apps/blockchain-node/keystore|keystore_path=/var/lib/aitbc/keystore|g' /etc/aitbc/blockchain.env
sed -i 's|keystore_password_file=/opt/aitbc/apps/blockchain-node/keystore/.password|keystore_password_file=/var/lib/aitbc/keystore/.password|g' /etc/aitbc/blockchain.env
sed -i 's|db_path=./data/ait-mainnet/chain.db|db_path=/var/lib/aitbc/data/ait-mainnet/chain.db|g' /etc/aitbc/blockchain.env
sed -i 's|enable_block_production=true|enable_block_production=true|g' /etc/aitbc/blockchain.env
sed -i 's|gossip_broadcast_url=redis://127.0.0.1:6379|gossip_broadcast_url=redis://localhost:6379|g' /etc/aitbc/blockchain.env
sed -i 's|p2p_bind_port=8005|p2p_bind_port=7070|g' /etc/aitbc/blockchain.env

# Add trusted proposers for follower nodes
echo "trusted_proposers=aitbc1genesis" >> /etc/aitbc/blockchain.env

# Create genesis block with wallets (using Python script until CLI is fully implemented)
cd /opt/aitbc/apps/blockchain-node
/opt/aitbc/venv/bin/python scripts/setup_production.py \
  --base-dir /opt/aitbc/apps/blockchain-node \
  --chain-id ait-mainnet \
  --total-supply 1000000000

# Get actual genesis wallet address and update config
GENESIS_ADDR=$(cat /opt/aitbc/apps/blockchain-node/keystore/aitbc1genesis.json | jq -r '.address')
echo "Genesis address: $GENESIS_ADDR"
sed -i "s|proposer_id=.*|proposer_id=$GENESIS_ADDR|g" /etc/aitbc/blockchain.env
sed -i "s|trusted_proposers=.*|trusted_proposers=$GENESIS_ADDR|g" /etc/aitbc/blockchain.env

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
# ⚠️  DO NOT: scp aitbc1:/var/lib/aitbc/data/ait-mainnet/genesis.json /var/lib/aitbc/data/ait-mainnet/
# ✅ INSTEAD: Wait for automatic sync via blockchain protocol

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
