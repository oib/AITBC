#!/bin/bash
# Scenario C: aitbc Container User Operations Test

echo "🚀 Scenario C: aitbc Container User Operations"
echo "=============================================="

echo "📋 Step 1: Connect to aitbc container"
echo "=========================================="
ssh aitbc-cascade "echo '✅ Connected to aitbc container'"

echo ""
echo "📋 Step 2: Check container services status"
echo "=========================================="
ssh aitbc-cascade "systemctl status coordinator-api | grep Active"
ssh aitbc-cascade "systemctl status aitbc-blockchain-node-1 | grep Active"

echo ""
echo "📋 Step 3: Test container CLI functionality"
echo "=========================================="
ssh aitbc-cascade "python3 --version"
ssh aitbc-cascade "which aitbc || echo 'CLI not found in container PATH'"

echo ""
echo "📋 Step 4: Test blockchain operations in container"
echo "=========================================="
ssh aitbc-cascade "curl -s http://localhost:8000/v1/health | jq ."

echo ""
echo "📋 Step 5: Test marketplace access from container"
echo "=========================================="
ssh aitbc-cascade "curl -s http://localhost:8000/v1/marketplace/offers | jq '.[] | select(.miner_id == \"miner1\")'"

echo ""
echo "📋 Step 6: Test GPU service discovery from container"
echo "=========================================="
ssh aitbc-cascade "curl -X POST http://localhost:8000/v1/gpu/inference \
  -H 'Content-Type: application/json' \
  -d '{\"miner_id\": \"miner1\", \"model\": \"gemma3:1b\", \"prompt\": \"Test from container\"}' | jq ."

echo ""
echo "📋 Step 7: Test blockchain node RPC from container"
echo "=========================================="
ssh aitbc-cascade "curl -s http://localhost:9080/rpc/head | jq .height"

echo ""
echo "📋 Step 8: Test wallet operations in container"
echo "=========================================="
ssh aitbc-cascade "curl -s http://localhost:8002/wallet/status | jq ."

echo ""
echo "📋 Step 9: Test analytics from container"
echo "=========================================="
ssh aitbc-cascade "curl -s http://localhost:8000/v1/analytics/summary | jq .total_chains"

echo ""
echo "📋 Step 10: Verify container has no GPU access"
echo "=========================================="
ssh aitbc-cascade "nvidia-smi 2>/dev/null || echo '✅ No GPU access (expected for container)'"
ssh aitbc-cascade "lspci | grep -i nvidia || echo '✅ No GPU devices found (expected)'"

echo ""
echo "📋 Step 11: Test container resource usage"
echo "=========================================="
ssh aitbc-cascade "free -h | head -2"
ssh aitbc-cascade "df -h | grep -E '^/dev/' | head -3"

echo ""
echo "🎉 Scenario C Complete!"
echo "======================="
