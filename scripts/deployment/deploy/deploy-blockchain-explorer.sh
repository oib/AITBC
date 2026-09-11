#!/bin/bash

# Deploy blockchain explorer to incus container

set -e

# shellcheck source=scripts/deployment/deploy/deploy-env.sh
source "$(dirname "$0")/deploy-env.sh"
require_deploy_var AITBC_SSH_TARGET "Set it to the ssh alias or user@host of the deployment server."
require_deploy_var AITBC_PUBLIC_HOST "Set it to the public FQDN this deployment is reached on."


echo "🔍 Deploying Blockchain Explorer"
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

# Copy explorer to container
print_status "Copying blockchain explorer to container..."
ssh "$AITBC_SSH_TARGET" "rm -rf /opt/blockchain-explorer 2>/dev/null || true"
scp -r apps/blockchain-explorer ${AITBC_SSH_TARGET}:/opt/

# Setup explorer in container
print_status "Setting up blockchain explorer..."
ssh "$AITBC_SSH_TARGET" << 'EOF'
cd /opt/blockchain-explorer

# Create Python environment
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
EOF

# Create systemd service for explorer
print_status "Creating systemd service for blockchain explorer..."
ssh "$AITBC_SSH_TARGET" << 'EOF'
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
ssh "$AITBC_SSH_TARGET" "systemctl start blockchain-explorer"

# Wait for explorer to start
print_status "Waiting for explorer to start..."
sleep 3

# Setup port forwarding for explorer
#
# The forwarding target used to be hardcoded to one island's container address.
# It comes from AITBC_DNAT_TARGET now. The heredoc below is quoted, so the value
# is handed to the remote shell through its environment rather than expanded
# here -- expanding it here would send a literal that the remote never resolves.
if [ -n "${AITBC_DNAT_TARGET:-}" ]; then
    print_status "Setting up port forwarding for explorer..."
    ssh "$AITBC_SSH_TARGET" "AITBC_DNAT_TARGET='${AITBC_DNAT_TARGET}' bash -s" << 'EOF'
set -e
iptables -t nat -A PREROUTING -p tcp --dport 3000 -j DNAT \
    --to-destination "$AITBC_DNAT_TARGET:3000"
iptables -t nat -A POSTROUTING -p tcp -d "$AITBC_DNAT_TARGET" --dport 3000 -j MASQUERADE

mkdir -p /etc/iptables
iptables-save > /etc/iptables/rules.v4
EOF
else
    echo "NOTE: AITBC_DNAT_TARGET is not set -- nothing is published from the" >&2
    echo "      deployment host. Set it to the container's address on the bridge" >&2
    echo "      if this host is meant to forward to it." >&2
fi

# Check status
print_status "Checking blockchain explorer status..."
ssh "$AITBC_SSH_TARGET" "systemctl status blockchain-explorer --no-pager | grep -E 'Active:|Main PID:'"

print_success "✅ Blockchain explorer deployed!"
echo ""
if [ -n "${AITBC_DNAT_TARGET:-}" ]; then
    echo "Explorer URL: http://${AITBC_DNAT_TARGET}:3000"
fi
echo "External URL: http://${AITBC_PUBLIC_HOST}:3000"
echo ""
echo "The explorer will automatically connect to the local blockchain node."
echo "You can view blocks, transactions, and chain statistics."
