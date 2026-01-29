#!/bin/bash

# Setup gossip relay to connect blockchain nodes

set -e

echo "🌐 Setting up Gossip Relay for Blockchain Nodes"
echo "=============================================="

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

print_status() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

# Stop existing nodes
print_status "Stopping blockchain nodes..."
sudo systemctl stop blockchain-node blockchain-node-2 blockchain-rpc blockchain-rpc-2 2>/dev/null || true

# Update node configurations to use broadcast backend
print_status "Updating Node 1 configuration..."
sudo cat > /opt/blockchain-node/.env << EOF
CHAIN_ID=ait-devnet
DB_PATH=./data/chain.db
RPC_BIND_HOST=127.0.0.1
RPC_BIND_PORT=8082
P2P_BIND_HOST=0.0.0.0
P2P_BIND_PORT=7070
PROPOSER_KEY=node1_proposer_key_$(date +%s)
MINT_PER_UNIT=1000
COORDINATOR_RATIO=0.05
GOSSIP_BACKEND=broadcast
GOSSIP_BROADCAST_URL=http://127.0.0.1:7070/gossip
EOF

print_status "Updating Node 2 configuration..."
sudo cat > /opt/blockchain-node-2/.env << EOF
CHAIN_ID=ait-devnet
DB_PATH=./data/chain2.db
RPC_BIND_HOST=127.0.0.1
RPC_BIND_PORT=8081
P2P_BIND_HOST=0.0.0.0
P2P_BIND_PORT=7071
PROPOSER_KEY=node2_proposer_key_$(date +%s)
MINT_PER_UNIT=1000
COORDINATOR_RATIO=0.05
GOSSIP_BACKEND=broadcast
GOSSIP_BROADCAST_URL=http://127.0.0.1:7070/gossip
EOF

# Create gossip relay service
print_status "Creating gossip relay service..."
sudo cat > /etc/systemd/system/blockchain-gossip-relay.service << EOF
[Unit]
Description=AITBC Blockchain Gossip Relay
After=network.target

[Service]
Type=exec
User=root
WorkingDirectory=/opt/blockchain-node
Environment=PATH=/opt/blockchain-node/.venv/bin:/usr/local/bin:/usr/bin:/bin
Environment=PYTHONPATH=/opt/blockchain-node/src:/opt/blockchain-node/scripts
ExecStart=/opt/blockchain-node/.venv/bin/python3 -m aitbc_chain.gossip.relay --port 7070 --host 0.0.0.0
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

# Enable and start gossip relay
print_status "Starting gossip relay..."
sudo systemctl daemon-reload
sudo systemctl enable blockchain-gossip-relay
sudo systemctl start blockchain-gossip-relay

# Wait for relay to start
sleep 2

# Check if relay is running
print_status "Checking gossip relay status..."
sudo systemctl status blockchain-gossip-relay --no-pager | head -10

# Restart blockchain nodes
print_status "Restarting blockchain nodes with shared gossip..."
sudo systemctl start blockchain-node blockchain-node-2 blockchain-rpc blockchain-rpc-2

# Wait for nodes to start
sleep 3

# Check status
print_status "Checking node status..."
sudo systemctl status blockchain-node blockchain-node-2 --no-pager | grep -E 'Active:|Main PID:'

echo ""
print_status "✅ Gossip relay setup complete!"
echo ""
echo "Nodes are now connected via shared gossip backend."
echo "They should sync blocks and transactions."
echo ""
echo "To verify connectivity:"
echo "  1. Run: python /opt/test_blockchain_simple.py"
echo "  2. Check if heights are converging"
echo ""
echo "Gossip relay logs: sudo journalctl -u blockchain-gossip-relay -f"
