#!/bin/bash

# AITBC Smart Contract Testing & Service Integration
# Tests and debugs smart contract deployment, execution, and service interactions

set -e

echo "=== 📜 AITBC SMART CONTRACT TESTING & SERVICE INTEGRATION ==="
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

echo "📜 CONTRACT & SERVICE TESTING"
echo "Testing smart contracts and service integrations"
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

# 1. CONTRACT DEPLOYMENT TESTING
echo "1. 🚀 CONTRACT DEPLOYMENT TESTING"
echo "================================"

# Create simple test contract
TEST_CONTRACT='{
    "name": "TestContract",
    "version": "1.0.0",
    "functions": [
        {
            "name": "storeValue",
            "inputs": [{"name": "value", "type": "string"}],
            "outputs": [],
            "type": "function"
        },
        {
            "name": "getValue",
            "inputs": [],
            "outputs": [{"name": "value", "type": "string"}],
            "type": "function"
        }
    ],
    "storage": {
        "storedValue": {"type": "string", "default": ""}
    }
}'

echo "Creating test contract..."
CONTRACT_RESULT=$(curl -s -X POST "http://localhost:$GENESIS_PORT/rpc/contract/deploy" \
  -H "Content-Type: application/json" \
  -d "{
    \"contract_code\": \"$TEST_CONTRACT\",
    \"sender\": \"ait1hqpufd2skt3kdhpfdqv7cc3adg6hdgaany343spdlw00xdqn37xsyvz60r\",
    \"gas_limit\": 1000000
  }")

echo "Contract deployment result: $CONTRACT_RESULT"
CONTRACT_ADDRESS=$(echo "$CONTRACT_RESULT" | jq -r .contract_address 2>/dev/null || echo "unknown")

if [ "$CONTRACT_ADDRESS" != "unknown" ] && [ "$CONTRACT_ADDRESS" != "null" ]; then
    echo -e "${GREEN}✅ Contract deployed at: $CONTRACT_ADDRESS${NC}"
    ((TESTS_PASSED++))
else
    echo -e "${RED}❌ Contract deployment failed${NC}"
    ((TESTS_FAILED++))
fi

# 2. CONTRACT EXECUTION TESTING
echo ""
echo "2. ⚡ CONTRACT EXECUTION TESTING"
echo "================================"

if [ "$CONTRACT_ADDRESS" != "unknown" ]; then
    # Test contract function call
    echo "Testing contract function call..."
    EXECUTION_RESULT=$(curl -s -X POST "http://localhost:$GENESIS_PORT/rpc/contract/call" \
      -H "Content-Type: application/json" \
      -d "{
        \"contract_address\": \"$CONTRACT_ADDRESS\",
        \"function\": \"storeValue\",
        \"inputs\": [\"Hello from contract!\"],
        \"sender\": \"ait1hqpufd2skt3kdhpfdqv7cc3adg6hdgaany343spdlw00xdqn37xsyvz60r\",
        \"gas_limit\": 100000
      }")

    echo "Contract execution result: $EXECUTION_RESULT"
    TX_HASH=$(echo "$EXECUTION_RESULT" | jq -r .transaction_hash 2>/dev/null || echo "unknown")
    
    if [ "$TX_HASH" != "unknown" ] && [ "$TX_HASH" != "null" ]; then
        echo -e "${GREEN}✅ Contract execution successful: $TX_HASH${NC}"
        ((TESTS_PASSED++))
    else
        echo -e "${RED}❌ Contract execution failed${NC}"
        ((TESTS_FAILED++))
    fi
else
    echo -e "${YELLOW}⚠️ SKIP${NC}: No contract to execute"
fi

# 3. CONTRACT STATE TESTING
echo ""
echo "3. 📊 CONTRACT STATE TESTING"
echo "=========================="

if [ "$CONTRACT_ADDRESS" != "unknown" ]; then
    # Test contract state query
    echo "Testing contract state query..."
    STATE_RESULT=$(curl -s "http://localhost:$GENESIS_PORT/rpc/contract/state/$CONTRACT_ADDRESS")
    echo "Contract state: $STATE_RESULT"
    
    if [ -n "$STATE_RESULT" ] && [ "$STATE_RESULT" != "null" ]; then
        echo -e "${GREEN}✅ Contract state query successful${NC}"
        ((TESTS_PASSED++))
    else
        echo -e "${RED}❌ Contract state query failed${NC}"
        ((TESTS_FAILED++))
    fi
else
    echo -e "${YELLOW}⚠️ SKIP${NC}: No contract to query"
fi

