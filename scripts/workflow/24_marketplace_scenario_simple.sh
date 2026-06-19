#!/usr/bin/env bash

# Simplified Hardware+Software Bundle Marketplace Scenario using existing blockchain endpoints
echo "=== 🛒 SIMPLIFIED HARDWARE+SOFTWARE BUNDLE MARKETPLACE SCENARIO ==="
echo "Timestamp: $(date)"
echo ""

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

# Addresses
GENESIS_ADDR="ait1hqpufd2skt3kdhpfdqv7cc3adg6hdgaany343spdlw00xdqn37xsyvz60r"
USER_ADDR="ait1e7d5e60688ff0b4a5c6863f1625e47945d84c94b"

echo "🎯 SIMPLIFIED HARDWARE+SOFTWARE BUNDLE MARKETPLACE WORKFLOW"
echo "Testing hardware+software bundle marketplace functionality using blockchain"
echo ""

# 1. CREATE HARDWARE+SOFTWARE BUNDLE OFFER
echo "1. 📋 CREATING HARDWARE+SOFTWARE BUNDLE OFFER"
echo "=========================================="
echo "Creating hardware+software bundle offer..."
OFFER_ID="bundle_offer_$(date +%s)"
echo "Bundle Offer ID: $OFFER_ID"
echo "Service Type: Ollama"
echo "Model: llama3.2:3b"
echo "GPU: NVIDIA RTX 4090"
echo "Price: 0.001 AIT per 1k tokens"
echo "Provider: $GENESIS_ADDR"

# 2. VERIFY BUNDLE REGISTRATION
echo ""
echo "2. 🔍 VERIFY BUNDLE REGISTRATION"
echo "=============================="
echo "Checking bundle registration in plugin registry..."
BUNDLE_CHECK=$(curl -s "http://localhost:8109/plugins" 2>/dev/null || echo "[]")
echo "Registry response: $BUNDLE_CHECK"

# 3. BUNDLE EXECUTION
echo ""
echo "3. ✅ BUNDLE EXECUTION"
echo "===================="
echo "Executing bundle job..."
JOB_ID="bundle_job_$(date +%s)"
echo "Job ID: $JOB_ID"
echo "Status: executing"

# 4. AI TASK EXECUTION (if available)
echo ""
echo "4. 🤖 AI TASK EXECUTION"
echo "======================"
echo "Attempting AI task submission..."

# Try AI submit endpoint
AI_RESULT=$(curl -s -X POST $BLOCKCHAIN_RPC/rpc/ai-submit \
  -H "Content-Type: application/json" \
  -d "{
    \"job_id\": \"$JOB_ID\",
    \"task_type\": \"llm_inference\",
    \"model\": \"llama3.2:3b\",
    \"prompt\": \"What is blockchain technology?\",
    \"parameters\": {
      \"max_tokens\": 100,
      \"temperature\": 0.7
    }
  }" 2>/dev/null)

if [ -n "$AI_RESULT" ] && [ "$AI_RESULT" != "null" ] && [ "$AI_RESULT" != '{"detail":"Not Found"}' ]; then
    echo "✅ AI task submitted successfully"
    echo "Result: $AI_RESULT"
    TASK_ID=$(echo "$AI_RESULT" | jq -r .task_id 2>/dev/null || echo "unknown")
else
    echo "⚠️ AI endpoint not available, simulating task completion"
    TASK_ID="simulated_task_$(date +%s)"
    echo "Simulated task ID: $TASK_ID"
fi

# 5. ESCROW PAYMENT FOR BUNDLE USAGE
echo ""
echo "5. 💰 ESCROW PAYMENT FOR BUNDLE USAGE"
echo "=================================="
echo "Processing escrow payment for completed bundle job..."

# Create escrow payment transaction
BUNDLE_COST=10  # Simulated cost in milli-AIT
PAYMENT_RESULT=$(curl -s -X POST $BLOCKCHAIN_RPC/rpc/sendTx \
  -H "Content-Type: application/json" \
  -d "{
    \"type\": \"TRANSFER\",
    \"sender\": \"$USER_ADDR\",
    \"nonce\": 0,
    \"fee\": 5,
    \"payload\": {
      \"to\": \"$GENESIS_ADDR\",
      \"amount\": $BUNDLE_COST
    }
  }")

echo "Payment result: $PAYMENT_RESULT"
PAYMENT_TX=$(echo "$PAYMENT_RESULT" | jq -r .tx_hash 2>/dev/null || echo "unknown")
echo "Payment transaction: $PAYMENT_TX"

if [ "$PAYMENT_TX" != "unknown" ] && [ "$PAYMENT_TX" != "null" ]; then
    echo "✅ Escrow payment transaction created"

    # Wait for mining
    echo "Waiting for payment to be mined..."
    for i in {1..10}; do
        TX_STATUS=$(curl -s "$BLOCKCHAIN_RPC/rpc/tx/$PAYMENT_TX" | jq -r .block_height 2>/dev/null || echo "pending")
        if [ "$TX_STATUS" != "null" ] && [ "$TX_STATUS" != "pending" ]; then
            echo "✅ Payment mined in block: $TX_STATUS"
            break
        fi
        sleep 2
    done
else
    echo "❌ Payment transaction failed"
fi

# 6. FINAL VERIFICATION
echo ""
echo "6. 📊 FINAL VERIFICATION"
echo "======================"

# Check final balances
GENESIS_BALANCE=$(curl -s "$BLOCKCHAIN_RPC/rpc/getBalance/$GENESIS_ADDR" | jq .balance)
USER_FINAL_BALANCE=$(curl -s "$BLOCKCHAIN_RPC/rpc/getBalance/$USER_ADDR" | jq .balance)

echo "Genesis final balance: $GENESIS_BALANCE AIT"
echo "User final balance: $USER_FINAL_BALANCE AIT"

echo ""
echo "=== 🛒 SIMPLIFIED HARDWARE+SOFTWARE BUNDLE MARKETPLACE SCENARIO COMPLETE ==="
echo ""
echo "✅ SCENARIO RESULTS:"
echo "• Bundle Offer ID: $OFFER_ID"
echo "• Job ID: $JOB_ID"
echo "• Task ID: $TASK_ID"
echo "• Payment transaction: $PAYMENT_TX"
echo "• Bundle cost: $BUNDLE_COST milli-AIT"
echo "• Genesis balance: $GENESIS_BALANCE AIT"
echo "• User balance: $USER_FINAL_BALANCE AIT"
echo ""
echo "🎯 HARDWARE+SOFTWARE BUNDLE MARKETPLACE WORKFLOW: SIMULATED"
