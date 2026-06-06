#!/bin/bash

# Deploy a second blockchain node on the same server

set -e

echo "🚀 Deploying Second Blockchain Node"
echo "=================================="

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

# Create directory for second node
print_status "Creating directory for second node..."
NODE2_DIR="/opt/blockchain-node-2"
sudo mkdir -p $NODE2_DIR
sudo chown $USER:$USER $NODE2_DIR

# Copy blockchain node code
print_status "Copying blockchain node code..."
cp -r /opt/blockchain-node/* $NODE2_DIR/

# Create configuration for second node
print_status "Creating configuration for second node..."
cat > $NODE2_DIR/.env << EOF
CHAIN_ID=ait-devnet
DB_PATH=./data/chain2.db
RPC_BIND_HOST=127.0.0.1
RPC_BIND_PORT=8081
P2P_BIND_HOST=0.0.0.0
P2P_BIND_PORT=7071
PROPOSER_KEY=node2_proposer_key_$(date +%s)
MINT_PER_UNIT=1000
COORDINATOR_RATIO=0.05
GOSSIP_BACKEND=http
GOSSIP_BROADCAST_URL=http://127.0.0.1:7070/gossip
EOF

# Create data directory
mkdir -p $NODE2_DIR/data/devnet

# Generate genesis file (same as first node)
print_status "Generating genesis file..."
cd $NODE2_DIR
export PYTHONPATH="${NODE2_DIR}/src:${NODE2_DIR}/scripts:${PYTHONPATH:-}"
python3 scripts/make_genesis.py --output data/devnet/genesis.json --force

# Create systemd service
print_status "Creating systemd service..."
sudo cat > /etc/systemd/system/blockchain-node-2.service << EOF
[Unit]
Description=AITBC Blockchain Node 2
After=network.target

[Service]
Type=exec
User=root
WorkingDirectory=$NODE2_DIR
Environment=PATH=$NODE2_DIR/.venv/bin:/usr/local/bin:/usr/bin:/bin
Environment=PYTHONPATH=$NODE2_DIR/src:$NODE2_DIR/scripts
ExecStart=$NODE2_DIR/.venv/bin/python3 -m aitbc_chain.main
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

# Create RPC API service
print_status "Creating RPC API service..."
sudo cat > /etc/systemd/system/blockchain-rpc-2.service << EOF
[Unit]
Description=AITBC Blockchain RPC API 2
After=blockchain-node-2.service

[Service]
Type=exec
User=root
WorkingDirectory=$NODE2_DIR
Environment=PATH=$NODE2_DIR/.venv/bin:/usr/local/bin:/usr/bin:/bin
Environment=PYTHONPATH=$NODE2_DIR/src:$NODE2_DIR/scripts
ExecStart=$NODE2_DIR/.venv/bin/python3 -m uvicorn aitbc_chain.app:app --host 0.0.0.0 --port 8081
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

# Setup Python environment
print_status "Setting up Python environment..."
cd $NODE2_DIR
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -e .

# Enable and start services
print_status "Enabling and starting services..."
sudo systemctl daemon-reload
sudo systemctl enable blockchain-node-2 blockchain-rpc-2
sudo systemctl start blockchain-node-2 blockchain-rpc-2

# Check status
print_status "Checking service status..."
sudo systemctl status blockchain-node-2 --no-pager -l
sudo systemctl status blockchain-rpc-2 --no-pager -l

echo ""
print_status "✅ Second blockchain node deployed!"
echo ""
echo "Node 1 RPC: http://127.0.0.1:8080"
echo "Node 2 RPC: http://127.0.0.1:8081"
echo ""
echo "To check logs:"
echo "  Node 1: sudo journalctl -u blockchain-node -f"
echo "  Node 2: sudo journalctl -u blockchain-node-2 -f"
