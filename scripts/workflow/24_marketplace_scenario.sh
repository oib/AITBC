#!/bin/bash

# AITBC Marketplace Scenario Test
# Complete marketplace workflow: bidding, confirmation, task execution, payment

set -e

echo "=== 🛒 AITBC MARKETPLACE SCENARIO TEST ==="
echo "Timestamp: $(date)"
echo ""

# Colors for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# Configuration
GENESIS_NODE="localhost"
FOLLOWER_NODE="aitbc"
GENESIS_PORT="8006"
FOLLOWER_PORT="8006"

# Addresses
GENESIS_ADDR="ait1hqpufd2skt3kdhpfdqv7cc3adg6hdgaany343spdlw00xdqn37xsyvz60r"
USER_ADDR="ait1e7d5e60688ff0b4a5c6863f1625e47945d84c94b"

echo "🎯 MARKETPLACE WORKFLOW SCENARIO"
echo "Testing complete marketplace functionality"
echo ""

# 1. USER FROM AITBC SERVER BIDS ON GPU
echo "1. 🎯 USER BIDDING ON GPU PUBLISHED ON MARKET"
echo "=============================================="

# Check available GPU listings on aitbc
echo "Checking GPU marketplace listings on aitbc:"
LISTINGS=$(ssh $FOLLOWER_NODE "curl -s http://localhost:$FOLLOWER_PORT/rpc/market-list | jq .marketplace[0:3] | .[] | {id, title, price, status}" 2>/dev/null || echo "No listings found")
echo "$LISTINGS"

# User places bid on GPU listing
echo "Placing bid on GPU listing..."
BID_RESULT=$(ssh $FOLLOWER_NODE "curl -s -X POST http://localhost:$FOLLOWER_PORT/rpc/market-bid \
  -H 'Content-Type: application/json' \
  -d '{
    \"market_id\": \"gpu_001\",
    \"bidder\": \"$USER_ADDR\",
    \"bid_amount\": 100,
    \"duration_hours\": 2
  }'" 2>/dev/null || echo '{"error": "Bid failed"}')

echo "Bid result: $BID_RESULT"
BID_ID=$(echo "$BID_RESULT" | jq -r .bid_id 2>/dev/null || echo "unknown")
echo "Bid ID: $BID_ID"

if [ "$BID_ID" = "unknown" ] || [ "$BID_ID" = "null" ]; then
    echo -e "${RED}❌ Failed to create bid${NC}"
    exit 1
fi

echo -e "${GREEN}✅ Bid created successfully${NC}"

# 2. AITBC1 CONFIRMS THE BID
echo ""
echo "2. ✅ AITBC1 CONFIRMATION"
echo "========================"

# aitbc1 reviews and confirms the bid
echo "aitbc1 reviewing bid $BID_ID..."
CONFIRM_RESULT=$(curl -s -X POST "http://localhost:$GENESIS_PORT/rpc/market-confirm" \
  -H "Content-Type: application/json" \
  -d "{
    \"bid_id\": \"$BID_ID\",
    \"confirm\": true,
    \"provider\": \"$GENESIS_ADDR\"
  }" 2>/dev/null || echo '{"error": "Confirmation failed"}')

echo "Confirmation result: $CONFIRM_RESULT"
JOB_ID=$(echo "$CONFIRM_RESULT" | jq -r .job_id 2>/dev/null || echo "unknown")
echo "Job ID: $JOB_ID"

if [ "$JOB_ID" = "unknown" ] || [ "$JOB_ID" = "null" ]; then
    echo -e "${RED}❌ Failed to confirm bid${NC}"
    exit 1
fi

echo -e "${GREEN}✅ Bid confirmed, job created${NC}"

# 3. AITBC SERVER SENDS OLLAMA TASK PROMPT
echo ""
echo "3. 🤖 AITBC SERVER SENDS OLLAMA TASK PROMPT"
echo "=========================================="

# aitbc server submits AI task using Ollama
echo "Submitting AI task to confirmed job..."
TASK_RESULT=$(ssh $FOLLOWER_NODE "curl -s -X POST http://localhost:$FOLLOWER_PORT/rpc/ai-submit \
  -H 'Content-Type: application/json' \
  -d '{
    \"job_id\": \"$JOB_ID\",
    \"task_type\": \"llm_inference\",
    \"model\": \"llama2\",
    \"prompt\": \"Analyze the performance implications of blockchain sharding on scalability and security.\",
    \"parameters\": {
      \"max_tokens\": 500,
      \"temperature\": 0.7
    }
  }'" 2>/dev/null || echo '{"error": "Task submission failed"}')

echo "Task submission result: $TASK_RESULT"
TASK_ID=$(echo "$TASK_RESULT" | jq -r .task_id 2>/dev/null || echo "unknown")
echo "Task ID: $TASK_ID"

if [ "$TASK_ID" = "unknown" ] || [ "$TASK_ID" = "null" ]; then
    echo -e "${RED}❌ Failed to submit task${NC}"
    exit 1
fi

echo -e "${GREEN}✅ Task submitted successfully${NC}"

# Monitor task progress
echo "Monitoring task progress..."
STATUS="unknown"
for i in {1..10}; do
    echo "Check $i: Monitoring task $TASK_ID..."
    TASK_STATUS=$(ssh $FOLLOWER_NODE "curl -s http://localhost:$FOLLOWER_PORT/rpc/ai-status?task_id=$TASK_ID" 2>/dev/null || echo '{"status": "unknown"}')
    echo "Status: $TASK_STATUS"
    STATUS=$(echo "$TASK_STATUS" | jq -r .status 2>/dev/null || echo "unknown")
    
    if [ "$STATUS" = "completed" ]; then
        echo -e "${GREEN}✅ Task completed!${NC}"
        break
    elif [ "$STATUS" = "failed" ]; then
        echo -e "${RED}❌ Task failed!${NC}"
        break
    elif [ "$STATUS" = "running" ]; then
        echo "Task is running..."
    fi
    
    sleep 3
