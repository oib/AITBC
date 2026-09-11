#!/bin/bash

# Clean up failed deployment and prepare for redeployment


# shellcheck source=scripts/deployment/deploy/deploy-env.sh
source "$(dirname "$0")/deploy-env.sh"
require_deploy_var AITBC_SSH_TARGET "Set it to the ssh alias or user@host of the deployment server."

echo "🧹 Cleaning up failed deployment..."
echo "=================================="

# Stop any running services
echo "Stopping services..."
ssh "$AITBC_SSH_TARGET" "systemctl stop blockchain-node blockchain-rpc nginx 2>/dev/null || true"

# Remove old directories
echo "Removing old directories..."
ssh "$AITBC_SSH_TARGET" "rm -rf /opt/blockchain-node /opt/blockchain-node-src /opt/blockchain-explorer 2>/dev/null || true"

# Remove systemd services
echo "Removing systemd services..."
ssh "$AITBC_SSH_TARGET" "systemctl disable blockchain-node blockchain-rpc blockchain-explorer 2>/dev/null || true"
ssh "$AITBC_SSH_TARGET" "rm -f /etc/systemd/system/blockchain-node.service /etc/systemd/system/blockchain-rpc.service /etc/systemd/system/blockchain-explorer.service 2>/dev/null || true"
ssh "$AITBC_SSH_TARGET" "systemctl daemon-reload"

echo "✅ Cleanup complete!"
echo ""
echo "You can now run: ./scripts/deployment/deploy-all-remote.sh"
