#!/bin/bash
# Scenario B: Localhost GPU Client → aitbc1 Marketplace Test

echo "🚀 Scenario B: Localhost GPU Client → aitbc1 Marketplace"
echo "======================================================"

# Set up client1 environment
export CLIENT_ID="client1"
export CLIENT_WALLET="0xabcdef1234567890abcdef1234567890abcdef12"
export CLIENT_REGION="localhost"

echo "📋 Step 1: Check client1 wallet configuration"
echo "=========================================="
if [ -f "/home/oib/windsurf/aitbc/home/client1/client_wallet.json" ]; then
    echo "✅ client1 wallet found:"
    cat /home/oib/windsurf/aitbc/home/client1/client_wallet.json
else
    echo "❌ client1 wallet not found"
fi

echo ""
echo "📋 Step 2: Verify aitbc1 marketplace connectivity"
echo "=========================================="
curl -s http://127.0.0.1:18001/v1/health | jq .

echo ""
echo "📋 Step 3: Wait for marketplace synchronization"
echo "=========================================="
echo "⏳ Waiting 30 seconds for miner1 registration to sync from aitbc to aitbc1..."
sleep 30

echo ""
echo "📋 Step 4: Discover available services on aitbc1"
echo "=========================================="
curl -s http://127.0.0.1:18001/v1/marketplace/offers | jq '.[] | select(.miner_id == "miner1")'

echo ""
echo "📋 Step 5: Client1 discovers GPU services"
echo "=========================================="
aitbc marketplace gpu discover \
  --client-id $CLIENT_ID \
  --region $CLIENT_REGION \
  --marketplace-url "http://127.0.0.1:18001"

echo ""
echo "📋 Step 6: Client1 requests service from miner1 via aitbc1"
echo "=========================================="
aitbc marketplace gpu request \
  --client-id $CLIENT_ID \
  --miner-id "miner1" \
  --model "gemma3:1b" \
  --prompt "What is artificial intelligence?" \
  --marketplace-url "http://127.0.0.1:18001"

echo ""
echo "📋 Step 7: Verify transaction on aitbc1"
echo "=========================================="
sleep 5
aitbc marketplace transactions $CLIENT_ID \
  --marketplace-url "http://127.0.0.1:18001"

echo ""
echo "📋 Step 8: Test cross-container service routing"
echo "=========================================="
# This should route from client1 (localhost) → aitbc1 → aitbc → localhost miner1
curl -X POST http://127.0.0.1:18001/v1/gpu/inference \
  -H "Content-Type: application/json" \
  -d '{"miner_id": "miner1", "model": "gemma3:1b", "prompt": "Cross-container routing test"}' | jq .

echo ""
echo "📋 Step 9: Verify marketplace stats on both sites"
echo "=========================================="
echo "aitbc marketplace stats:"
curl -s http://127.0.0.1:18000/v1/marketplace/stats | jq '.total_offers, .active_miners'

echo ""
echo "aitbc1 marketplace stats:"
curl -s http://127.0.0.1:18001/v1/marketplace/stats | jq '.total_offers, .active_miners'

echo ""
echo "🎉 Scenario B Complete!"
echo "======================="
