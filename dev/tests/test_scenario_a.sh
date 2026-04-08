#!/bin/bash
# Scenario A: Localhost GPU Miner → aitbc Marketplace Test

echo "🚀 Scenario A: Localhost GPU Miner → aitbc Marketplace"
echo "=================================================="

# Set up miner1 environment
export MINER_ID="miner1"
export MINER_WALLET="0x1234567890abcdef1234567890abcdef12345678"
export MINER_REGION="localhost"
export OLLAMA_BASE_URL="http://localhost:11434"

echo "📋 Step 1: Check Ollama Models Available"
echo "=========================================="
ollama list

echo ""
echo "📋 Step 2: Check miner1 wallet configuration"
echo "=========================================="
if [ -f "/home/oib/windsurf/aitbc/home/miner1/miner_wallet.json" ]; then
    echo "✅ miner1 wallet found:"
    cat /home/oib/windsurf/aitbc/home/miner1/miner_wallet.json
else
    echo "❌ miner1 wallet not found"
fi

echo ""
echo "📋 Step 3: Verify aitbc marketplace connectivity"
echo "=========================================="
curl -s http://127.0.0.1:8000/v1/health | jq .

echo ""
echo "📋 Step 4: Register miner1 with aitbc marketplace"
echo "=========================================="
aitbc marketplace gpu register \
  --miner-id $MINER_ID \
  --wallet $MINER_WALLET \
  --region $MINER_REGION \
  --gpu-model "NVIDIA-RTX-4060Ti" \
  --gpu-memory "16GB" \
  --compute-capability "8.9" \
  --price-per-hour "0.001" \
  --models "gemma3:1b,lauchacarro/qwen2.5-translator:latest" \
  --endpoint "http://localhost:11434" \
  --marketplace-url "http://127.0.0.1:8000"

echo ""
echo "📋 Step 5: Verify registration on aitbc"
echo "=========================================="
sleep 5
curl -s http://127.0.0.1:8000/v1/marketplace/offers | jq '.[] | select(.miner_id == "miner1")'

echo ""
echo "📋 Step 6: Test direct GPU service"
echo "=========================================="
curl -X POST http://localhost:11434/api/generate \
  -H "Content-Type: application/json" \
  -d '{"model": "gemma3:1b", "prompt": "What is blockchain?", "stream": false}' | jq .

echo ""
echo "📋 Step 7: Test GPU service via marketplace proxy"
echo "=========================================="
curl -X POST http://127.0.0.1:8000/v1/gpu/inference \
  -H "Content-Type: application/json" \
  -d '{"miner_id": "miner1", "model": "gemma3:1b", "prompt": "What is blockchain via proxy?"}' | jq .

echo ""
echo "🎉 Scenario A Complete!"
echo "======================="