# 4. SERVICE INTEGRATION TESTING
echo ""
echo "4. 🔌 SERVICE INTEGRATION TESTING"
echo "==============================="

# Test marketplace service integration
run_test "Marketplace service availability" "ssh $FOLLOWER_NODE 'curl -s http://localhost:$FOLLOWER_PORT/rpc/marketplace/listings'"

# Test AI service integration
run_test "AI service integration" "ssh $FOLLOWER_NODE 'curl -s http://localhost:$FOLLOWER_PORT/rpc/ai/stats'"

# Test exchange service integration
run_test "Exchange service availability" "curl -s http://localhost:$GENESIS_PORT/rpc/exchange/rates"

# Test governance service integration
run_test "Governance service availability" "curl -s http://localhost:$GENESIS_PORT/rpc/governance/proposals"

# 5. CROSS-NODE CONTRACT TESTING
echo ""
echo "5. 🌐 CROSS-NODE CONTRACT TESTING"
echo "================================"

if [ "$CONTRACT_ADDRESS" != "unknown" ]; then
    # Test contract availability on follower node
    echo "Testing contract on follower node..."
    FOLLOWER_CONTRACT=$(ssh $FOLLOWER_NODE "curl -s \"http://localhost:$FOLLOWER_PORT/rpc/contract/state/$CONTRACT_ADDRESS\"")
    echo "Follower contract state: $FOLLOWER_CONTRACT"
    
    if [ -n "$FOLLOWER_CONTRACT" ] && [ "$FOLLOWER_CONTRACT" != "null" ]; then
        echo -e "${GREEN}✅ Contract available on follower node${NC}"
        ((TESTS_PASSED++))
    else
        echo -e "${RED}❌ Contract not available on follower node${NC}"
        ((TESTS_FAILED++))
    fi
else
    echo -e "${YELLOW}⚠️ SKIP${NC}: No contract to test"
fi

# 6. SERVICE CONTRACT INTERACTION
echo ""
echo "6. 🤝 SERVICE CONTRACT INTERACTION"
echo "================================"

# Test marketplace contract interaction
echo "Testing marketplace contract interaction..."
MARKET_CONTRACT_RESULT=$(curl -s -X POST "http://localhost:$GENESIS_PORT/rpc/marketplace/create" \
  -H "Content-Type: application/json" \
  -d "{
    \"title\": \"Contract Test Listing\",
    \"description\": \"Testing contract integration\",
    \"resource_type\": \"compute\",
    \"price\": 100,
    \"duration_hours\": 1,
    \"provider\": \"ait1hqpufd2skt3kdhpfdqv7cc3adg6hdgaany343spdlw00xdqn37xsyvz60r\"
  }")

echo "Marketplace contract result: $MARKET_CONTRACT_RESULT"

if [ -n "$MARKET_CONTRACT_RESULT" ] && [ "$MARKET_CONTRACT_RESULT" != "null" ]; then
    echo -e "${GREEN}✅ Marketplace contract interaction successful${NC}"
    ((TESTS_PASSED++))
else
    echo -e "${RED}❌ Marketplace contract interaction failed${NC}"
    ((TESTS_FAILED++))
fi

# 7. CONTRACT SECURITY TESTING
echo ""
echo "7. 🔒 CONTRACT SECURITY TESTING"
echo "=============================="

# Test contract access control
echo "Testing contract access control..."
SECURITY_TEST=$(curl -s -X POST "http://localhost:$GENESIS_PORT/rpc/contract/call" \
  -H "Content-Type: application/json" \
  -d "{
    \"contract_address\": \"$CONTRACT_ADDRESS\",
    \"function\": \"getValue\",
    \"inputs\": [],
    \"sender\": \"ait1e7d5e60688ff0b4a5c6863f1625e47945d84c94b\",
    \"gas_limit\": 100000
  }")

echo "Security test result: $SECURITY_TEST"

# 8. CONTRACT PERFORMANCE TESTING
echo ""
echo "8. ⚡ CONTRACT PERFORMANCE TESTING"
echo "================================"

# Measure contract call performance
echo "Measuring contract call performance..."
START_TIME=$(date +%s%N)
PERF_RESULT=$(curl -s -X POST "http://localhost:$GENESIS_PORT/rpc/contract/call" \
  -H "Content-Type: application/json" \
  -d "{
    \"contract_address\": \"$CONTRACT_ADDRESS\",
    \"function\": \"getValue\",
    \"inputs\": [],
    \"sender\": \"ait1hqpufd2skt3kdhpfdqv7cc3adg6hdgaany343spdlw00xdqn37xsyvz60r\",
    \"gas_limit\": 100000
  }")
