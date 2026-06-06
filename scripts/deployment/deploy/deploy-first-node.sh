#!/bin/bash

# Deploy the first blockchain node

set -e

echo "🚀 Deploying First Blockchain Node"
echo "================================="

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

NODE1_DIR="/opt/blockchain-node"

# Create configuration for first node
print_status "Creating configuration for first node..."
cat > $NODE1_DIR/.env << EOF
CHAIN_ID=ait-devnet
DB_PATH=./data/chain.db
RPC_BIND_HOST=127.0.0.1
RPC_BIND_PORT=8080
P2P_BIND_HOST=0.0.0.0
P2P_BIND_PORT=7070
PROPOSER_KEY=node1_proposer_key_$(date +%s)
MINT_PER_UNIT=1000
COORDINATOR_RATIO=0.05
GOSSIP_BACKEND=http
GOSSIP_BROADCAST_URL=http://127.0.0.1:7071/gossip
EOF

# Create data directory
mkdir -p $NODE1_DIR/data/devnet

# Generate genesis file
print_status "Generating genesis file..."
cd $NODE1_DIR
export PYTHONPATH="${NODE1_DIR}/src:${NODE1_DIR}/scripts:${PYTHONPATH:-}"
python3 scripts/make_genesis.py --output data/devnet/genesis.json --force

# Create systemd service
print_status "Creating systemd service..."
sudo cat > /etc/systemd/system/blockchain-node.service << EOF
[Unit]
Description=AITBC Blockchain Node 1
After=network.target

[Service]
Type=exec
User=root
WorkingDirectory=$NODE1_DIR
Environment=PATH=$NODE1_DIR/.venv/bin:/usr/local/bin:/usr/bin:/bin
Environment=PYTHONPATH=$NODE1_DIR/src:$NODE1_DIR/scripts
ExecStart=$NODE1_DIR/.venv/bin/python3 -m aitbc_chain.main
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

# Create RPC API service
print_status "Creating RPC API service..."
sudo cat > /etc/systemd/system/blockchain-rpc.service << EOF
[Unit]
Description=AITBC Blockchain RPC API 1
After=blockchain-node.service

[Service]
Type=exec
User=root
WorkingDirectory=$NODE1_DIR
Environment=PATH=$NODE1_DIR/.venv/bin:/usr/local/bin:/usr/bin:/bin
Environment=PYTHONPATH=$NODE1_DIR/src:$NODE1_DIR/scripts
ExecStart=$NODE1_DIR/.venv/bin/python3 -m uvicorn aitbc_chain.app:app --host 0.0.0.0 --port 8080
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

# Setup Python environment if not exists
if [ ! -d "$NODE1_DIR/.venv" ]; then
    print_status "Setting up Python environment..."
    cd $NODE1_DIR
    python3 -m venv .venv
    source .venv/bin/activate
    pip install --upgrade pip
    pip install -e .
fi

# Enable and start services
print_status "Enabling and starting services..."
sudo systemctl daemon-reload
sudo systemctl enable blockchain-node blockchain-rpc
sudo systemctl start blockchain-node blockchain-rpc

# Check status
print_status "Checking service status..."
sudo systemctl status blockchain-node --no-pager -l
sudo systemctl status blockchain-rpc --no-pager -l

echo ""
print_status "✅ First blockchain node deployed!"
echo ""
echo "Node 1 RPC: http://127.0.0.1:8080"
echo "Node 2 RPC: http://127.0.0.1:8081"
echo ""
echo "To check logs:"
echo "  Node 1: sudo journalctl -u blockchain-node -f"
echo "  Node 2: sudo journalctl -u blockchain-node-2 -f"
