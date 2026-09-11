#!/bin/bash

# Deploy blockchain node and explorer to incus container

set -e

# shellcheck source=scripts/deployment/deploy/deploy-env.sh
source "$(dirname "$0")/deploy-env.sh"
require_deploy_var AITBC_SSH_TARGET "Set it to the ssh alias or user@host of the deployment server."
require_deploy_var AITBC_PUBLIC_HOST "Set it to the public FQDN this deployment is reached on."


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
ssh "$AITBC_SSH_TARGET" "rm -rf /opt/blockchain-node 2>/dev/null || true"
scp -r apps/blockchain-node ${AITBC_SSH_TARGET}:/opt/

# Setup blockchain node in container
print_status "Setting up blockchain node..."
ssh "$AITBC_SSH_TARGET" << 'EOF'
cd /opt/blockchain-node

# Create configuration
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
ssh "$AITBC_SSH_TARGET" << 'EOF'
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

systemctl daemon-reload
systemctl enable blockchain-node blockchain-rpc
EOF

# Start blockchain node
print_status "Starting blockchain node..."
ssh "$AITBC_SSH_TARGET" "systemctl start blockchain-node blockchain-rpc"

# Wait for node to start
print_status "Waiting for blockchain node to start..."
sleep 5

# Check status
print_status "Checking blockchain node status..."
ssh "$AITBC_SSH_TARGET" "systemctl status blockchain-node blockchain-rpc --no-pager | grep -E 'Active:|Main PID:'"

# Setup port forwarding
# The forwarding target used to be hardcoded to one island's container address.
# It comes from AITBC_DNAT_TARGET now. The heredoc is quoted, so the value goes
# to the remote shell through its environment rather than being expanded here.
if [ -n "${AITBC_DNAT_TARGET:-}" ]; then
    print_status "Setting up port forwarding..."
    ssh "$AITBC_SSH_TARGET" "AITBC_DNAT_TARGET='${AITBC_DNAT_TARGET}' bash -s" << 'EOF'
set -e
iptables -t nat -F PREROUTING 2>/dev/null || true
iptables -t nat -F POSTROUTING 2>/dev/null || true

iptables -t nat -A PREROUTING -p tcp --dport 8202 -j DNAT \
    --to-destination "$AITBC_DNAT_TARGET:8202"
iptables -t nat -A POSTROUTING -p tcp -d "$AITBC_DNAT_TARGET" --dport 8202 -j MASQUERADE

mkdir -p /etc/iptables
iptables-save > /etc/iptables/rules.v4
EOF
else
    echo "NOTE: AITBC_DNAT_TARGET is not set -- nothing is published from the" >&2
    echo "      deployment host. Set it to the container's address on the bridge" >&2
    echo "      if this host is meant to forward to it." >&2
fi

print_success "✅ Blockchain node deployed!"
echo ""
if [ -n "${AITBC_DNAT_TARGET:-}" ]; then
    echo "Node RPC: http://${AITBC_DNAT_TARGET}:8202"
fi
echo "External RPC: http://${AITBC_PUBLIC_HOST}:8202"
echo ""
echo "Next: Deploying blockchain explorer..."
