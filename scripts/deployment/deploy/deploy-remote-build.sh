#!/bin/bash

# Deploy blockchain node by building directly on the deployment server


# shellcheck source=scripts/deployment/deploy/deploy-env.sh
source "$(dirname "$0")/deploy-env.sh"
require_deploy_var AITBC_SSH_TARGET "Set it to the ssh alias or user@host of the deployment server."

echo "🚀 Remote Blockchain Deployment (Build on Server)"
echo "=============================================="

# Copy deployment script to server
echo "Copying deployment script to the deployment server..."
scp scripts/deployment/deploy-blockchain-remote.sh ${AITBC_SSH_TARGET}:/opt/

# Execute deployment on server
echo "Executing deployment on the deployment server (utilizing gigabit connection)..."
ssh "$AITBC_SSH_TARGET" "cd /opt && chmod +x deploy-blockchain-remote.sh && ./deploy-blockchain-remote.sh"

echo ""
echo "Deployment complete!"
echo "The blockchain node was built directly on the deployment server using its fast connection."
