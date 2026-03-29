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

## Directory Structure

- `/opt/aitbc/venv` - Central Python virtual environment
- `/opt/aitbc/requirements.txt` - Python dependencies
- `/opt/aitbc/.env` - Central environment configuration
- `/var/lib/aitbc/data` - Blockchain database files
- `/var/lib/aitbc/keystore` - Wallet credentials
- `/etc/aitbc/` - System configuration files
- `/var/log/aitbc/` - Service logs

## Steps

### Environment Configuration

The workflow uses the central `/opt/aitbc/.env` file as the base configuration for both nodes:

- **Base Configuration**: The central `.env` contains all default settings
- **Node-Specific Adaptation**: Each node adapts the `.env` for its role (genesis vs follower)
- **Path Updates**: Paths are updated to use the standardized directory structure
- **Backup Strategy**: Original `.env` is backed up before modifications

### 1. Prepare aitbc1 (Genesis Authority Node)

```bash
# We are already on aitbc1 node (localhost)
# No SSH needed - running locally

# Pull latest code
cd /opt/aitbc
git pull origin main

# Install/update dependencies
/opt/aitbc/venv/bin/pip install -r requirements.txt

# Create required directories
mkdir -p /var/lib/aitbc/data /var/lib/aitbc/keystore /etc/aitbc /var/log/aitbc

# Copy and adapt central .env for aitbc1 (genesis authority)
cp /opt/aitbc/.env /opt/aitbc/.env.aitbc1.backup

# Update .env for aitbc1 genesis authority configuration
sed -i 's|proposer_id=.*|proposer_id=aitbc1genesis|g' /opt/aitbc/.env
sed -i 's|keystore_path=/opt/aitbc/apps/blockchain-node/keystore|keystore_path=/var/lib/aitbc/keystore|g' /opt/aitbc/.env
sed -i 's|keystore_password_file=/opt/aitbc/apps/blockchain-node/keystore/.password|keystore_password_file=/var/lib/aitbc/keystore/.password|g' /opt/aitbc/.env
sed -i 's|db_path=./data/ait-mainnet/chain.db|db_path=/var/lib/aitbc/data/ait-mainnet/chain.db|g' /opt/aitbc/.env
sed -i 's|enable_block_production=true|enable_block_production=true|g' /opt/aitbc/.env
sed -i 's|gossip_broadcast_url=redis://127.0.0.1:6379|gossip_broadcast_url=redis://localhost:6379|g' /opt/aitbc/.env
sed -i 's|p2p_bind_port=8005|p2p_bind_port=7070|g' /opt/aitbc/.env

# Add trusted proposers for follower nodes
echo "trusted_proposers=aitbc1genesis" >> /opt/aitbc/.env

# Create genesis block with wallets
cd /opt/aitbc/apps/blockchain-node
/opt/aitbc/venv/bin/python scripts/setup_production.py \
  --base-dir /opt/aitbc/apps/blockchain-node \
  --chain-id ait-mainnet \
  --total-supply 1000000000

# Copy genesis and allocations to standard location
mkdir -p /var/lib/aitbc/data/ait-mainnet
cp data/ait-mainnet/genesis.json /var/lib/aitbc/data/ait-mainnet/
cp data/ait-mainnet/allocations.json /var/lib/aitbc/data/ait-mainnet/
cp keystore/* /var/lib/aitbc/keystore/

# Update systemd services to use central .env and standard paths
# Note: systemd services already reference /opt/aitbc/.env by default
# The separate .env.production file has been merged into central .env
# No need to modify EnvironmentFile as they should use the central .env
# Just ensure the paths in .env are correct for the standard directory structure

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

# Create required directories
mkdir -p /var/lib/aitbc/data /var/lib/aitbc/keystore /etc/aitbc /var/log/aitbc

# Copy and adapt central .env for aitbc (follower node)
cp /opt/aitbc/.env /opt/aitbc/.env.aitbc.backup

# Update .env for aitbc follower node configuration
sed -i 's|proposer_id=.*|proposer_id=follower-node-aitbc|g' /opt/aitbc/.env
sed -i 's|keystore_path=/opt/aitbc/apps/blockchain-node/keystore|keystore_path=/var/lib/aitbc/keystore|g' /opt/aitbc/.env
sed -i 's|keystore_password_file=/opt/aitbc/apps/blockchain-node/keystore/.password|keystore_password_file=/var/lib/aitbc/keystore/.password|g' /opt/aitbc/.env
sed -i 's|db_path=./data/ait-mainnet/chain.db|db_path=/var/lib/aitbc/data/ait-mainnet/chain.db|g' /opt/aitbc/.env
sed -i 's|enable_block_production=true|enable_block_production=false|g' /opt/aitbc/.env
sed -i 's|gossip_broadcast_url=redis://127.0.0.1:6379|gossip_broadcast_url=redis://10.1.223.40:6379|g' /opt/aitbc/.env
sed -i 's|p2p_bind_port=8005|p2p_bind_port=7070|g' /opt/aitbc/.env
sed -i 's|trusted_proposers=.*|trusted_proposers=ait1apmaugx6csz50q07m99z8k44llry0zpl0yurl23hygarcey8z85qy4zr96|g' /opt/aitbc/.env

# Note: aitbc should sync genesis from aitbc1, not copy it
# The follower node will receive the genesis block via blockchain sync

# Note: systemd services already reference /opt/aitbc/.env by default
# No need to modify EnvironmentFile as they should use the central .env
# The .env file has been updated above with follower node configuration

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
# On aitbc, create a new wallet
cd /opt/aitbc/apps/blockchain-node
/opt/aitbc/venv/bin/python scripts/keystore.py \
  --name aitbc-user \
  --create \
  --password $(cat /var/lib/aitbc/keystore/.password)

# Note the new wallet address
WALLET_ADDR=$(cat /var/lib/aitbc/keystore/aitbc-user.json | jq -r '.address')
echo "New wallet: $WALLET_ADDR"
```

