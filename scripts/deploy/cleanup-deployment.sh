#!/bin/bash

# Clean up failed deployment and prepare for redeployment

echo "🧹 Cleaning up failed deployment..."
echo "=================================="

# Stop any running services
echo "Stopping services..."
ssh ns3-root "systemctl stop blockchain-node blockchain-rpc nginx 2>/dev/null || true"

# Remove old directories
echo "Removing old directories..."
ssh ns3-root "rm -rf /opt/blockchain-node /opt/blockchain-node-src /opt/blockchain-explorer 2>/dev/null || true"

# Remove systemd services
echo "Removing systemd services..."
ssh ns3-root "systemctl disable blockchain-node blockchain-rpc blockchain-explorer 2>/dev/null || true"
ssh ns3-root "rm -f /etc/systemd/system/blockchain-node.service /etc/systemd/system/blockchain-rpc.service /etc/systemd/system/blockchain-explorer.service 2>/dev/null || true"
ssh ns3-root "systemctl daemon-reload"

echo "✅ Cleanup complete!"
echo ""
echo "You can now run: ./scripts/deploy/deploy-all-remote.sh"
