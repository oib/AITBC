#!/bin/bash
# AITBC Comprehensive Services Test Script
# Tests all services with current AITBC service ports

set -euo pipefail

echo "=== 🧪 AITBC Comprehensive Services Test ==="
echo "Date: $(date)"
echo "Testing all AITBC services with current port numbers"
echo ""

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Test results
PASSED=0
FAILED=0

# Function to test a service
test_service() {
    local name="$1"
    local url="$2"
    local expected_pattern="$3"

    echo -n "Testing $name... "

    if response=$(curl -s "$url" 2>/dev/null); then
        if [[ $response =~ $expected_pattern ]]; then
            echo -e "${GREEN}✅ PASS${NC}"
            ((PASSED++))
            return 0
        else
            echo -e "${RED}❌ FAIL${NC} - Unexpected response"
            echo "  Expected: $expected_pattern"
            echo "  Got: $response"
            ((FAILED++))
            return 1
        fi
    else
        echo -e "${RED}❌ FAIL${NC} - No response"
        ((FAILED++))
        return 1
    fi
}

# Function to test port availability
test_port() {
    local port="$1"
    local name="$2"

    echo -n "Testing port $port ($name)... "

    if sudo netstat -tlnp 2>/dev/null | grep -q ":$port "; then
        echo -e "${GREEN}✅ PASS${NC}"
        ((PASSED++))
        return 0
    else
        echo -e "${RED}❌ FAIL${NC} - Port not listening"
        ((FAILED++))
        return 1
    fi
}

echo "🔍 Core Services Testing"
echo "====================="

# Test Core Services
test_service "Coordinator API (8203)" "http://localhost:8203/v1/health" '"status":"ok"'
test_service "Exchange API (8106)" "http://localhost:8106/" '"detail"'
test_service "Blockchain RPC (8202)" "http://localhost:8202/rpc/head" '"height"'

echo ""
echo "🚀 Enhanced Services Testing"
echo "=========================="

# Test Enhanced Services
test_service "GPU Service (8101)" "http://localhost:8101/health" '"service":"gpu"'
test_service "Multi-Modal Agent (8020)" "http://localhost:8020/health" '"service":"multimodal-agent"'
test_service "Modality Optimization (8021)" "http://localhost:8021/health" '"service":"modality-optimization"'
test_service "Adaptive Learning (8012)" "http://localhost:8012/health" '"service":"adaptive-learning"'

echo ""
echo "🔧 Service Features Testing"
echo "========================="

# Test Service Features
test_service "GPU Status (8101)" "http://localhost:8101/gpu/status" '"gpu_available"'
test_service "Multi-Modal Agent (8020)" "http://localhost:8020/multimodal/status" '"multimodal_capabilities"'
test_service "Modality Optimization (8021)" "http://localhost:8021/optimization/modality" '"optimization_active"'
test_service "Adaptive Learning (8012)" "http://localhost:8012/learning/status" '"learning_active"'

echo ""
echo "🌐 Port Availability Testing"
echo "=========================="

# Test Port Availability
test_port "8203" "Coordinator API"
test_port "8106" "Exchange API"
test_port "8202" "Blockchain RPC"
test_port "8101" "GPU Service"
test_port "8020" "Multi-Modal Agent"
test_port "8021" "Modality Optimization"
test_port "8012" "Adaptive Learning"

echo ""
echo "📊 Test Results Summary"
echo "===================="

TOTAL=$((PASSED + FAILED))
echo "Total Tests: $TOTAL"
echo -e "Passed: ${GREEN}$PASSED${NC}"
echo -e "Failed: ${RED}$FAILED${NC}"

if [ $FAILED -eq 0 ]; then
    echo -e "${GREEN}🎉 All tests passed!${NC}"
    echo "✅ AITBC services are fully operational with current ports"
    exit 0
else
    echo -e "${RED}❌ Some tests failed!${NC}"
    echo "⚠️  Please check the failed services above"
    exit 1
fi