### 6. Send 1000 AIT from Genesis to aitbc Wallet

```bash
# On aitbc1, create and sign transaction
cd /opt/aitbc/apps/blockchain-node

# Get genesis wallet private key
PASSWORD=$(cat /var/lib/aitbc/keystore/.password)
GENESIS_KEY=$(/opt/aitbc/venv/bin/python -c "
import json, sys
from cryptography.hazmat.primitives.asymmetric import ed25519
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.primitives import hashes
import base64

with open('/var/lib/aitbc/keystore/aitbc1genesis.json') as f:
    ks = json.load(f)

# Decrypt private key
crypto = ks['crypto']
salt = bytes.fromhex(crypto['kdfparams']['salt'])
kdf = PBKDF2HMAC(hashes.SHA256(), 32, salt, crypto['kdfparams']['c'])
key = kdf.derive('$PASSWORD'.encode())
aesgcm = AESGCM(key)
nonce = bytes.fromhex(crypto['cipherparams']['nonce'])
priv = aesgcm.decrypt(nonce, bytes.fromhex(crypto['ciphertext']), None)
print(priv.hex())
")

# Create transaction to send 1000 AIT
TX_JSON=$(cat << EOF
{
  "sender": "$(cat /var/lib/aitbc/keystore/aitbc1genesis.json | jq -r '.address')",
  "recipient": "$WALLET_ADDR",
  "value": 1000,
  "fee": 10,
  "nonce": 0,
  "type": "transfer",
  "payload": {}
}
EOF
)

# Submit transaction via RPC
curl -X POST http://localhost:8006/sendTx \
  -H "Content-Type: application/json" \
  -d "$TX_JSON"

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

The workflow uses `/opt/aitbc/.env` as the central configuration file:

```bash
# View current configuration
cat /opt/aitbc/.env

# Restore from backup if needed
cp /opt/aitbc/.env.aitbc1.backup /opt/aitbc/.env  # aitbc1
cp /opt/aitbc/.env.aitbc.backup /opt/aitbc/.env   # aitbc

# Key configuration differences:
# aitbc1: proposer_id=aitbc1genesis, enable_block_production=true
# aitbc: proposer_id=follower-node-aitbc, enable_block_production=false
```

### Service Configuration

- **Environment File**: All services use `/opt/aitbc/.env` (merged from .env.production)
- **Virtual Environment**: Central venv at `/opt/aitbc/venv`
- **Database Files**: `/var/lib/aitbc/data`
- **Wallet Credentials**: `/var/lib/aitbc/keystore`
- **Service Logs**: `/var/log/aitbc/` via journald
- **Standardized Paths**: All paths use `/var/lib/aitbc/` structure
- **No Separate Config Files**: `.env.production` merged into central `.env`

## Troubleshooting

- **Services won't start**: Check `/var/log/aitbc/` for service logs
- **Sync issues**: Verify Redis connectivity between nodes
- **Transaction failures**: Check wallet nonce and balance
- **Permission errors**: Ensure `/var/lib/aitbc/` is owned by root with proper permissions
- **Configuration issues**: Verify `.env` file contents and systemd service EnvironmentFile paths
