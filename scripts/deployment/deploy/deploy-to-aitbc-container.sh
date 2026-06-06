#!/bin/bash

# Deploy blockchain node inside incus container aitbc

set -e

echo "🚀 AITBC Deployment in Incus Container"
echo "======================================"
echo "This will deploy inside the aitbc container"
echo ""

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

# Check if we're on ns3 host
if [ "$(hostname)" != "ns3" ]; then
    print_warning "This script must be run on ns3 host"
    echo "Run: ssh ns3-root"
    exit 1
fi

# Check if container exists
if ! incus list | grep -q "aitbc.*RUNNING"; then
    print_warning "Container aitbc is not running"
    exit 1
fi

# Copy source to container
print_status "Copying source code to container..."
incus exec aitbc -- rm -rf /opt/blockchain-node-src 2>/dev/null || true
incus exec aitbc -- mkdir -p /opt/blockchain-node-src
# Use the source already on the server
incus file push -r /opt/blockchain-node-src/. aitbc/opt/blockchain-node-src/
# Fix the nested directory issue - move everything up one level
incus exec aitbc -- sh -c 'if [ -d /opt/blockchain-node-src/blockchain-node-src ]; then mv /opt/blockchain-node-src/blockchain-node-src/* /opt/blockchain-node-src/ && rmdir /opt/blockchain-node-src/blockchain-node-src; fi'

# Copy deployment script to container
print_status "Copying deployment script to container..."
incus file push /opt/deploy-in-container.sh aitbc/opt/

# Execute deployment inside container
print_status "Deploying inside container..."
incus exec aitbc -- bash /opt/deploy-in-container.sh

# Setup port forwarding on host
print_status "Setting up port forwarding on host..."
iptables -t nat -F PREROUTING 2>/dev/null || true
iptables -t nat -F POSTROUTING 2>/dev/null || true

# Forward blockchain RPC
iptables -t nat -A PREROUTING -p tcp --dport 8082 -j DNAT --to-destination 192.168.100.10:8082
iptables -t nat -A POSTROUTING -p tcp -d 192.168.100.10 --dport 8082 -j MASQUERADE

# Forward explorer
iptables -t nat -A PREROUTING -p tcp --dport 3000 -j DNAT --to-destination 192.168.100.10:3000
iptables -t nat -A POSTROUTING -p tcp -d 192.168.100.10 --dport 3000 -j MASQUERADE

# Save rules
mkdir -p /etc/iptables
iptables-save > /etc/iptables/rules.v4

# Check services
print_status "Checking services in container..."
incus exec aitbc -- systemctl status blockchain-node blockchain-rpc nginx --no-pager | grep -E 'Active:|Main PID:'

print_success "✅ Deployment complete!"
echo ""
echo "Services in container aitbc:"
echo "  - Blockchain Node RPC: http://192.168.100.10:8082"
echo "  - Blockchain Explorer: http://192.168.100.10:3000"
echo ""
echo "External access via ns3:"
echo "  - Blockchain Node RPC: http://aitbc.keisanki.net:8082"
echo "  - Blockchain Explorer: http://aitbc.keisanki.net:3000"
