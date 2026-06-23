#!/bin/bash
# Configuration

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
HUB_URL="https://hub.aitbc.bubuit.net"
BLOCKCHAIN_RPC="http://localhost:8202"
# Scenario D: Multi-Node Connectivity Test (Updated for v0.4.x)

echo "� Scenario D: Multi-Node Connectivity Test"
echo "=========================================="

echo "📋 Step 1: Test local blockchain RPC"
echo "===================================="
curl -s $BLOCKCHAIN_RPC/rpc/head | jq .height 2>/dev/null || echo "Local RPC not responding"

echo ""
echo "📋 Step 2: Test plugin registry"
echo "=============================="
curl -s $HUB_URL/plugin/plugins | jq . 2>/dev/null || echo "Plugin registry not available"

echo ""
echo "📋 Step 3: Test Whisper service"

echo ""
echo "📋 Step 4: Test PeerTube transcoder at hub"
echo "=========================================="
curl -s $HUB_URL/peertube/health | jq . 2>/dev/null || echo "PeerTube transcoder not available"
echo "==============================="
curl -s $HUB_URL/whisper/health | jq . 2>/dev/null || echo "Whisper service not available"

echo ""
echo "📋 Step 4: Test marketplace CLI"
echo "=============================="
aitbc market list 2>/dev/null || echo "Marketplace CLI not available"

echo ""
echo "📋 Step 5: Test P2P service"
echo "==========================="
# Check if P2P service is running
systemctl status aitbc-blockchain-p2p | grep Active || echo "P2P service not running"

echo ""
echo "📋 Step 6: Test Redis connectivity"
echo "=================================="
redis-cli ping 2>/dev/null || echo "Redis not available"

echo ""
echo "📋 Step 7: Test agent coordinator (port 8107)"
echo "=============================================="
curl -s http://localhost:8107/health | jq . 2>/dev/null || echo "Agent coordinator not available"

echo ""
echo "📋 Step 8: Test wallet service (port 8108)"
echo "========================================="
curl -s http://localhost:8108/v1/wallet/balance | jq . 2>/dev/null || echo "Wallet service not available"

echo ""
echo "📋 Step 9: Test trading service (port 8104)"
echo "=========================================="
curl -s http://localhost:8104/health | jq . 2>/dev/null || echo "Trading service not available"

echo ""
echo "📋 Step 10: Test governance service (port 8105)"
echo "=============================================="
curl -s http://localhost:8105/health | jq . 2>/dev/null || echo "Governance service not available"

echo ""
echo "📋 Step 11: Test exchange service (port 8106)"
echo "============================================"
curl -s http://localhost:8106/health | jq . 2>/dev/null || echo "Exchange service not available"

echo ""
echo "📋 Step 12: Test Agent Coordinator service (port 8107)"
echo "=========================================="
curl -s http://localhost:8107/health | jq . 2>/dev/null || echo "Agent Coordinator service not available"

echo ""
echo "📋 Step 13: Network connectivity check"
echo "===================================="
ping -c 2 8.8.8.8 > /dev/null 2>&1 && echo "✅ Internet connectivity" || echo "❌ No internet connectivity"

echo ""
echo "📋 Step 14: System resource check"
echo "================================"
free -h | head -2
df -h | grep -E '^/dev/' | head -3

echo ""
echo "🎉 Scenario D Complete!"
echo "======================="
echo "✅ Multi-node connectivity tested"
