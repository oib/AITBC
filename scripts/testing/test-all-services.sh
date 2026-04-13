#!/bin/bash
# AITBC Comprehensive Services Test Script
# Tests all services with new port logic implementation

set -euo pipefail

echo "=== 🧪 AITBC Comprehensive Services Test ==="
echo "Date: $(date)"
echo "Testing all services with new port logic (8000-8003, 8010-8015)"
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
test_service "Coordinator API (8000)" "http://localhost:8000/v1/health" '"status":"ok"'
test_service "Exchange API (8001)" "http://localhost:8001/" '"detail"'
test_service "Blockchain RPC (8003)" "http://localhost:8003/rpc/head" '"height"'

echo ""
echo "🚀 Enhanced Services Testing"
echo "=========================="

# Test Enhanced Services
test_service "Multimodal GPU (8010)" "http://localhost:8010/health" '"service":"gpu-multimodal"'
test_service "GPU Multimodal (8011)" "http://localhost:8011/health" '"service":"gpu-multimodal"'
test_service "Modality Optimization (8012)" "http://localhost:8012/health" '"service":"modality-optimization"'
test_service "Adaptive Learning (8013)" "http://localhost:8013/health" '"service":"adaptive-learning"'

echo ""
echo "🔧 Service Features Testing"
echo "========================="

# Test Service Features
test_service "GPU Status (8010)" "http://localhost:8010/gpu/status" '"gpu_available"'
test_service "GPU Multimodal Features (8011)" "http://localhost:8011/gpu/multimodal" '"multimodal_capabilities"'
test_service "Modality Optimization (8012)" "http://localhost:8012/optimization/modality" '"optimization_active"'
test_service "Learning Status (8013)" "http://localhost:8013/learning/status" '"learning_active"'

echo ""
echo "🌐 Port Availability Testing"
echo "=========================="

# Test Port Availability
test_port "8000" "Coordinator API"
test_port "8001" "Exchange API"
test_port "8003" "Blockchain RPC"
test_port "8010" "Multimodal GPU"
test_port "8011" "GPU Multimodal"
test_port "8012" "Modality Optimization"
test_port "8013" "Adaptive Learning"

echo ""
echo "📊 Test Results Summary"
echo "===================="

TOTAL=$((PASSED + FAILED))
echo "Total Tests: $TOTAL"
echo -e "Passed: ${GREEN}$PASSED${NC}"
echo -e "Failed: ${RED}$FAILED${NC}"

if [ $FAILED -eq 0 ]; then
    echo -e "${GREEN}🎉 All tests passed!${NC}"
    echo "✅ AITBC services are fully operational with new port logic"
    exit 0
else
    echo -e "${RED}❌ Some tests failed!${NC}"
    echo "⚠️  Please check the failed services above"
    exit 1
fi
