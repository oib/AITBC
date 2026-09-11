#!/bin/bash

# Deploy blockchain node directly on the deployment server (build in place)

set -e

# shellcheck source=scripts/deployment/deploy/deploy-env.sh
source "$(dirname "$0")/deploy-env.sh"
# Runs on the deployment server itself, so AITBC_SSH_TARGET is optional here --
# it only decorates the closing summary.


echo "🚀 Deploying Blockchain Node on the deployment server (Build in Place)"
echo "====================================================="

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

# Check if we're on the right server
print_status "Checking server..."
if [ "$(hostname)" != "ns3" ] && [ "$(hostname)" != "aitbc" ]; then
    print_warning "This script should be run on the deployment server"
    echo "Please run: ssh $AITBC_SSH_TARGET"
    echo "Then: cd /opt && ./deploy-blockchain-remote.sh"
    exit 1
fi

# Install dependencies if needed
print_status "Installing dependencies..."
apt-get update
apt-get install -y python3 python3-venv python3-pip git curl

# Create directory
print_status "Creating blockchain node directory..."
mkdir -p /opt/blockchain-node
cd /opt/blockchain-node

# Check if source code exists
if [ ! -d "src" ]; then
    print_status "Source code not found in /opt/blockchain-node, copying from /opt/blockchain-node-src..."
    if [ -d "/opt/blockchain-node-src" ]; then
        cp -r /opt/blockchain-node-src/* .
    else
        print_warning "Source code not found. Please ensure it was copied properly."
        exit 1
    fi
fi

# Setup Python environment
print_status "Setting up Python environment..."
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -e .

# Create configuration with auto-sync
print_status "Creating configuration..."
cat > .env << EOL
CHAIN_ID=ait-devnet
DB_PATH=./data/chain.db
RPC_BIND_HOST=0.0.0.0
RPC_BIND_PORT=8202
P2P_BIND_HOST=0.0.0.0
P2P_BIND_PORT=7070
PROPOSER_KEY=proposer_key_$(date +%s)
MINT_PER_UNIT=1000
COORDINATOR_RATIO=0.05
GOSSIP_BACKEND=memory
EOL

# Create fresh data directory
print_status "Creating fresh data directory..."
rm -rf data
mkdir -p data/devnet

# Generate fresh genesis
print_status "Generating fresh genesis block..."
export PYTHONPATH="${PWD}/src:${PWD}/scripts:${PYTHONPATH:-}"
python scripts/make_genesis.py --output data/devnet/genesis.json --force

# Create systemd service for blockchain node
print_status "Creating systemd services..."
cat > /etc/systemd/system/blockchain-node.service << EOL
[Unit]
Description=AITBC Blockchain Node
After=network.target

[Service]
Type=exec
User=root
WorkingDirectory=/opt/blockchain-node
Environment=PATH=/opt/blockchain-node/.venv/bin:/usr/local/bin:/usr/bin:/bin
Environment=PYTHONPATH=/opt/blockchain-node/src:/opt/blockchain-node/scripts
ExecStart=/opt/blockchain-node/.venv/bin/python3 -m aitbc_chain.main
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOL

cat > /etc/systemd/system/blockchain-rpc.service << EOL
[Unit]
Description=AITBC Blockchain RPC API
After=blockchain-node.service

[Service]
Type=exec
User=root
WorkingDirectory=/opt/blockchain-node
Environment=PATH=/opt/blockchain-node/.venv/bin:/usr/local/bin:/usr/bin:/bin
Environment=PYTHONPATH=/opt/blockchain-node/src:/opt/blockchain-node/scripts
ExecStart=/opt/blockchain-node/.venv/bin/python3 -m uvicorn aitbc_chain.app:app --host 0.0.0.0 --port 8202
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOL

# Enable and start services
print_status "Starting blockchain node..."
systemctl daemon-reload
systemctl enable blockchain-node blockchain-rpc
systemctl start blockchain-node blockchain-rpc

# Wait for services to start
print_status "Waiting for services to start..."
sleep 5

# Check status
print_status "Checking service status..."
systemctl status blockchain-node blockchain-rpc --no-pager | head -15

# Setup port forwarding if in container
if [ "$(hostname)" = "aitbc" ]; then
    print_status "Setting up port forwarding..."
    iptables -t nat -A PREROUTING -p tcp --dport 8202 -j DNAT --to-destination 192.168.100.10:8202
    iptables -t nat -A POSTROUTING -p tcp -d 192.168.100.10 --dport 8202 -j MASQUERADE
    iptables-save > /etc/iptables/rules.v4
fi

print_success "✅ Blockchain node deployed!"
echo ""
# Addresses are deployment-specific and deliberately not hardcoded here.
echo "Node RPC: http://${NODE_RPC_HOST:-127.0.0.1}:${RPC_BIND_PORT}"
if [ -n "${NODE_RPC_EXTERNAL:-}" ]; then
    echo "External: ${NODE_RPC_EXTERNAL}"
fi
echo ""
echo "The node will automatically sync on startup."
