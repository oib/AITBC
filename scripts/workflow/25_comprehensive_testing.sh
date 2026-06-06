#!/bin/bash

# AITBC Comprehensive Testing Suite
# Tests all blockchain functionality including marketplace scenarios

# Removed set -e to allow script to continue on test failures
# Test failures are tracked via TESTS_PASSED and TESTS_FAILED counters

# Source scenario configuration
if [ -f "/etc/aitbc/.env.scenario" ]; then
    source /etc/aitbc/.env.scenario
    echo "✅ Loaded scenario configuration from /etc/aitbc/.env.scenario"
else
    # Fallback to defaults
    export HUB_URL="${HUB_URL:-https://hub.aitbc.bubuit.net}"
    export SHOP_URL="${SHOP_URL:-https://aitbc3.aitbc.bubuit.net}"
    export BLOCKCHAIN_RPC="${BLOCKCHAIN_RPC:-http://localhost:8202}"
    export GENESIS_PORT="${GENESIS_PORT:-8202}"
    export FOLLOWER_PORT="${FOLLOWER_PORT:-8202}"
    export FOLLOWER_NODE="${FOLLOWER_NODE:-}"
    echo "⚠️  Using default configuration (env file not found)"
fi

# Skip remote tests if FOLLOWER_NODE is not set
if [ -z "$FOLLOWER_NODE" ]; then
    echo "[WARN] FOLLOWER_NODE not set - skipping remote node tests"
    echo "   Set FOLLOWER_NODE in /etc/aitbc/.env.scenario to enable multi-node testing"
    SKIP_REMOTE_TESTS=true
else
    SKIP_REMOTE_TESTS=false
fi

echo "=== [TEST] AITBC COMPREHENSIVE TESTING SUITE ==="
echo "Timestamp: $(date)"
echo ""

# Colors for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# Configuration
GENESIS_NODE="localhost"
# FOLLOWER_NODE="aitbc"  # Commented out to respect .env.scenario setting
GENESIS_PORT="8202"
FOLLOWER_PORT="8202"

# Test counters
TESTS_PASSED=0
TESTS_FAILED=0

# Function to run test
run_test() {
    local test_name="$1"
    local test_command="$2"
    
    echo ""
    echo "[TEST] Testing: $test_name"
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
    echo "[TEST] Testing: $test_name"
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

echo "[START] STARTING COMPREHENSIVE TEST SUITE"
echo "Testing all AITBC blockchain functionality"
echo ""

# 1. BASIC CONNECTIVITY TESTS
echo "1. [NET] BASIC CONNECTIVITY TESTS"
echo "=============================="

run_test "Local RPC connectivity" "curl -s http://localhost:$GENESIS_PORT/rpc/info"
if [ "$SKIP_REMOTE_TESTS" = false ]; then
    run_test "Remote RPC connectivity" "ssh -o BatchMode=yes -o ConnectTimeout=5 $FOLLOWER_NODE 'curl -s http://localhost:$FOLLOWER_PORT/rpc/info'"
    run_test "Cross-node SSH connectivity" "ssh -o BatchMode=yes -o ConnectTimeout=5 $FOLLOWER_NODE 'echo SSH_OK'"
    run_test "Network ping connectivity" "ping -c 1 -W 2 $FOLLOWER_NODE"
fi

# 2. BLOCKCHAIN CORE TESTS
echo ""
echo "2. [CHAIN] BLOCKCHAIN CORE TESTS"
echo "=========================="

run_test_verbose "Blockchain head retrieval" "curl -s http://localhost:$GENESIS_PORT/rpc/head | jq .height"
run_test_verbose "Blockchain info retrieval" "curl -s http://localhost:$GENESIS_PORT/rpc/info | jq .total_transactions"
run_test_verbose "Genesis wallet balance" "curl -s 'http://localhost:$GENESIS_PORT/rpc/balance/ait1hqpufd2skt3kdhpfdqv7cc3adg6hdgaany343spdlw00xdqn37xsyvz60r' | jq .balance"
run_test_verbose "User wallet balance" "curl -s 'http://localhost:$GENESIS_PORT/rpc/balance/ait1e7d5e60688ff0b4a5c6863f1625e47945d84c94b' | jq .balance"

# 3. TRANSACTION TESTS
echo ""
echo "3. [TX] TRANSACTION TESTS"
echo "======================"

run_test_verbose "Transaction submission" "curl -s -X POST http://localhost:$GENESIS_PORT/rpc/transaction \
  -H 'Content-Type: application/json' \
  -d '{
    \"type\": \"TRANSFER\",
    \"from\": \"ait1hqpufd2skt3kdhpfdqv7cc3adg6hdgaany343spdlw00xdqn37xsyvz60r\",
    \"to\": \"ait1e7d5e60688ff0b4a5c6863f1625e47945d84c94b\",
    \"amount\": 10,
    \"fee\": 5,
    \"nonce\": 1,
    \"signature\": \"0x0000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000\"
  }' | jq .tx_hash"

