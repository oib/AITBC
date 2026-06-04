#!/bin/bash
# Scenario B: Software Offer Discovery and Execution (Updated for v0.4.x)

echo "🚀 Scenario B: Software Offer Discovery and Execution"
echo "======================================================"


# Source scenario configuration
if [ -f "/opt/aitbc/.env.scenario" ]; then
    source /opt/aitbc/.env.scenario
    echo "✅ Loaded scenario configuration from /opt/aitbc/.env.scenario"
else
    # Fallback to defaults
    export HUB_URL="${HUB_URL:-https://hub.aitbc.bubuit.net}"
    export SHOP_URL="${SHOP_URL:-https://aitbc3.aitbc.bubuit.net}"
    export BLOCKCHAIN_RPC="${BLOCKCHAIN_RPC:-http://localhost:8202}"
    echo "⚠️  Using default configuration (env file not found)"
fi
echo "📋 Step 1: List all marketplace offers"
echo "======================================"
aitbc market list || echo "Marketplace not available"

echo ""
echo "📋 Step 2: Create multiple software offers"
echo "=========================================="
echo "Creating Ollama offer..."
OLLAMA_OFFER=$(aitbc market software-offer ollama llama2 0.001 2>&1)
OLLAMA_OFFER_ID=$(echo "$OLLAMA_OFFER" | grep -oP 'sw_offer_\w+' || echo "")
echo "Ollama Offer: $OLLAMA_OFFER_ID"

echo ""
echo "Creating Whisper offer..."
WHISPER_OFFER=$(aitbc market software-offer whisper base 0.002 2>&1)
WHISPER_OFFER_ID=$(echo "$WHISPER_OFFER" | grep -oP 'sw_offer_\w+' || echo "")
echo "Whisper Offer: $WHISPER_OFFER_ID"

if [ -n "$OLLAMA_OFFER_ID" ] && [ -n "$WHISPER_OFFER_ID" ]; then
    echo "✅ Both offers created successfully"
else
    echo "⚠️ Some offers may have failed"
fi

echo ""
echo "📋 Step 3: Verify offers in plugin registry"
echo "=========================================="
sleep 2
if [ -n "$OLLAMA_OFFER_ID" ]; then
    echo "Checking Ollama offer in registry:"
    curl -s http://localhost:8109/plugins/$OLLAMA_OFFER_ID | jq .
fi

if [ -n "$WHISPER_OFFER_ID" ]; then
    echo "Checking Whisper offer in registry:"
    curl -s http://localhost:8109/plugins/$WHISPER_OFFER_ID | jq .
fi

echo ""
echo "📋 Step 4: List offers again to verify registration"
echo "=================================================="
aitbc market list

echo ""
echo "📋 Step 5: Execute inference with Ollama offer"
echo "=============================================="
if [ -n "$OLLAMA_OFFER_ID" ]; then
    echo "Running inference..."
    RUN_RESULT=$(aitbc market run $OLLAMA_OFFER_ID "What is artificial intelligence?" 2>&1)
    echo "$RUN_RESULT"
    
    JOB_ID=$(echo "$RUN_RESULT" | grep -oP 'sw_job_\w+' || echo "")
    if [ -n "$JOB_ID" ]; then
        echo "✅ Inference job created: $JOB_ID"
    fi
fi

echo ""
echo "📋 Step 6: Test offer retrieval from registry"
echo "==========================================="
if [ -n "$OLLAMA_OFFER_ID" ]; then
    echo "Retrieving offer details:"
    curl -s $SHOP_URL/plugin/plugins/$OLLAMA_OFFER_ID/offer | jq .
fi

echo ""
echo "🎉 Scenario B Complete!"
echo "======================="
echo "✅ Software offer discovery and execution tested"
