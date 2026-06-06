#!/bin/bash

# Test if blockchain node and explorer are running

echo "🔍 Testing Blockchain Deployment"
echo "==============================="

# Test blockchain RPC
echo "Testing blockchain RPC..."
if curl -s http://aitbc.keisanki.net:8082/rpc/head > /dev/null; then
    echo "✅ Blockchain RPC is accessible"
    curl -s http://aitbc.keisanki.net:8082/rpc/head | jq '.height'
else
    echo "❌ Blockchain RPC is not accessible"
fi

# Test explorer
echo ""
echo "Testing blockchain explorer..."
if curl -s http://aitbc.keisanki.net:3000 > /dev/null; then
    echo "✅ Explorer is accessible"
else
    echo "❌ Explorer is not accessible"
fi

# Check services on server
echo ""
echo "Checking service status on ns3..."
ssh ns3-root "systemctl is-active blockchain-node blockchain-rpc nginx" | while read service status; do
    if [ "$status" = "active" ]; then
        echo "✅ $service is running"
    else
        echo "❌ $service is not running"
    fi
done

# Check logs if needed
echo ""
echo "Recent blockchain logs:"
ssh ns3-root "journalctl -u blockchain-node -n 5 --no-pager"
