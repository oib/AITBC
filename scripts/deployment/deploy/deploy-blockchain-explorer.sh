#!/bin/bash

# Deploy blockchain explorer to incus container

set -e

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

# Setup port forwarding for explorer
print_status "Setting up port forwarding for explorer..."
ssh ns3-root << 'EOF'
# Add port forwarding for explorer
iptables -t nat -A PREROUTING -p tcp --dport 3000 -j DNAT --to-destination 192.168.100.10:3000
iptables -t nat -A POSTROUTING -p tcp -d 192.168.100.10 --dport 3000 -j MASQUERADE

# Save rules
iptables-save > /etc/iptables/rules.v4
EOF

# Check status
print_status "Checking blockchain explorer status..."
ssh ns3-root "systemctl status blockchain-explorer --no-pager | grep -E 'Active:|Main PID:'"

print_success "✅ Blockchain explorer deployed!"
echo ""
echo "Explorer URL: http://192.168.100.10:3000"
echo "External URL: http://aitbc.keisanki.net:3000"
echo ""
echo "The explorer will automatically connect to the local blockchain node."
echo "You can view blocks, transactions, and chain statistics."