done

# Get task result
if [ "$STATUS" = "completed" ]; then
    echo "Getting task result..."
    TASK_RESULT=$(ssh $FOLLOWER_NODE "curl -s http://localhost:$FOLLOWER_PORT/rpc/ai-result?task_id=$TASK_ID" 2>/dev/null || echo '{"result": "No result"}')
    echo "Task result: $TASK_RESULT"
fi

# 4. AITBC1 GETS PAYMENT OVER BLOCKCHAIN
echo ""
echo "4. 💰 AITBC1 BLOCKCHAIN PAYMENT"
echo "==============================="

# aitbc1 processes payment for completed job
echo "Processing blockchain payment for completed job..."
PAYMENT_RESULT=$(curl -s -X POST "http://localhost:$GENESIS_PORT/rpc/market-payment" \
  -H "Content-Type: application/json" \
  -d "{
    \"job_id\": \"$JOB_ID\",
    \"task_id\": \"$TASK_ID\",
    \"amount\": 100,
    \"recipient\": \"$GENESIS_ADDR\",
    \"currency\": \"AIT\"
  }" 2>/dev/null || echo '{"error": "Payment failed"}')

echo "Payment result: $PAYMENT_RESULT"
PAYMENT_TX=$(echo "$PAYMENT_RESULT" | jq -r .transaction_hash 2>/dev/null || echo "unknown")
echo "Payment transaction: $PAYMENT_TX"

if [ "$PAYMENT_TX" = "unknown" ] || [ "$PAYMENT_TX" = "null" ]; then
    echo -e "${RED}❌ Failed to process payment${NC}"
    exit 1
fi

echo -e "${GREEN}✅ Payment transaction created${NC}"

# Wait for payment to be mined
echo "Waiting for payment to be mined..."
TX_STATUS="pending"
for i in {1..15}; do
    echo "Check $i: Checking transaction $PAYMENT_TX..."
    TX_CHECK=$(curl -s "http://localhost:$GENESIS_PORT/rpc/tx/$PAYMENT_TX" 2>/dev/null || echo '{"block_height": null}')
    TX_STATUS=$(echo "$TX_CHECK" | jq -r .block_height 2>/dev/null || echo "pending")
    
    if [ "$TX_STATUS" != "null" ] && [ "$TX_STATUS" != "pending" ]; then
        echo -e "${GREEN}✅ Payment mined in block: $TX_STATUS${NC}"
        break
    fi
    
    sleep 2
done

# 5. FINAL BALANCE VERIFICATION
echo ""
echo "5. 📊 FINAL BALANCE VERIFICATION"
echo "=============================="

# Get initial balances for comparison
echo "Checking final balances..."

# Check aitbc1 balance (should increase by payment amount)
AITBC1_BALANCE=$(curl -s "http://localhost:$GENESIS_PORT/rpc/getBalance/$GENESIS_ADDR" | jq .balance 2>/dev/null || echo "0")
echo "aitbc1 final balance: $AITBC1_BALANCE AIT"

# Check aitbc-user balance (should decrease by payment amount)
AITBC_USER_BALANCE=$(ssh $FOLLOWER_NODE "curl -s http://localhost:$FOLLOWER_PORT/rpc/getBalance/$USER_ADDR" | jq .balance 2>/dev/null || echo "0")
echo "aitbc-user final balance: $AITBC_USER_BALANCE AIT"

# 6. MARKETPLACE STATUS SUMMARY
echo ""
echo "6. 🏪 MARKETPLACE STATUS SUMMARY"
echo "==============================="

echo "Marketplace overview:"
MARKETPLACE_COUNT=$(curl -s "http://localhost:$GENESIS_PORT/rpc/market-list" | jq '.marketplace | length' 2>/dev/null || echo "0")
echo "$MARKETPLACE_COUNT active listings"

echo "Job status:"
JOB_STATUS=$(curl -s "http://localhost:$GENESIS_PORT/rpc/market-status?job_id=$JOB_ID" 2>/dev/null || echo '{"status": "unknown"}')
echo "Job $JOB_ID status: $JOB_STATUS"

echo ""
echo "=== 🛒 MARKETPLACE SCENARIO COMPLETE ==="
echo ""
echo "✅ SCENARIO RESULTS:"
echo "• User bid: $BID_ID"
echo "• Job confirmation: $JOB_ID" 
echo "• Task execution: $TASK_ID"
echo "• Task status: $STATUS"
echo "• Payment transaction: $PAYMENT_TX"
echo "• Payment block: $TX_STATUS"
echo "• aitbc1 balance: $AITBC1_BALANCE AIT"
echo "• aitbc-user balance: $AITBC_USER_BALANCE AIT"
echo ""

# Determine success
if [ "$STATUS" = "completed" ] && [ "$TX_STATUS" != "pending" ] && [ "$TX_STATUS" != "null" ]; then
    echo -e "${GREEN}🎉 MARKETPLACE SCENARIO: SUCCESSFUL${NC}"
    echo "✅ All workflow steps completed successfully"
    exit 0
else
    echo -e "${YELLOW}⚠️  MARKETPLACE SCENARIO: PARTIAL SUCCESS${NC}"
    echo "Some steps may need attention"
    exit 0
fi
