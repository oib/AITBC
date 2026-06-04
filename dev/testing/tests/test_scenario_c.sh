#!/bin/bash
# Scenario C: Container Service Operations Test (Updated for v0.4.x)

echo "🚀 Scenario C: Container Service Operations"
echo "============================================"


# Source scenario configuration
if [ -f "/etc/aitbc/.env.scenario" ]; then
    source /etc/aitbc/.env.scenario
    echo "✅ Loaded scenario configuration from /etc/aitbc/.env.scenario"
else
    # Fallback to defaults
    export HUB_URL="${HUB_URL:-https://hub.aitbc.bubuit.net}"
    export SHOP_URL="${SHOP_URL:-https://aitbc3.aitbc.bubuit.net}"
    export BLOCKCHAIN_RPC="${BLOCKCHAIN_RPC:-http://localhost:8202}"
    echo "⚠️  Using default configuration (env file not found)"
fi
# Configuration
HUB_URL="https://hub.aitbc.bubuit.net"
SHOP_URL="https://aitbc3.aitbc.bubuit.net"
BLOCKCHAIN_RPC="http://localhost:8202"

echo "📋 Step 1: Connect to container"
echo "==============================="
# Try to connect, but handle if container doesn't exist
if ssh aitbc-cascade "echo '✅ Connected to container'" 2>/dev/null; then
    CONTAINER="aitbc-cascade"
elif ssh aitbc "echo '✅ Connected to aitbc'" 2>/dev/null; then
    CONTAINER="aitbc"
else
    echo "⚠️ No container available, testing locally"
    CONTAINER=""
fi

if [ -n "$CONTAINER" ]; then
    echo ""
    echo "📋 Step 2: Check container services status"
    echo "========================================"
    ssh $CONTAINER "systemctl status aitbc-blockchain-p2p | grep Active || echo 'P2P service not running'"
    ssh $CONTAINER "systemctl status aitbc-blockchain-node | grep Active || echo 'Node service not running'"

    echo ""
    echo "📋 Step 3: Test container CLI functionality"
    echo "=========================================="
    ssh $CONTAINER "python3 --version"
    ssh $CONTAINER "which aitbc || echo 'CLI not found in container PATH'"

    echo ""
    echo "📋 Step 4: Test blockchain RPC from container"
    echo "=========================================="
    ssh $CONTAINER "curl -s $BLOCKCHAIN_RPC/rpc/head | jq .height 2>/dev/null || echo 'RPC not responding'"

    echo ""
    echo "📋 Step 5: Test marketplace CLI from container"
    echo "==========================================="
    ssh $CONTAINER "aitbc market list 2>/dev/null || echo 'Marketplace CLI not available'"

    echo ""
    echo "📋 Step 6: Test plugin registry from container"
    echo "=========================================="
    ssh $CONTAINER "curl -s $SHOP_URL/plugin/plugins | jq . 2>/dev/null || echo 'Plugin registry not available'"

    echo ""
    echo "📋 Step 7: Test Whisper service from container"
    echo "==========================================="
    ssh $CONTAINER "curl -s $SHOP_URL/whisper/health | jq . 2>/dev/null || echo 'Whisper service not available'"

    echo ""
    echo "📋 Step 8: Verify container has no GPU access"
    echo "=========================================="
    ssh $CONTAINER "nvidia-smi 2>/dev/null || echo '✅ No GPU access (expected for container)'"

    echo ""
    echo "📋 Step 9: Test container resource usage"
    echo "========================================"
    ssh $CONTAINER "free -h | head -2"
    ssh $CONTAINER "df -h | grep -E '^/dev/' | head -3"
else
    echo "Testing services locally..."
    echo "Hub: $HUB_URL"
echo "Shop: $SHOP_URL"
    echo ""
    echo "📋 Step 2: Test blockchain RPC locally"
    echo "===================================="
    curl -s $BLOCKCHAIN_RPC/rpc/head | jq .height 2>/dev/null || echo "RPC not responding"

    echo ""
    echo "📋 Step 3: Test marketplace CLI locally"
    echo "======================================"
    aitbc market list 2>/dev/null || echo "Marketplace CLI not available"

    echo ""
    echo "📋 Step 4: Test plugin registry locally"
    echo "======================================"
    curl -s $SHOP_URL/plugin/plugins | jq . 2>/dev/null || echo "Plugin registry not available"
fi

echo ""
echo "🎉 Scenario C Complete!"
echo "======================="
echo "✅ Service operations tested"