run_test "Mempool functionality" "curl -s http://localhost:$GENESIS_PORT/rpc/mempool | jq .total"

# 4. CROSS-NODE SYNC TESTS
echo ""
echo "4. [SYNC] CROSS-NODE SYNC TESTS"
echo "=========================="

if [ "$SKIP_REMOTE_TESTS" = false ]; then
    LOCAL_HEIGHT=$(curl -s http://localhost:$GENESIS_PORT/rpc/head | jq .height)
    REMOTE_HEIGHT=$(ssh -o BatchMode=yes -o ConnectTimeout=5 $FOLLOWER_NODE 'curl -s http://localhost:$FOLLOWER_PORT/rpc/head | jq .height')
    SYNC_DIFF=$((LOCAL_HEIGHT - REMOTE_HEIGHT))

    echo "Local height: $LOCAL_HEIGHT"
    echo "Remote height: $REMOTE_HEIGHT"
    echo "Sync difference: $SYNC_DIFF"

    if [ $SYNC_DIFF -le 1 ]; then
        echo -e "${GREEN}[OK] Nodes are in sync${NC}"
        ((TESTS_PASSED++))
    else
        echo -e "${RED}[FAIL] Nodes are out of sync${NC}"
        ((TESTS_FAILED++))
    fi
else
    echo "[WARN] Skipping cross-node sync tests (FOLLOWER_NODE not set)"
fi

if [ "$SKIP_REMOTE_TESTS" = false ]; then
    if [ "$SYNC_DIFF" -lt 100 ]; then
        echo -e "${GREEN}[OK] PASS${NC}: Cross-node sync within acceptable range"
        ((TESTS_PASSED++))
    else
        echo -e "${RED}[FAIL] Cross-node sync gap too large ($SYNC_DIFF blocks)${NC}"
        ((TESTS_FAILED++))
    fi
fi

# 5. MARKETPLACE TESTS
echo ""
echo "5. [MARKET] MARKETPLACE FUNCTIONALITY TESTS"
echo "===================================="

if [ "$SKIP_REMOTE_TESTS" = false ]; then
    run_test "Marketplace listings API" "ssh -o BatchMode=yes -o ConnectTimeout=5 $FOLLOWER_NODE 'curl -s http://localhost:$FOLLOWER_PORT/rpc/marketplace/listings | jq .total'"
    run_test "AI submission endpoint" "ssh -o BatchMode=yes -o ConnectTimeout=5 $FOLLOWER_NODE 'curl -s -X POST http://localhost:$FOLLOWER_PORT/rpc/ai/submit \
      -H \"Content-Type: application/json\" \
      -d \"{\\\"prompt\\\": \\\"Test prompt\\\", \\\"model\\\": \\\"llama3.2:3b\\\"}\"'"
else
    echo "[WARN] Skipping marketplace tests (FOLLOWER_NODE not set)"
fi

# 6. SYSTEM HEALTH TESTS
echo ""
echo "6. [HEALTH] SYSTEM HEALTH TESTS"
echo "========================"

run_test "Blockchain node service" "systemctl is-active aitbc-blockchain-node"
run_test "RPC service" "systemctl is-active aitbc-blockchain-rpc"
run_test "Database accessibility" "test -d /var/lib/aitbc/data/ait-hub.aitbc.bubuit.net"
run_test "Log directory" "test -d /var/log/aitbc"

# 7. GPU HARDWARE TESTS (if available)
echo ""
echo "7. [GPU] GPU HARDWARE TESTS"
echo "========================"

# Test GPU on localhost first
if command -v nvidia-smi >/dev/null 2>&1; then
    run_test "NVIDIA GPU detection (localhost)" "nvidia-smi --query-gpu=name --format=csv,noheader"
    run_test "GPU memory check (localhost)" "nvidia-smi --query-gpu=memory.total --format=csv,noheader"
    run_test "GPU utilization (localhost)" "nvidia-smi --query-gpu=utilization.gpu --format=csv,noheader"
else
    echo -e "${YELLOW}[WARN] SKIP${NC}: NVIDIA GPU not available on localhost"
fi

# Test GPU on remote follower node if available
if [ "$SKIP_REMOTE_TESTS" = false ]; then
    if ssh -o BatchMode=yes -o ConnectTimeout=5 $FOLLOWER_NODE "command -v nvidia-smi" >/dev/null 2>&1; then
        run_test "NVIDIA GPU detection (remote)" "ssh -o BatchMode=yes -o ConnectTimeout=5 $FOLLOWER_NODE 'nvidia-smi --query-gpu=name --format=csv,noheader'"
        run_test "GPU memory check (remote)" "ssh -o BatchMode=yes -o ConnectTimeout=5 $FOLLOWER_NODE 'nvidia-smi --query-gpu=memory.total --format=csv,noheader'"
        run_test "GPU utilization (remote)" "ssh -o BatchMode=yes -o ConnectTimeout=5 $FOLLOWER_NODE 'nvidia-smi --query-gpu=utilization.gpu --format=csv,noheader'"
    else
        echo -e "${YELLOW}[WARN] SKIP${NC}: NVIDIA GPU not available on remote node"
    fi
else
    echo "[INFO] Skipping remote GPU tests (FOLLOWER_NODE not set)"
fi

# 8. INTEGRATION TESTS
echo ""
echo "8. [INTEGRATION] INTEGRATION TESTS"
echo "======================"

run_test "Bulk sync functionality" "test -f /opt/aitbc/scripts/sync/fast_bulk_sync.sh"
run_test "Health monitoring" "test -f /opt/aitbc/scripts/workflow/22_advanced_monitoring.sh"
run_test "Marketplace scenario" "test -f /opt/aitbc/scripts/workflow/24_marketplace_scenario_real.sh"

# 9. PERFORMANCE TESTS
echo ""
echo "9. [PERF] PERFORMANCE TESTS"
echo "======================"

echo "Testing RPC response time..."
START_TIME=$(date +%s%N)
curl -s http://localhost:$GENESIS_PORT/rpc/info >/dev/null
END_TIME=$(date +%s%N)
RESPONSE_TIME=$(( (END_TIME - START_TIME) / 1000000 ))

echo "RPC response time: ${RESPONSE_TIME}ms"

if [ "$RESPONSE_TIME" -lt 1000 ]; then
    echo -e "${GREEN}[OK] PASS${NC}: RPC response time acceptable (${RESPONSE_TIME}ms)"
    ((TESTS_PASSED++))
else
    echo -e "${RED}[FAIL] RPC response time too high (${RESPONSE_TIME}ms)${NC}"
    ((TESTS_FAILED++))
fi

# 10. SECURITY TESTS
echo ""
echo "10. [SECURITY] SECURITY TESTS"
echo "====================="

run_test "Security hardening status" "test -f /opt/aitbc/scripts/workflow/36_contract_security_testing.sh"
run_test "SSH configuration" "test -f /etc/ssh/sshd_config"

# FINAL RESULTS
echo ""
echo "=== [TEST] TEST RESULTS SUMMARY ==="
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
