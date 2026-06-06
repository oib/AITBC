#!/bin/bash
# Integration test script for resource CLI commands
# Tests resource status, deallocation, and coordinator-api integration

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Test counters
TESTS_RUN=0
TESTS_PASSED=0
TESTS_FAILED=0

# Helper functions
log_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

run_test() {
    local test_name="$1"
    local test_command="$2"
    
    TESTS_RUN=$((TESTS_RUN + 1))
    log_info "Running: $test_name"
    
    if eval "$test_command"; then
        TESTS_PASSED=$((TESTS_PASSED + 1))
        log_info "PASSED: $test_name"
    else
        TESTS_FAILED=$((TESTS_FAILED + 1))
        log_error "FAILED: $test_name"
        return 1
    fi
}

# Setup
cd "$REPO_ROOT"

log_info "Starting resource CLI integration tests"
log_info "Note: Some tests require coordinator-api running"

# Test 1: Resource status (all resources)
run_test "Resource status (all)" "aitbc resource status"

# Test 2: Resource status (specific resource)
run_test "Resource status (specific)" "aitbc resource status --resource-id test_res_123"

# Test 3: Resource deallocation (with confirmation)
run_test "Resource deallocation (confirmed)" "echo 'y' | aitbc resource deallocate test_res_123"

# Test 4: Resource deallocation (force)
run_test "Resource deallocation (force)" "aitbc resource deallocate test_res_123 --force"

# Test 5: Resource deallocation (cancelled)
run_test "Resource deallocation (cancelled)" "echo 'n' | aitbc resource deallocate test_res_123"

# Test 6: Experimental commands require --mock flag
log_warn "Testing experimental commands (should fail without --mock)"

if aitbc resource allocate --resource-type gpu --quantity 4 2>&1 | grep -q "EXPERIMENTAL"; then
    TESTS_PASSED=$((TESTS_PASSED + 1))
    log_info "PASSED: Allocate shows experimental warning"
else
    TESTS_FAILED=$((TESTS_FAILED + 1))
    log_error "FAILED: Allocate should show experimental warning"
fi
TESTS_RUN=$((TESTS_RUN + 1))

if aitbc resource list 2>&1 | grep -q "EXPERIMENTAL"; then
    TESTS_PASSED=$((TESTS_PASSED + 1))
    log_info "PASSED: List shows experimental warning"
else
    TESTS_FAILED=$((TESTS_FAILED + 1))
    log_error "FAILED: List should show experimental warning"
fi
TESTS_RUN=$((TESTS_RUN + 1))

if aitbc resource release test_res 2>&1 | grep -q "EXPERIMENTAL"; then
    TESTS_PASSED=$((TESTS_PASSED + 1))
    log_info "PASSED: Release shows experimental warning"
else
    TESTS_FAILED=$((TESTS_FAILED + 1))
    log_error "FAILED: Release should show experimental warning"
fi
TESTS_RUN=$((TESTS_RUN + 1))

if aitbc resource utilization 2>&1 | grep -q "EXPERIMENTAL"; then
    TESTS_PASSED=$((TESTS_PASSED + 1))
    log_info "PASSED: Utilization shows experimental warning"
else
    TESTS_FAILED=$((TESTS_FAILED + 1))
    log_error "FAILED: Utilization should show experimental warning"
fi
TESTS_RUN=$((TESTS_RUN + 1))

if aitbc resource optimize 2>&1 | grep -q "EXPERIMENTAL"; then
    TESTS_PASSED=$((TESTS_PASSED + 1))
    log_info "PASSED: Optimize shows experimental warning"
else
    TESTS_FAILED=$((TESTS_FAILED + 1))
    log_error "FAILED: Optimize should show experimental warning"
fi
TESTS_RUN=$((TESTS_RUN + 1))

# Test 7: Mock mode for experimental commands
log_info "Testing experimental commands with --mock flag"

run_test "Allocate with --mock" "aitbc resource allocate --resource-type gpu --quantity 4 --mock"

run_test "List with --mock" "aitbc resource list --mock"

run_test "Release with --mock" "aitbc resource release test_res --mock"

run_test "Utilization with --mock" "aitbc resource utilization --mock"

run_test "Optimize with --mock" "aitbc resource optimize --mock"

# Summary
echo ""
echo "========================================"
echo "Test Summary"
echo "========================================"
echo "Tests Run: $TESTS_RUN"
echo "Tests Passed: $TESTS_PASSED"
echo "Tests Failed: $TESTS_FAILED"
echo "========================================"

if [ $TESTS_FAILED -eq 0 ]; then
    log_info "All tests passed!"
    exit 0
else
    log_error "Some tests failed!"
    exit 1
fi
