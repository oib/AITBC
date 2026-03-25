#!/bin/bash

# Deploy blockchain node and explorer by building directly on ns3

echo "🚀 AITBC Remote Deployment (Build on Server)"
echo "=========================================="
echo "This will build the blockchain node directly on ns3"
echo "to utilize the gigabit connection instead of uploading."
echo ""

# Copy deployment scripts to server
echo "Copying deployment scripts to ns3..."
scp scripts/deploy/deploy-blockchain-remote.sh ns3-root:/opt/
scp scripts/deploy/deploy-explorer-remote.sh ns3-root:/opt/

# Create directories on server first
echo "Creating directories on ns3..."
ssh ns3-root "mkdir -p /opt/blockchain-node-src /opt/blockchain-node"

# Copy blockchain source code to server (excluding data files)
echo "Copying blockchain source code to ns3..."
rsync -av --exclude='data/' --exclude='*.db' --exclude='__pycache__' --exclude='.venv' apps/blockchain-node/ ns3-root:/opt/blockchain-node-src/

# Execute blockchain deployment
echo ""
echo "Deploying blockchain node..."
ssh ns3-root "cd /opt && cp -r /opt/blockchain-node-src/* /opt/blockchain-node/ && cd /opt/blockchain-node && chmod +x ../deploy-blockchain-remote.sh && ../deploy-blockchain-remote.sh"

# Wait for blockchain to start
echo ""
echo "Waiting 10 seconds for blockchain node to start..."
sleep 10

# Execute explorer deployment on ns3
echo ""
echo "Deploying blockchain explorer..."
ssh ns3-root "cd /opt && ./deploy-explorer-remote.sh"

# Check services
echo ""
echo "Checking service status..."
ssh ns3-root "systemctl status blockchain-node blockchain-rpc nginx --no-pager | grep -E 'Active:|Main PID:'"

echo ""
echo "✅ Deployment complete!"
echo ""
echo "Services:"
echo "  - Blockchain Node RPC: http://localhost:8082"
echo "  - Blockchain Explorer: http://localhost:3000"
echo ""
echo "External access:"
echo "  - Blockchain Node RPC: http://aitbc.keisanki.net:8082"
echo "  - Blockchain Explorer: http://aitbc.keisanki.net:3000"
echo ""
echo "The blockchain node will start syncing automatically."
echo "The explorer connects to the local node and displays real-time data."
