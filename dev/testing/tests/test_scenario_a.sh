#!/bin/bash
# Scenario A: Software Offer Creation and Execution (Updated for v0.4.x)

echo "🚀 Scenario A: Software Offer Creation and Execution"
echo "======================================================"


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
echo "📋 Step 1: Check Ollama Models Available"
echo "=========================================="
ollama list || echo "Ollama not available, skipping model check"

echo ""
echo "📋 Step 2: Check aitbc marketplace connectivity"
echo "==============================================="
aitbc market list || echo "Marketplace not available"

echo ""
echo "📋 Step 3: Create Ollama Software Offer"
echo "======================================="
echo "Creating software offer for ollama model..."
OFFER_RESULT=$(aitbc market software-offer ollama llama3.2:3b 0.001 2>&1)
echo "$OFFER_RESULT"

OFFER_ID=$(echo "$OFFER_RESULT" | grep -oP 'sw_offer_\w+' || echo "")
if [ -n "$OFFER_ID" ]; then
    echo "✅ Software offer created: $OFFER_ID"
else
    echo "❌ Failed to create software offer"
    exit 1
fi

echo ""
echo "📋 Step 4: Verify offer in plugin registry"
echo "=========================================="
sleep 2
curl -s $SHOP_URL/plugin/plugins/$OFFER_ID | jq .

echo ""
echo "📋 Step 5: Run inference with created offer"
echo "==========================================="
echo "Running inference test..."
RUN_RESULT=$(aitbc market run $OFFER_ID "What is blockchain?" 2>&1)
echo "$RUN_RESULT"

JOB_ID=$(echo "$RUN_RESULT" | grep -oP 'sw_job_\w+' || echo "")
if [ -n "$JOB_ID" ]; then
    echo "✅ Inference job created: $JOB_ID"
else
    echo "❌ Failed to run inference"
    exit 1
fi

echo ""
echo "📋 Step 6: Test direct Ollama service"
echo "======================================"
if command -v ollama &> /dev/null; then
    curl -X POST http://localhost:11434/api/generate \
      -H "Content-Type: application/json" \
      -d '{"model": "llama3.2:3b", "prompt": "What is blockchain?", "stream": false}' | jq . || echo "Direct Ollama test failed"
else
    echo "Ollama not available, skipping direct test"
fi

echo ""
echo "🎉 Scenario A Complete!"
echo "======================="
echo "✅ Software offer workflow tested successfully"
