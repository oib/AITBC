#!/bin/bash

# Simplified Marketplace Scenario using existing blockchain endpoints
echo "=== 🛒 SIMPLIFIED MARKETPLACE SCENARIO ==="
echo "Timestamp: $(date)"
echo ""

# Addresses
GENESIS_ADDR="ait1hqpufd2skt3kdhpfdqv7cc3adg6hdgaany343spdlw00xdqn37xsyvz60r"
USER_ADDR="ait1e7d5e60688ff0b4a5c6863f1625e47945d84c94b"

echo "🎯 SIMPLIFIED MARKETPLACE WORKFLOW"
echo "Testing marketplace-like functionality using blockchain"
echo ""

# 1. SIMULATE MARKETPLACE LISTING
echo "1. 📋 SIMULATED GPU LISTING"
echo "=========================="
echo "Creating simulated GPU listing..."
LISTING_ID="gpu_listing_$(date +%s)"
echo "Listing ID: $LISTING_ID"
echo "Title: NVIDIA RTX 4090 GPU"
echo "Price: 100 AIT"
echo "Provider: $GENESIS_ADDR"

# 2. USER BIDDING SIMULATION
echo ""
echo "2. 🎯 USER BIDDING SIMULATION"
echo "============================"
echo "Simulating bid from user $USER_ADDR..."
BID_AMOUNT=100
echo "Bid amount: $BID_AMOUNT AIT"

# Check user balance
USER_BALANCE=$(curl -s "http://localhost:8006/rpc/getBalance/$USER_ADDR" | jq .balance)
echo "User balance: $USER_BALANCE AIT"

if [ "$USER_BALANCE" -lt "$BID_AMOUNT" ]; then
    echo "❌ Insufficient balance for bid"
    exit 1
fi

echo "✅ User has sufficient balance"

# 3. PROVIDER CONFIRMATION
echo ""
echo "3. ✅ PROVIDER CONFIRMATION"
echo "========================"
echo "Provider confirming bid..."
JOB_ID="job_$(date +%s)"
echo "Job ID: $JOB_ID"
echo "Status: confirmed"

# 4. AI TASK EXECUTION (if available)
echo ""
echo "4. 🤖 AI TASK EXECUTION"
echo "======================"
echo "Attempting AI task submission..."

# Try AI submit endpoint
AI_RESULT=$(curl -s -X POST http://localhost:8006/rpc/ai-submit \
  -H "Content-Type: application/json" \
  -d "{
    \"job_id\": \"$JOB_ID\",
    \"task_type\": \"llm_inference\",
    \"model\": \"llama2\",
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

# 5. BLOCKCHAIN PAYMENT SIMULATION
echo ""
echo "5. 💰 BLOCKCHAIN PAYMENT"
echo "======================"
echo "Processing payment for completed job..."

# Create payment transaction
PAYMENT_RESULT=$(curl -s -X POST http://localhost:8006/rpc/sendTx \
  -H "Content-Type: application/json" \
  -d "{
    \"type\": \"TRANSFER\",
    \"sender\": \"$USER_ADDR\",
    \"nonce\": 0,
    \"fee\": 5,
    \"payload\": {
      \"to\": \"$GENESIS_ADDR\",
      \"amount\": $BID_AMOUNT
    }
  }")

echo "Payment result: $PAYMENT_RESULT"
PAYMENT_TX=$(echo "$PAYMENT_RESULT" | jq -r .tx_hash 2>/dev/null || echo "unknown")
echo "Payment transaction: $PAYMENT_TX"

if [ "$PAYMENT_TX" != "unknown" ] && [ "$PAYMENT_TX" != "null" ]; then
    echo "✅ Payment transaction created"
    
    # Wait for mining
    echo "Waiting for payment to be mined..."
    for i in {1..10}; do
        TX_STATUS=$(curl -s "http://localhost:8006/rpc/tx/$PAYMENT_TX" | jq -r .block_height 2>/dev/null || echo "pending")
        if [ "$TX_STATUS" != "null" ] && [ "$TX_STATUS" != "pending" ]; then
            echo "✅ Payment mined in block: $TX_STATUS"
            break
        fi
        sleep 2
    done
else
    echo "❌ Payment transaction failed"
fi

# 6. FINAL BALANCE VERIFICATION
echo ""
echo "6. 📊 FINAL BALANCE VERIFICATION"
echo "=============================="

# Check final balances
GENESIS_BALANCE=$(curl -s "http://localhost:8006/rpc/getBalance/$GENESIS_ADDR" | jq .balance)
USER_FINAL_BALANCE=$(curl -s "http://localhost:8006/rpc/getBalance/$USER_ADDR" | jq .balance)

echo "Genesis final balance: $GENESIS_BALANCE AIT"
echo "User final balance: $USER_FINAL_BALANCE AIT"

echo ""
echo "=== 🛒 SIMPLIFIED MARKETPLACE SCENARIO COMPLETE ==="
echo ""
echo "✅ SCENARIO RESULTS:"
echo "• Listing ID: $LISTING_ID"
echo "• Job ID: $JOB_ID"
echo "• Task ID: $TASK_ID"
echo "• Payment transaction: $PAYMENT_TX"
echo "• Genesis balance: $GENESIS_BALANCE AIT"
echo "• User balance: $USER_FINAL_BALANCE AIT"
echo ""
echo "🎯 MARKETPLACE WORKFLOW: SIMULATED"
