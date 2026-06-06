#!/bin/bash

# Deploy blockchain node by building directly on ns3 server

echo "🚀 Remote Blockchain Deployment (Build on Server)"
echo "=============================================="

# Copy deployment script to server
echo "Copying deployment script to ns3..."
scp scripts/deployment/deploy-blockchain-remote.sh ns3-root:/opt/

# Execute deployment on server
echo "Executing deployment on ns3 (utilizing gigabit connection)..."
ssh ns3-root "cd /opt && chmod +x deploy-blockchain-remote.sh && ./deploy-blockchain-remote.sh"

echo ""
echo "Deployment complete!"
echo "The blockchain node was built directly on ns3 using its fast connection."
