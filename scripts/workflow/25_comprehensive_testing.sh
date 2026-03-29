#!/bin/bash

# AITBC Comprehensive Testing Suite
# Tests all blockchain functionality including marketplace scenarios

set -e

echo "=== 🧪 AITBC COMPREHENSIVE TESTING SUITE ==="
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

# Test counters
TESTS_PASSED=0
TESTS_FAILED=0

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

echo "🚀 STARTING COMPREHENSIVE TEST SUITE"
echo "Testing all AITBC blockchain functionality"
echo ""

# 1. BASIC CONNECTIVITY TESTS
echo "1. 🌐 BASIC CONNECTIVITY TESTS"
echo "=============================="

run_test "Local RPC connectivity" "curl -s http://localhost:$GENESIS_PORT/rpc/info"
run_test "Remote RPC connectivity" "ssh $FOLLOWER_NODE 'curl -s http://localhost:$FOLLOWER_PORT/rpc/info'"
run_test "Cross-node SSH connectivity" "ssh $FOLLOWER_NODE 'echo SSH_OK'"
run_test "Network ping connectivity" "ping -c 1 $FOLLOWER_NODE"

# 2. BLOCKCHAIN CORE TESTS
echo ""
echo "2. ⛓️ BLOCKCHAIN CORE TESTS"
echo "=========================="

run_test_verbose "Blockchain head retrieval" "curl -s http://localhost:$GENESIS_PORT/rpc/head | jq .height"
run_test_verbose "Blockchain info retrieval" "curl -s http://localhost:$GENESIS_PORT/rpc/info | jq .total_transactions"
run_test_verbose "Genesis wallet balance" "curl -s 'http://localhost:$GENESIS_PORT/rpc/getBalance/ait1hqpufd2skt3kdhpfdqv7cc3adg6hdgaany343spdlw00xdqn37xsyvz60r' | jq .balance"
run_test_verbose "User wallet balance" "curl -s 'http://localhost:$GENESIS_PORT/rpc/getBalance/ait1e7d5e60688ff0b4a5c6863f1625e47945d84c94b' | jq .balance"

# 3. TRANSACTION TESTS
echo ""
echo "3. 💳 TRANSACTION TESTS"
echo "======================"

run_test_verbose "Transaction submission" "curl -s -X POST http://localhost:$GENESIS_PORT/rpc/sendTx \
  -H 'Content-Type: application/json' \
  -d '{
    \"type\": \"TRANSFER\",
    \"sender\": \"ait1hqpufd2skt3kdhpfdqv7cc3adg6hdgaany343spdlw00xdqn37xsyvz60r\",
    \"nonce\": 1,
    \"fee\": 5,
    \"payload\": {
      \"to\": \"ait1e7d5e60688ff0b4a5c6863f1625e47945d84c94b\",
      \"amount\": 10
    }
  }' | jq .tx_hash"

run_test "Mempool functionality" "curl -s http://localhost:$GENESIS_PORT/rpc/mempool | jq .total"

# 4. CROSS-NODE SYNC TESTS
echo ""
echo "4. 🔄 CROSS-NODE SYNC TESTS"
echo "=========================="

