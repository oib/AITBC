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
- `/var/lib/aitbc/data` - Blockchain database files
- `/var/lib/aitbc/keystore` - Wallet credentials
- `/etc/aitbc/` - Configuration files
- `/var/log/aitbc/` - Service logs

## Steps

### 1. Prepare aitbc1 (Genesis Authority Node)

```bash
# SSH to aitbc1
ssh aitbc1

# Pull latest code
cd /opt/aitbc
git pull origin main

# Install/update dependencies
/opt/aitbc/venv/bin/pip install -r requirements.txt

# Create required directories
mkdir -p /var/lib/aitbc/data /var/lib/aitbc/keystore /etc/aitbc /var/log/aitbc

# Set up environment configuration
cat > /etc/aitbc/blockchain.env << 'EOF'
# Blockchain Node Configuration (aitbc1 - genesis authority)
chain_id=ait-mainnet
supported_chains=ait-mainnet
rpc_bind_host=0.0.0.0
rpc_bind_port=8006
p2p_bind_host=0.0.0.0
p2p_bind_port=7070
proposer_id=aitbc1genesis
enable_block_production=true
block_time_seconds=10
keystore_path=/var/lib/aitbc/keystore
keystore_password_file=/var/lib/aitbc/keystore/.password
gossip_backend=broadcast
gossip_broadcast_url=redis://localhost:6379
db_path=/var/lib/aitbc/data/ait-mainnet/chain.db
mint_per_unit=0
coordinator_ratio=0.05
EOF

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

# Update systemd services to use new paths
sed -i 's|EnvironmentFile=/opt/aitbc/.env|EnvironmentFile=/etc/aitbc/blockchain.env|g' /opt/aitbc/systemd/aitbc-blockchain-*.service
sed -i 's|WorkingDirectory=/opt/aitbc/apps/blockchain-node|WorkingDirectory=/opt/aitbc/apps/blockchain-node|g' /opt/aitbc/systemd/aitbc-blockchain-*.service
sed -i 's|ExecStart=/opt/aitbc/venv/bin/python|ExecStart=/opt/aitbc/venv/bin/python|g' /opt/aitbc/systemd/aitbc-blockchain-*.service

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

# Set up follower configuration
cat > /etc/aitbc/blockchain.env << 'EOF'
# Blockchain Node Configuration (aitbc - follower node)
chain_id=ait-mainnet
supported_chains=ait-mainnet
rpc_bind_host=0.0.0.0
rpc_bind_port=8006
p2p_bind_host=0.0.0.0
p2p_bind_port=7070
proposer_id=follower-node-aitbc
enable_block_production=false
block_time_seconds=10
keystore_path=/var/lib/aitbc/keystore
keystore_password_file=/var/lib/aitbc/keystore/.password
gossip_backend=broadcast
gossip_broadcast_url=redis://10.1.223.40:6379
db_path=/var/lib/aitbc/data/ait-mainnet/chain.db
mint_per_unit=0
coordinator_ratio=0.05
EOF

# Copy genesis from aitbc1
scp aitbc1:/var/lib/aitbc/data/ait-mainnet/genesis.json /var/lib/aitbc/data/ait-mainnet/
scp aitbc1:/var/lib/aitbc/data/ait-mainnet/allocations.json /var/lib/aitbc/data/ait-mainnet/

# Update systemd services
sed -i 's|EnvironmentFile=/opt/aitbc/.env|EnvironmentFile=/etc/aitbc/blockchain.env|g' /opt/aitbc/systemd/aitbc-blockchain-*.service

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
echo "=== aitbc1 height ==="
ssh aitbc1 'curl -s http://localhost:8006/rpc/head | jq .height'

echo "=== aitbc height ==="
curl -s http://localhost:8006/rpc/head | jq .height

echo "=== aitbc wallet balance ==="
curl -s "http://localhost:8006/rpc/getBalance/$WALLET_ADDR" | jq .
```

## Troubleshooting

- **Services won't start**: Check `/var/log/aitbc/` for service logs
- **Sync issues**: Verify Redis connectivity between nodes
- **Transaction failures**: Check wallet nonce and balance
- **Permission errors**: Ensure `/var/lib/aitbc/` is owned by root with proper permissions

## Notes

- Only one `.env` file is used at `/etc/aitbc/blockchain.env`
- All services use the central venv at `/opt/aitbc/venv`
- Database files are stored in `/var/lib/aitbc/data`
- Wallet credentials are in `/var/lib/aitbc/keystore`
- Service logs go to `/var/log/aitbc/` via journald