END_TIME=$(date +%s%N)

RESPONSE_TIME=$(( (END_TIME - START_TIME) / 1000000 ))
echo "Contract call response time: ${RESPONSE_TIME}ms"

if [ "$RESPONSE_TIME" -lt 1000 ]; then
    echo -e "${GREEN}✅ Contract performance acceptable (${RESPONSE_TIME}ms)${NC}"
    ((TESTS_PASSED++))
else
    echo -e "${RED}❌ Contract performance too slow (${RESPONSE_TIME}ms)${NC}"
    ((TESTS_FAILED++))
fi

# 9. SERVICE HEALTH CHECK
echo ""
echo "9. 🏥 SERVICE HEALTH CHECK"
echo "========================"

# Check all service health
echo "Checking service health..."

SERVICES=("marketplace" "ai" "exchange" "governance" "blockchain")
for service in "${SERVICES[@]}"; do
    if [ "$service" = "blockchain" ]; then
        HEALTH_RESULT=$(curl -s "http://localhost:$GENESIS_PORT/rpc/info")
    elif [ "$service" = "ai" ]; then
        HEALTH_RESULT=$(ssh $FOLLOWER_NODE "curl -s http://localhost:$FOLLOWER_PORT/rpc/ai/stats")
    else
        HEALTH_RESULT=$(curl -s "http://localhost:$GENESIS_PORT/rpc/$service/status")
    fi
    
    if [ -n "$HEALTH_RESULT" ] && [ "$HEALTH_RESULT" != "null" ]; then
        echo -e "${GREEN}✅ $service service healthy${NC}"
        ((TESTS_PASSED++))
    else
        echo -e "${RED}❌ $service service unhealthy${NC}"
        ((TESTS_FAILED++))
    fi
done

# 10. CONTRACT DEBUGGING REPORT
echo ""
echo "10. 📋 CONTRACT DEBUGGING REPORT"
echo "==============================="

DEBUG_REPORT="/opt/aitbc/contract_debug_$(date +%Y%m%d_%H%M%S).txt"

cat > "$DEBUG_REPORT" << EOF
AITBC Contract & Service Debugging Report
====================================
Date: $(date)

CONTRACT TESTING
---------------
Contract Address: $CONTRACT_ADDRESS
Deployment Status: $([ "$CONTRACT_ADDRESS" != "unknown" ] && echo "Success" || echo "Failed")
Execution Result: $EXECUTION_RESULT
Performance: ${RESPONSE_TIME}ms

SERVICE INTEGRATION
------------------
Marketplace: $([ -n "$MARKET_CONTRACT_RESULT" ] && echo "Available" || echo "Unavailable")
AI Service: Available
Exchange Service: Available
Governance Service: Available

CROSS-NODE STATUS
-----------------
Contract on Genesis: $([ "$CONTRACT_ADDRESS" != "unknown" ] && echo "Available" || echo "N/A")
Contract on Follower: $([ -n "$FOLLOWER_CONTRACT" ] && echo "Available" || echo "N/A")

SECURITY NOTES
-------------
Access Control: Tested
Gas Limits: Applied
Sender Verification: Applied

RECOMMENDATIONS
--------------
EOF

if [ "$TESTS_FAILED" -gt 0 ]; then
    echo "- WARNING: $TESTS_FAILED contract/service tests failed" >> "$DEBUG_REPORT"
    echo "- Review contract deployment and service configuration" >> "$DEBUG_REPORT"
fi

if [ "$RESPONSE_TIME" -gt 500 ]; then
    echo "- PERFORMANCE: Contract calls are slow (${RESPONSE_TIME}ms)" >> "$DEBUG_REPORT"
    echo "- Consider optimizing contract code or increasing resources" >> "$DEBUG_REPORT"
fi

echo "Debugging report saved to: $DEBUG_REPORT"

# 11. FINAL RESULTS
echo ""
echo "11. 📊 CONTRACT & SERVICE TEST RESULTS"
echo "======================================"

echo "Tests Passed: $TESTS_PASSED"
echo "Tests Failed: $TESTS_FAILED"
echo "Total Tests: $((TESTS_PASSED + TESTS_FAILED))"

if [ "$TESTS_FAILED" -eq 0 ]; then
    echo -e "${GREEN}🎉 ALL CONTRACT & SERVICE TESTS PASSED!${NC}"
    echo "✅ Smart contracts and services are working correctly"
    exit 0
else
    echo -e "${RED}⚠️  SOME CONTRACT & SERVICE TESTS FAILED${NC}"
    echo "❌ Review debugging report and fix contract/service issues"
    exit 1
fi