LOCAL_HEIGHT=$(curl -s http://localhost:$GENESIS_PORT/rpc/head | jq .height)
REMOTE_HEIGHT=$(ssh $FOLLOWER_NODE 'curl -s http://localhost:$FOLLOWER_PORT/rpc/head | jq .height')
SYNC_DIFF=$((LOCAL_HEIGHT - REMOTE_HEIGHT))

echo "Local height: $LOCAL_HEIGHT"
echo "Remote height: $REMOTE_HEIGHT"
echo "Sync difference: $SYNC_DIFF"

if [ "$SYNC_DIFF" -lt 100 ]; then
    echo -e "${GREEN}✅ PASS${NC}: Cross-node sync within acceptable range"
    ((TESTS_PASSED++))
else
    echo -e "${RED}❌ FAIL${NC}: Cross-node sync gap too large ($SYNC_DIFF blocks)"
    ((TESTS_FAILED++))
fi

# 5. MARKETPLACE TESTS
echo ""
echo "5. 🛒 MARKETPLACE FUNCTIONALITY TESTS"
echo "===================================="

run_test "Marketplace listings API" "ssh $FOLLOWER_NODE 'curl -s http://localhost:$FOLLOWER_PORT/rpc/marketplace/listings | jq .total'"
run_test "AI submission endpoint" "ssh $FOLLOWER_NODE 'curl -s -X POST http://localhost:$FOLLOWER_PORT/rpc/ai/submit \
  -H \"Content-Type: application/json\" \
  -d \"{\\\"prompt\\\": \\\"Test prompt\\\", \\\"model\\\": \\\"llama2\\\"}\"'"

# 6. SYSTEM HEALTH TESTS
echo ""
echo "6. 🏥 SYSTEM HEALTH TESTS"
echo "========================"

run_test "Blockchain node service" "systemctl is-active aitbc-blockchain-node"
run_test "RPC service" "systemctl is-active aitbc-blockchain-rpc"
run_test "Database accessibility" "test -f /var/lib/aitbc/data/ait-mainnet/chain.db"
run_test "Log directory" "test -d /var/log/aitbc"

# 7. GPU HARDWARE TESTS (if available)
echo ""
echo "7. 🖥️ GPU HARDWARE TESTS"
echo "========================"

if ssh $FOLLOWER_NODE "command -v nvidia-smi" >/dev/null 2>&1; then
    run_test "NVIDIA GPU detection" "ssh $FOLLOWER_NODE 'nvidia-smi --query-gpu=name --format=csv,noheader'"
    run_test "GPU memory check" "ssh $FOLLOWER_NODE 'nvidia-smi --query-gpu=memory.total --format=csv,noheader'"
    run_test "GPU utilization" "ssh $FOLLOWER_NODE 'nvidia-smi --query-gpu=utilization.gpu --format=csv,noheader'"
else
    echo -e "${YELLOW}⚠️ SKIP${NC}: NVIDIA GPU not available"
fi

# 8. INTEGRATION TESTS
echo ""
echo "8. 🔗 INTEGRATION TESTS"
echo "======================"

run_test "Bulk sync functionality" "test -f /opt/aitbc/scripts/fast_bulk_sync.sh"
run_test "Health monitoring" "test -f /opt/aitbc/monitoring/health_monitor.sh"
run_test "Marketplace scenario" "test -f /opt/aitbc/scripts/workflow/24_marketplace_scenario_real.sh"

# 9. PERFORMANCE TESTS
echo ""
echo "9. ⚡ PERFORMANCE TESTS"
echo "======================"

echo "Testing RPC response time..."
START_TIME=$(date +%s%N)
curl -s http://localhost:$GENESIS_PORT/rpc/info >/dev/null
END_TIME=$(date +%s%N)
RESPONSE_TIME=$(( (END_TIME - START_TIME) / 1000000 ))

echo "RPC response time: ${RESPONSE_TIME}ms"

if [ "$RESPONSE_TIME" -lt 1000 ]; then
    echo -e "${GREEN}✅ PASS${NC}: RPC response time acceptable (${RESPONSE_TIME}ms)"
    ((TESTS_PASSED++))
else
    echo -e "${RED}❌ FAIL${NC}: RPC response time too high (${RESPONSE_TIME}ms)"
    ((TESTS_FAILED++))
fi

# 10. SECURITY TESTS
echo ""
echo "10. 🔒 SECURITY TESTS"
echo "====================="

run_test "Security hardening status" "test -f /opt/aitbc/security_summary.txt"
run_test "SSH configuration" "test -f /etc/ssh/sshd_config"
run_test "Firewall status" "ufw status || iptables -L"

# FINAL RESULTS
echo ""
echo "=== 🧪 TEST RESULTS SUMMARY ==="
echo ""
echo "Tests Passed: $TESTS_PASSED"
echo "Tests Failed: $TESTS_FAILED"
echo "Total Tests: $((TESTS_PASSED + TESTS_FAILED))"

if [ "$TESTS_FAILED" -eq 0 ]; then
    echo -e "${GREEN}🎉 ALL TESTS PASSED!${NC}"
    echo "✅ AITBC blockchain is fully functional"
    exit 0
else
    echo -e "${RED}⚠️  SOME TESTS FAILED${NC}"
    echo "❌ Review failed tests and fix issues"
    exit 1
fi
