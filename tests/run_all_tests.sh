#!/bin/bash

# AITBC Developer Ecosystem - Comprehensive Test Runner
# This script runs all test suites for the Developer Ecosystem system

set -e

echo "🚀 Starting AITBC Developer Ecosystem Test Suite"
echo "=================================================="

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Function to print colored output
print_status() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

print_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Function to run tests and capture results
run_test_suite() {
    local test_name=$1
    local test_command=$2
    local test_dir=$3
    
    print_status "Running $test_name tests..."
    
    cd "$test_dir" || {
        print_error "Failed to navigate to $test_dir"
        return 1
    }
    
    if eval "$test_command"; then
        print_success "$test_name tests passed!"
        return 0
    else
        print_error "$test_name tests failed!"
        return 1
    fi
}

# Test results tracking
TOTAL_TESTS=0
PASSED_TESTS=0
FAILED_TESTS=0

# 1. Smart Contract Unit Tests
print_status "📋 Phase 1: Smart Contract Unit Tests"
echo "----------------------------------------"

if run_test_suite "Smart Contract" "npx hardhat test tests/contracts/ --reporter spec" "/home/oib/windsurf/aitbc"; then
    ((PASSED_TESTS++))
else
    ((FAILED_TESTS++))
fi
((TOTAL_TESTS++))

# 2. API Integration Tests
print_status "🔌 Phase 2: API Integration Tests"
echo "------------------------------------"

if run_test_suite "API Integration" "npm test tests/integration/" "/home/oib/windsurf/aitbc"; then
    ((PASSED_TESTS++))
else
    ((FAILED_TESTS++))
fi
((TOTAL_TESTS++))

# 3. Frontend E2E Tests
print_status "🌐 Phase 3: Frontend E2E Tests"
echo "---------------------------------"

# Start the frontend dev server in background
print_status "Starting frontend development server..."
cd /home/oib/windsurf/aitbc/apps/marketplace-web
npm run dev &
DEV_SERVER_PID=$!

# Wait for server to start
sleep 10

# Run E2E tests
if run_test_suite "Frontend E2E" "npm run test" "/home/oib/windsurf/aitbc/apps/marketplace-web"; then
    ((PASSED_TESTS++))
else
    ((FAILED_TESTS++))
fi
((TOTAL_TESTS++))

# Stop the dev server
kill $DEV_SERVER_PID 2>/dev/null || true

# 4. Performance Tests
print_status "⚡ Phase 4: Performance Tests"
echo "---------------------------------"

if run_test_suite "Performance" "npm run test:performance" "/home/oib/windsurf/aitbc/tests/load"; then
    ((PASSED_TESTS++))
else
    ((FAILED_TESTS++))
fi
((TOTAL_TESTS++))

# 5. Security Tests
print_status "🔒 Phase 5: Security Tests"
echo "-------------------------------"

if run_test_suite "Security" "npm run test:security" "/home/oib/windsurf/aitbc/tests/security"; then
    ((PASSED_TESTS++))
else
    ((FAILED_TESTS++))
fi
((TOTAL_TESTS++))

# Generate Test Report
echo ""
echo "=================================================="
echo "📊 TEST SUMMARY"
echo "=================================================="
echo "Total Test Suites: $TOTAL_TESTS"
echo -e "Passed: ${GREEN}$PASSED_TESTS${NC}"
echo -e "Failed: ${RED}$FAILED_TESTS${NC}"

if [ $FAILED_TESTS -eq 0 ]; then
    print_success "🎉 All test suites passed! Ready for deployment."
    exit 0
else
    print_error "❌ $FAILED_TESTS test suite(s) failed. Please review the logs above."
    exit 1
fi
fi
