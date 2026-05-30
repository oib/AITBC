# Blockchain Setup

This guide covers configuring the AITBC blockchain node for follower nodes on the island.

## Prerequisites

- Ubuntu Linux system
- Python 3.13+
- Network access to hub.aitbc.bubuit.net
- AITBC codebase installed

## 1. Install AITBC Blockchain Node

```bash
# Clone repository (if not already done)
cd /opt
git clone <aitbc-repo-url> aitbc
cd /opt/aitbc

# Install dependencies
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

## 2. Configure Blockchain Environment

Create `/etc/aitbc/blockchain.env`:

```bash
CHAIN_ID=ait-hub.aitbc.bubuit.net
SUPPORTED_CHAINS=ait-hub.aitbc.bubuit.net
RPC_BIND_HOST=0.0.0.0
RPC_BIND_PORT=8006
P2P_BIND_HOST=0.0.0.0
P2P_BIND_PORT=7070
ENABLE_BLOCK_PRODUCTION=false  # Set to false for follower nodes
GOSSIP_BROADCAST_URL=redis://127.0.0.1:6379
MEMPOOL_BACKEND=database
MEMPOOL_DB_URL=postgresql+psycopg2://aitbc_mempool:password@localhost:5432/aitbc_mempool
PROPOSER_ID=ait1db5247d03ca2e40f3995a583b2c097ab703efd4d
DEFAULT_PEER_RPC_URL=http://hub.aitbc.bubuit.net:8006
P2P_NODE_ID=<your-node-id>
P2P_PEERS=auto
```

## 3. Setup Genesis Block

```bash
# Create data directory
mkdir -p /var/lib/aitbc/data/ait-hub.aitbc.bubuit.net/

# Copy genesis.json from hub (must match hub's genesis)
# Genesis hash: cb501afac77f861ad145aa7fc1106bb8f9caa90ed5c2498f0d4e73107c327504
```

**Genesis file content:**
```json
{
  "chain_id": "ait-hub.aitbc.bubuit.net",
  "block": {
    "height": 0,
    "hash": "cb501afac77f861ad145aa7fc1106bb8f9caa90ed5c2498f0d4e73107c327504",
    "parent_hash": "0x00",
    "proposer": "ait1db5247d03ca2e40f3995a583b2c097ab703efd4d",
    "timestamp": "2026-05-30T16:50:31.562096+00:00",
    "tx_count": 0,
    "chain_id": "ait-hub.aitbc.bubuit.net",
    "state_root": "0x00",
    "metadata": {
      "chain_type": "mainnet",
      "purpose": "production",
      "consensus_algorithm": "poa"
    }
  },
  "allocations": [
    {
      "address": "ait1db5247d03ca2e40f3995a583b2c097ab703efd4d",
      "balance": 1000000000,
      "nonce": 0
    }
  ]
}
```

## 4. Start Blockchain Services

```bash
# Create systemd service for blockchain node
cat > /etc/systemd/system/aitbc-blockchain-node.service << 'EOF'
[Unit]
Description=AITBC Blockchain Node
After=network.target postgresql.service redis.service

[Service]
Type=simple
User=root
WorkingDirectory=/opt/aitbc
Environment=PATH=/usr/bin:/usr/local/bin:/usr/bin:/bin
EnvironmentFile=/etc/aitbc/blockchain.env
ExecStart=/opt/aitbc/venv/bin/python -m aitbc_chain.main
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

# Create systemd service for RPC
cat > /etc/systemd/system/aitbc-blockchain-rpc.service << 'EOF'
[Unit]
Description=AITBC Blockchain RPC API
After=network.target aitbc-blockchain-node.service

[Service]
Type=simple
User=root
WorkingDirectory=/opt/aitbc
EnvironmentFile=/etc/aitbc/blockchain.env
ExecStart=/opt/aitbc/venv/bin/python -m uvicorn aitbc_chain.app:app --host 0.0.0.0 --port 8006
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

# Enable and start services
systemctl daemon-reload
systemctl enable aitbc-blockchain-node.service
systemctl enable aitbc-blockchain-rpc.service
systemctl start aitbc-blockchain-node.service
systemctl start aitbc-blockchain-rpc.service
```

## 5. Verify Sync

```bash
# Check health
curl -s http://localhost:8006/health

# Check genesis block
curl -s http://localhost:8006/rpc/blocks/0

# Should show hash: cb501afac77f861ad145aa7fc1106bb8f9caa90ed5c2498f0d4e73107c327504
```

## See Also

- [Hermes Messaging Setup](hermes-messaging.md)
- [Troubleshooting](troubleshooting.md)
- [Network Requirements](network-requirements.md)
