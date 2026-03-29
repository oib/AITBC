#!/bin/bash

# AITBC Cross-Node Consensus Testing
# Tests and debugs consensus mechanisms between nodes

set -e

echo "=== 🔗 AITBC CROSS-NODE CONSENSUS TESTING ==="
echo "Timestamp: $(date)"
echo ""

# Colors for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
GENESIS_NODE="localhost"
FOLLOWER_NODE="aitbc"
GENESIS_PORT="8006"
FOLLOWER_PORT="8006"

# Test counters
TESTS_PASSED=0
TESTS_FAILED=0

echo "🔗 CONSENSUS TESTING & DEBUGGING"
echo "Testing blockchain consensus between nodes"
echo ""

# Function to run test
run_test() {
    local test_name="$1"
    local test_command="$2"
    
    echo ""
    echo "🧪 Testing: $test_name"
    echo "================================"
    
    if eval "$test_command" >/dev/null 2>&1; then
        echo -e "${GREEN}✅ PASS${NC}: $test_name"
        ((TESTS_PASSED++))
        return 0
    else
        echo -e "${RED}❌ FAIL${NC}: $test_name"
        ((TESTS_FAILED++))
        return 1
    fi
}

# Function to run test with output
run_test_verbose() {
    local test_name="$1"
    local test_command="$2"
    
    echo ""
    echo "🧪 Testing: $test_name"
    echo "================================"
    
    if eval "$test_command"; then
        echo -e "${GREEN}✅ PASS${NC}: $test_name"
        ((TESTS_PASSED++))
        return 0
    else
        echo -e "${RED}❌ FAIL${NC}: $test_name"
        ((TESTS_FAILED++))
        return 1
    fi
}

# 1. BASIC CONNECTIVITY CONSENSUS
echo "1. 🌐 BASIC CONNECTIVITY CONSENSUS"
echo "================================"

run_test "Both nodes reachable" "ping -c 1 $FOLLOWER_NODE"
run_test "Genesis RPC responding" "curl -s http://localhost:$GENESIS_PORT/rpc/info"
run_test "Follower RPC responding" "ssh $FOLLOWER_NODE 'curl -s http://localhost:$FOLLOWER_PORT/rpc/info'"

# 2. BLOCK HEIGHT CONSENSUS
echo ""
echo "2. 📏 BLOCK HEIGHT CONSENSUS"
echo "============================"

