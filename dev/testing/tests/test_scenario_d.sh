#!/bin/bash
# Scenario D: aitbc1 Container User Operations Test

echo "🚀 Scenario D: aitbc1 Container User Operations"
echo "==============================================="

echo "📋 Step 1: Connect to aitbc1 container"
echo "=========================================="
ssh aitbc1-cascade "echo '✅ Connected to aitbc1 container'"

echo ""
echo "📋 Step 2: Check container services status"
echo "=========================================="
ssh aitbc1-cascade "systemctl status coordinator-api | grep Active || echo 'Service not running'"
ssh aitbc1-cascade "ps aux | grep python | grep coordinator || echo 'No coordinator process found'"

echo ""
echo "📋 Step 3: Test container CLI functionality"
echo "=========================================="
ssh aitbc1-cascade "python3 --version"
ssh aitbc1-cascade "which aitbc || echo 'CLI not found in container PATH'"

echo ""
echo "📋 Step 4: Test blockchain operations in container"
echo "=========================================="
ssh aitbc1-cascade "curl -s http://localhost:8000/v1/health | jq . 2>/dev/null || echo 'Health endpoint not responding'"

echo ""
echo "📋 Step 5: Test marketplace access from container"
echo "=========================================="
ssh aitbc1-cascade "curl -s http://localhost:8000/v1/marketplace/offers | jq '.[] | select(.miner_id == \"miner1\")' 2>/dev/null || echo 'Marketplace offers not available'"

echo ""
echo "📋 Step 6: Test GPU service discovery from container"
echo "=========================================="
ssh aitbc1-cascade "curl -X POST http://localhost:8000/v1/gpu/inference \
  -H 'Content-Type: application/json' \
  -d '{\"miner_id\": \"miner1\", \"model\": \"gemma3:1b\", \"prompt\": \"Test from aitbc1 container\"}' | jq . 2>/dev/null || echo 'GPU inference not available'"

echo ""
echo "📋 Step 7: Test blockchain synchronization"
echo "=========================================="
ssh aitbc1-cascade "curl -s http://localhost:8000/v1/blockchain/sync/status | jq . 2>/dev/null || echo 'Sync status not available'"

echo ""
echo "📋 Step 8: Test cross-site connectivity"
echo "=========================================="
# Test if aitbc1 can reach aitbc via host proxy
ssh aitbc1-cascade "curl -s http://127.0.0.1:8000/v1/health | jq . 2>/dev/null || echo 'Cannot reach aitbc via proxy'"

echo ""
echo "📋 Step 9: Test analytics from container"
echo "=========================================="
ssh aitbc1-cascade "curl -s http://localhost:8000/v1/analytics/summary | jq .total_chains 2>/dev/null || echo 'Analytics not available'"

echo ""
echo "📋 Step 10: Verify container has no GPU access"
echo "=========================================="
ssh aitbc1-cascade "nvidia-smi 2>/dev/null || echo '✅ No GPU access (expected for container)'"
ssh aitbc1-cascade "lspci | grep -i nvidia || echo '✅ No GPU devices found (expected)'"

echo ""
echo "📋 Step 11: Test container resource usage"
echo "=========================================="
ssh aitbc1-cascade "free -h | head -2"
ssh aitbc1-cascade "df -h | grep -E '^/dev/' | head -3"

echo ""
echo "📋 Step 12: Test network connectivity from container"
echo "=========================================="
ssh aitbc1-cascade "ping -c 2 10.1.223.93 && echo '✅ Can reach aitbc container' || echo '❌ Cannot reach aitbc container'"
ssh aitbc1-cascade "ping -c 2 8.8.8.8 && echo '✅ Internet connectivity' || echo '❌ No internet connectivity'"

echo ""
echo "📋 Step 13: Test container vs localhost differences"
echo "=========================================="
echo "aitbc1 container services:"
ssh aitbc1-cascade "ps aux | grep -E '(python|node|nginx)' | grep -v grep || echo 'No services found'"

echo ""
echo "aitbc1 container network interfaces:"
ssh aitbc1-cascade "ip addr show | grep -E 'inet ' | head -3"

echo ""
echo "🎉 Scenario D Complete!"
echo "======================="
