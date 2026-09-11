#!/bin/bash

# Test if blockchain node and explorer are running


# shellcheck source=scripts/deployment/deploy/deploy-env.sh
source "$(dirname "$0")/deploy-env.sh"
require_deploy_var AITBC_SSH_TARGET "Set it to the ssh alias or user@host of the deployment server."
require_deploy_var AITBC_PUBLIC_HOST "Set it to the public FQDN this deployment is reached on."

echo "🔍 Testing Blockchain Deployment"
echo "==============================="

# Test blockchain RPC
echo "Testing blockchain RPC..."
if curl -s http://${AITBC_PUBLIC_HOST}:8202/rpc/head > /dev/null; then
    echo "✅ Blockchain RPC is accessible"
    curl -s http://${AITBC_PUBLIC_HOST}:8202/rpc/head | jq '.height'
else
    echo "❌ Blockchain RPC is not accessible"
fi

# Test explorer
echo ""
echo "Testing blockchain explorer..."
if curl -s http://${AITBC_PUBLIC_HOST}:3000 > /dev/null; then
    echo "✅ Explorer is accessible"
else
    echo "❌ Explorer is not accessible"
fi

# Check services on server
echo ""
echo "Checking service status on the deployment server..."
ssh "$AITBC_SSH_TARGET" "systemctl is-active blockchain-node blockchain-rpc nginx" | while read service status; do
    if [ "$status" = "active" ]; then
        echo "✅ $service is running"
    else
        echo "❌ $service is not running"
    fi
done

# Check logs if needed
echo ""
echo "Recent blockchain logs:"
ssh "$AITBC_SSH_TARGET" "journalctl -u blockchain-node -n 5 --no-pager"