LOCAL_HEIGHT=$(curl -s http://localhost:$GENESIS_PORT/rpc/head | jq .height)
REMOTE_HEIGHT=$(ssh $FOLLOWER_NODE 'curl -s http://localhost:$FOLLOWER_PORT/rpc/head | jq .height')
SYNC_DIFF=$((LOCAL_HEIGHT - REMOTE_HEIGHT))

echo "Local height: $LOCAL_HEIGHT"
echo "Remote height: $REMOTE_HEIGHT"
echo "Sync difference: $SYNC_DIFF"

if [ "$SYNC_DIFF" -le 5 ]; then
    echo -e "${GREEN}✅ PASS${NC}: Block height consensus within acceptable range"
    ((TESTS_PASSED++))
else
    echo -e "${RED}❌ FAIL${NC}: Block height consensus gap too large ($SYNC_DIFF blocks)"
    ((TESTS_FAILED++))
fi

# 3. GENESIS BLOCK CONSENSUS
echo ""
echo "3. 🏛️ GENESIS BLOCK CONSENSUS"
echo "============================"

run_test_verbose "Genesis block hash consistency" "
    LOCAL_GENESIS=$(curl -s http://localhost:$GENESIS_PORT/rpc/block/1 | jq .hash)
    REMOTE_GENESIS=$(ssh $FOLLOWER_NODE 'curl -s http://localhost:$FOLLOWER_PORT/rpc/block/1 | jq .hash')
    echo \"Local genesis: \$LOCAL_GENESIS\"
    echo \"Remote genesis: \$REMOTE_GENESIS\"
    [ \"\$LOCAL_GENESIS\" = \"\$REMOTE_GENESIS\" ]
"

# 4. TRANSACTION CONSENSUS
echo ""
echo "4. 💳 TRANSACTION CONSENSUS"
echo "=========================="

# Create test transaction
echo "Creating test transaction for consensus testing..."
TEST_TX=$(curl -s -X POST http://localhost:$GENESIS_PORT/rpc/sendTx \
  -H "Content-Type: application/json" \
  -d "{
    \"type\": \"TRANSFER\",
    \"sender\": \"ait1hqpufd2skt3kdhpfdqv7cc3adg6hdgaany343spdlw00xdqn37xsyvz60r\",
    \"nonce\": 10,
    \"fee\": 5,
    \"payload\": {
      \"to\": \"ait1e7d5e60688ff0b4a5c6863f1625e47945d84c94b\",
      \"amount\": 1
    }
  }")

TEST_TX_HASH=$(echo "$TEST_TX" | jq -r .tx_hash)
echo "Test transaction: $TEST_TX_HASH"

# Wait for transaction to propagate
echo "Waiting for transaction propagation..."
sleep 5

# Check if transaction appears on both nodes
run_test_verbose "Transaction propagation consensus" "
    echo \"Checking transaction \$TEST_TX_HASH on both nodes...\"
    LOCAL_TX=$(curl -s \"http://localhost:$GENESIS_PORT/rpc/tx/\$TEST_TX_HASH\" | jq .block_height)
    REMOTE_TX=$(ssh $FOLLOWER_NODE \"curl -s \\\"http://localhost:$FOLLOWER_PORT/rpc/tx/\$TEST_TX_HASH\\\" | jq .block_height\")
    echo \"Local tx block: \$LOCAL_TX\"
    echo \"Remote tx block: \$REMOTE_TX\"
    [ \"\$LOCAL_TX\" != \"null\" ] && [ \"\$REMOTE_TX\" != \"null\" ] && [ \"\$LOCAL_TX\" = \"\$REMOTE_TX\" ]
"

# 5. MEMPOOL CONSENSUS
echo ""
echo "5. 📋 MEMPOOL CONSENSUS"
echo "======================"

run_test_verbose "Mempool synchronization" "
    LOCAL_MEMPOOL=$(curl -s http://localhost:$GENESIS_PORT/rpc/mempool | jq .total)
    REMOTE_MEMPOOL=$(ssh $FOLLOWER_NODE 'curl -s http://localhost:$FOLLOWER_PORT/rpc/mempool | jq .total')
    echo \"Local mempool: \$LOCAL_MEMPOOL\"
    echo \"Remote mempool: \$REMOTE_MEMPOOL\"
    # Allow small difference due to timing
    [ \$((LOCAL_MEMPOOL - REMOTE_MEMPOOL)) -le 2 ] && [ \$((REMOTE_MEMPOOL - LOCAL_MEMPOOL)) -le 2 ]
"

# 6. CHAIN STATE CONSENSUS
echo ""
echo "6. ⛓️ CHAIN STATE CONSENSUS"
echo "=========================="

run_test_verbose "Total transactions consensus" "
    LOCAL_TXS=$(curl -s http://localhost:$GENESIS_PORT/rpc/info | jq .total_transactions)
    REMOTE_TXS=$(ssh $FOLLOWER_NODE 'curl -s http://localhost:$FOLLOWER_PORT/rpc/info | jq .total_transactions')
    echo \"Local total txs: \$LOCAL_TXS\"
    echo \"Remote total txs: \$REMOTE_TXS\"
    [ \"\$LOCAL_TXS\" = \"\$REMOTE_TXS\" ]
"

run_test_verbose "Chain hash consistency" "
    LOCAL_CHAIN_HASH=$(curl -s http://localhost:$GENESIS_PORT/rpc/head | jq .hash)
    REMOTE_CHAIN_HASH=$(ssh $FOLLOWER_NODE 'curl -s http://localhost:$FOLLOWER_PORT/rpc/head | jq .hash')
    echo \"Local chain hash: \$LOCAL_CHAIN_HASH\"
    echo \"Remote chain hash: \$REMOTE_CHAIN_HASH\"
    [ \"\$LOCAL_CHAIN_HASH\" = \"\$REMOTE_CHAIN_HASH\" ]
"

# 7. NETWORK PARTITION TESTING
echo ""
echo "7. 🌐 NETWORK PARTITION TESTING"
echo "=============================="

echo "Simulating network partition by blocking sync..."
# Temporarily block sync port (if firewall available)
if command -v ufw >/dev/null 2>&1; then
    ufw --force enable >/dev/null 2>&1
    ufw deny out to $FOLLOWER_NODE port 7070 >/dev/null 2>&1
    echo "Network partition simulated"
    sleep 3
    
    # Create transaction during partition
    echo "Creating transaction during partition..."
    PARTITION_TX=$(curl -s -X POST http://localhost:$GENESIS_PORT/rpc/sendTx \
      -H "Content-Type: application/json" \
      -d "{
        \"type\": \"TRANSFER\",
        \"sender\": \"ait1hqpufd2skt3kdhpfdqv7cc3adg6hdgaany343spdlw00xdqn37xsyvz60r\",
        \"nonce\": 11,
        \"fee\": 5,
        \"payload\": {
          \"to\": \"ait1e7d5e60688ff0b4a5c6863f1625e47945d84c94b\",
          \"amount\": 1
        }
      }")
    
    sleep 5
    
    # Restore network
    ufw --force delete deny out to $FOLLOWER_NODE port 7070 >/dev/null 2>&1
    echo "Network partition restored"
    
    # Wait for sync recovery
    echo "Waiting for sync recovery..."
    sleep 10
    
    # Check if nodes recovered consensus
    RECOVERY_HEIGHT_LOCAL=$(curl -s http://localhost:$GENESIS_PORT/rpc/head | jq .height)
    RECOVERY_HEIGHT_REMOTE=$(ssh $FOLLOWER_NODE 'curl -s http://localhost:$FOLLOWER_PORT/rpc/head | jq .height')
    RECOVERY_DIFF=$((RECOVERY_HEIGHT_LOCAL - RECOVERY_HEIGHT_REMOTE))
    
    if [ "$RECOVERY_DIFF" -le 10 ]; then
        echo -e "${GREEN}✅ PASS${NC}: Network partition recovery successful"
        ((TESTS_PASSED++))
    else
        echo -e "${RED}❌ FAIL${NC}: Network partition recovery failed (diff: $RECOVERY_DIFF)"
        ((TESTS_FAILED++))
    fi
else
    echo -e "${YELLOW}⚠️ SKIP${NC}: Network partition test requires ufw"
fi

# 8. CONSENSUS DEBUGGING TOOLS
echo ""
echo "8. 🔧 CONSENSUS DEBUGGING TOOLS"
echo "=============================="

echo "Generating consensus debugging report..."
DEBUG_REPORT="/opt/aitbc/consensus_debug_$(date +%Y%m%d_%H%M%S).txt"

cat > "$DEBUG_REPORT" << EOF
AITBC Consensus Debugging Report
===============================
Date: $(date)

NODE STATUS
-----------
Genesis Node (localhost:$GENESIS_PORT):
- Height: $(curl -s http://localhost:$GENESIS_PORT/rpc/head | jq .height)
- Hash: $(curl -s http://localhost:$GENESIS_PORT/rpc/head | jq .hash)
- Total TXs: $(curl -s http://localhost:$GENESIS_PORT/rpc/info | jq .total_transactions)
- Mempool: $(curl -s http://localhost:$GENESIS_PORT/rpc/mempool | jq .total)

Follower Node ($FOLLOWER_NODE:$FOLLOWER_PORT):
- Height: $(ssh $FOLLOWER_NODE 'curl -s http://localhost:$FOLLOWER_PORT/rpc/head | jq .height')
- Hash: $(ssh $FOLLOWER_NODE 'curl -s http://localhost:$FOLLOWER_PORT/rpc/head | jq .hash)
- Total TXs: $(ssh $FOLLOWER_NODE 'curl -s http://localhost:$FOLLOWER_PORT/rpc/info | jq .total_transactions')
- Mempool: $(ssh $FOLLOWER_NODE 'curl -s http://localhost:$FOLLOWER_PORT/rpc/mempool | jq .total)

SYNC ANALYSIS
-------------
Height Difference: $SYNC_DIFF blocks
Test Transaction: $TEST_TX_HASH
Network Partition Test: Completed

RECOMMENDATIONS
--------------
EOF

# Add recommendations based on test results
if [ "$SYNC_DIFF" -gt 10 ]; then
    echo "- CRITICAL: Large sync gap detected, run bulk sync" >> "$DEBUG_REPORT"
    echo "- Command: /opt/aitbc/scripts/fast_bulk_sync.sh" >> "$DEBUG_REPORT"
fi

if [ "$TESTS_FAILED" -gt 0 ]; then
    echo "- WARNING: $TESTS_FAILED consensus tests failed" >> "$DEBUG_REPORT"
    echo "- Review network connectivity and node configuration" >> "$DEBUG_REPORT"
fi

if [ "$TESTS_PASSED" -eq "$((TESTS_PASSED + TESTS_FAILED))" ]; then
    echo "- ✅ All consensus tests passed" >> "$DEBUG_REPORT"
    echo "- Nodes are in proper consensus" >> "$DEBUG_REPORT"
fi

echo "Debugging report saved to: $DEBUG_REPORT"

# 9. FINAL RESULTS
echo ""
echo "9. 📊 CONSENSUS TEST RESULTS"
echo "=========================="

echo "Tests Passed: $TESTS_PASSED"
echo "Tests Failed: $TESTS_FAILED"
echo "Total Tests: $((TESTS_PASSED + TESTS_FAILED))"

if [ "$TESTS_FAILED" -eq 0 ]; then
    echo -e "${GREEN}🎉 ALL CONSENSUS TESTS PASSED!${NC}"
    echo "✅ Multi-node blockchain consensus is working correctly"
    exit 0
else
    echo -e "${RED}⚠️  SOME CONSENSUS TESTS FAILED${NC}"
    echo "❌ Review debugging report and fix consensus issues"
    exit 1
fi
