#!/bin/bash

# Deploy blockchain node and explorer by building directly on the deployment server


# shellcheck source=scripts/deployment/deploy/deploy-env.sh
source "$(dirname "$0")/deploy-env.sh"
require_deploy_var AITBC_SSH_TARGET "Set it to the ssh alias or user@host of the deployment server."
require_deploy_var AITBC_PUBLIC_HOST "Set it to the public FQDN this deployment is reached on."

echo "🚀 AITBC Remote Deployment (Build on Server)"
echo "=========================================="
echo "This will build the blockchain node directly on the deployment server"
echo "to utilize the gigabit connection instead of uploading."
echo ""

# Copy deployment scripts to server
echo "Copying deployment scripts to the deployment server..."
scp scripts/deployment/deploy-blockchain-remote.sh ${AITBC_SSH_TARGET}:/opt/
scp scripts/deployment/deploy-explorer-remote.sh ${AITBC_SSH_TARGET}:/opt/

# Create directories on server first
echo "Creating directories on the deployment server..."
ssh "$AITBC_SSH_TARGET" "mkdir -p /opt/blockchain-node-src /opt/blockchain-node"

# Copy blockchain source code to server (excluding data files)
echo "Copying blockchain source code to the deployment server..."
rsync -av --exclude='data/' --exclude='*.db' --exclude='__pycache__' --exclude='.venv' apps/blockchain-node/ ${AITBC_SSH_TARGET}:/opt/blockchain-node-src/

# Execute blockchain deployment
echo ""
echo "Deploying blockchain node..."
ssh "$AITBC_SSH_TARGET" "cd /opt && cp -r /opt/blockchain-node-src/* /opt/blockchain-node/ && cd /opt/blockchain-node && chmod +x ../deploy-blockchain-remote.sh && ../deploy-blockchain-remote.sh"

# Wait for blockchain to start
echo ""
echo "Waiting 10 seconds for blockchain node to start..."
sleep 10

# Execute explorer deployment on the deployment server
echo ""
echo "Deploying blockchain explorer..."
ssh "$AITBC_SSH_TARGET" "cd /opt && ./deploy-explorer-remote.sh"

# Check services
echo ""
echo "Checking service status..."
ssh "$AITBC_SSH_TARGET" "systemctl status blockchain-node blockchain-rpc nginx --no-pager | grep -E 'Active:|Main PID:'"

echo ""
echo "✅ Deployment complete!"
echo ""
echo "Services:"
echo "  - Blockchain Node RPC: http://localhost:8202"
echo "  - Blockchain Explorer: http://localhost:3000"
echo ""
echo "External access:"
echo "  - Blockchain Node RPC: http://${AITBC_PUBLIC_HOST}:8202"
echo "  - Blockchain Explorer: http://${AITBC_PUBLIC_HOST}:3000"
echo ""
echo "The blockchain node will start syncing automatically."
echo "The explorer connects to the local node and displays real-time data."
