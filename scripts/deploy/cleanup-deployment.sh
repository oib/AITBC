#!/bin/bash

# Clean up failed deployment and prepare for redeployment

echo "🧹 Cleaning up failed deployment..."
echo "=================================="

# Stop any running services
echo "Stopping services..."
ssh redacted-host-root "systemctl stop blockchain-node blockchain-rpc nginx 2>/dev/null || true"

# Remove old directories
echo "Removing old directories..."
ssh redacted-host-root "rm -rf /opt/blockchain-node /opt/blockchain-node-src /opt/blockchain-explorer 2>/dev/null || true"

# Remove systemd services
echo "Removing systemd services..."
ssh redacted-host-root "systemctl disable blockchain-node blockchain-rpc blockchain-explorer 2>/dev/null || true"
ssh redacted-host-root "rm -f /etc/systemd/system/blockchain-node.service /etc/systemd/system/blockchain-rpc.service /etc/systemd/system/blockchain-explorer.service 2>/dev/null || true"
ssh redacted-host-root "systemctl daemon-reload"

echo "✅ Cleanup complete!"
echo ""
echo "You can now run: ./scripts/deploy/deploy-all-remote.sh"
