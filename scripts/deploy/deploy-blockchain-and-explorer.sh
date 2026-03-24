#!/bin/bash

# Deploy blockchain node and explorer to incus container

set -e

echo "🚀 Deploying Blockchain Node and Explorer"
echo "========================================"

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

# Copy blockchain node to container
print_status "Copying blockchain node to container..."
ssh ns3-root "rm -rf /opt/blockchain-node 2>/dev/null || true"
scp -r apps/blockchain-node ns3-root:/opt/

# Setup blockchain node in container
print_status "Setting up blockchain node..."
ssh ns3-root << 'EOF'
cd /opt/blockchain-node

# Create configuration
cat > .env << EOL
CHAIN_ID=ait-devnet
DB_PATH=./data/chain.db
RPC_BIND_HOST=0.0.0.0
RPC_BIND_PORT=8082
P2P_BIND_HOST=0.0.0.0
P2P_BIND_PORT=7070
PROPOSER_KEY=proposer_key_$(date +%s)
MINT_PER_UNIT=1000
COORDINATOR_RATIO=0.05
GOSSIP_BACKEND=memory
EOL

# Create data directory
mkdir -p data/devnet

# Setup Python environment
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -e .

# Generate genesis
export PYTHONPATH="${PWD}/src:${PWD}/scripts:${PYTHONPATH:-}"
python scripts/make_genesis.py --output data/devnet/genesis.json --force
EOF

# Create systemd service for blockchain node
print_status "Creating systemd service for blockchain node..."
ssh ns3-root << 'EOF'
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
ExecStart=/opt/blockchain-node/.venv/bin/python3 -m uvicorn aitbc_chain.app:app --host 0.0.0.0 --port 8082
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOL

systemctl daemon-reload
systemctl enable blockchain-node blockchain-rpc
EOF

# Start blockchain node
print_status "Starting blockchain node..."
ssh ns3-root "systemctl start blockchain-node blockchain-rpc"

# Wait for node to start
print_status "Waiting for blockchain node to start..."
sleep 5

# Check status
print_status "Checking blockchain node status..."
ssh ns3-root "systemctl status blockchain-node blockchain-rpc --no-pager | grep -E 'Active:|Main PID:'"

# Copy explorer to container
print_status "Copying blockchain explorer to container..."
ssh ns3-root "rm -rf /opt/blockchain-explorer 2>/dev/null || true"
scp -r apps/blockchain-explorer ns3-root:/opt/

# Setup explorer in container
print_status "Setting up blockchain explorer..."
ssh ns3-root << 'EOF'
cd /opt/blockchain-explorer

# Create Python environment
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
EOF

# Create systemd service for explorer
print_status "Creating systemd service for blockchain explorer..."
ssh ns3-root << 'EOF'
cat > /etc/systemd/system/blockchain-explorer.service << EOL
[Unit]
Description=AITBC Blockchain Explorer
After=blockchain-rpc.service

[Service]
Type=exec
User=root
WorkingDirectory=/opt/blockchain-explorer
Environment=PATH=/opt/blockchain-explorer/.venv/bin:/usr/local/bin:/usr/bin:/bin
ExecStart=/opt/blockchain-explorer/.venv/bin/python3 main.py
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOL

systemctl daemon-reload
systemctl enable blockchain-explorer
EOF

# Start explorer
print_status "Starting blockchain explorer..."
ssh ns3-root "systemctl start blockchain-explorer"

# Wait for explorer to start
print_status "Waiting for explorer to start..."
sleep 3

# Setup port forwarding
print_status "Setting up port forwarding..."
ssh ns3-root << 'EOF'
# Clear existing NAT rules
iptables -t nat -F PREROUTING 2>/dev/null || true
iptables -t nat -F POSTROUTING 2>/dev/null || true

# Add port forwarding for blockchain RPC
iptables -t nat -A PREROUTING -p tcp --dport 8082 -j DNAT --to-destination 192.168.100.10:8082
iptables -t nat -A POSTROUTING -p tcp -d 192.168.100.10 --dport 8082 -j MASQUERADE

# Add port forwarding for explorer
iptables -t nat -A PREROUTING -p tcp --dport 3000 -j DNAT --to-destination 192.168.100.10:3000
iptables -t nat -A POSTROUTING -p tcp -d 192.168.100.10 --dport 3000 -j MASQUERADE

# Save rules
mkdir -p /etc/iptables
iptables-save > /etc/iptables/rules.v4

# Install iptables-persistent for persistence
apt-get update
apt-get install -y iptables-persistent
EOF

# Check all services
print_status "Checking all services..."
ssh ns3-root "systemctl status blockchain-node blockchain-rpc blockchain-explorer --no-pager | grep -E 'Active:|Main PID:'"

print_success "✅ Deployment complete!"
echo ""
echo "Services deployed:"
echo "  - Blockchain Node RPC: http://192.168.100.10:8082"
echo "  - Blockchain Explorer: http://192.168.100.10:3000"
echo ""
echo "External access:"
echo "  - Blockchain Node RPC: http://aitbc.keisanki.net:8082"
echo "  - Blockchain Explorer: http://aitbc.keisanki.net:3000"
echo ""
echo "The explorer is connected to the local blockchain node and will display"
echo "real-time blockchain data including blocks and transactions."
