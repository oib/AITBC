#!/bin/bash

# Deploy blockchain node by building directly on redacted-host server

echo "🚀 Remote Blockchain Deployment (Build on Server)"
echo "=============================================="

# Copy deployment script to server
echo "Copying deployment script to redacted-host..."
scp scripts/deploy/deploy-blockchain-remote.sh redacted-host-root:/opt/

# Execute deployment on server
echo "Executing deployment on redacted-host (utilizing gigabit connection)..."
ssh redacted-host-root "cd /opt && chmod +x deploy-blockchain-remote.sh && ./deploy-blockchain-remote.sh"

echo ""
echo "Deployment complete!"
echo "The blockchain node was built directly on redacted-host using its fast connection."
