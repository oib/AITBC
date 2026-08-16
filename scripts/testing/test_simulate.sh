#!/bin/bash
# Integration test script for simulate CLI commands
# Tests simulation operations including blockchain, wallets, price, network, and ai-jobs

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
COORDINATOR_URL="http://127.0.0.1:18000"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Test counters
TESTS_RUN=0
TESTS_PASSED=0
TESTS_FAILED=0
TESTS_SKIPPED=0

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

check_coordinator() {
    if curl -s -f "$COORDINATOR_URL/health" > /dev/null 2>&1; then
        return 0
    else
        return 1
    fi
}

run_test() {
    local test_name="$1"
    local require_coordinator="$2"
    shift 2

    TESTS_RUN=$((TESTS_RUN + 1))

    if [ "$require_coordinator" = "true" ] && ! check_coordinator; then
        log_warn "SKIPPED: $test_name (coordinator-api not available)"
        TESTS_SKIPPED=$((TESTS_SKIPPED + 1))
        return 0
    fi

    log_info "Running: $test_name"

    if "$@"; then
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

log_info "Starting simulate CLI integration tests"
log_info "Coordinator URL: $COORDINATOR_URL"

# Test 1: Blockchain simulation
run_test "Blockchain simulation" "true" aitbc simulate blockchain --blocks 10 --transactions 50

# Test 2: Wallets simulation
run_test "Wallets simulation" "true" aitbc simulate wallets --count 5 --balance 1000

# Test 3: Price simulation
run_test "Price simulation" "true" aitbc simulate price --days 30 --volatility 0.1

# Test 4: Network simulation
run_test "Network simulation" "true" aitbc simulate network --nodes 10 --latency 50

# Test 5: AI jobs simulation
run_test "AI jobs simulation" "true" aitbc simulate ai-jobs --jobs 20 --duration 300

# Test 6: Run simulation
run_test "Run simulation" "true" aitbc simulate run --type blockchain --duration 60

# Test 7: Blockchain with custom parameters
run_test "Blockchain with params" "true" aitbc simulate blockchain --blocks 100 --transactions 500 --difficulty 5

# Test 8: Wallets with distribution
run_test "Wallets with distribution" "true" aitbc simulate wallets --count 10 --distribution exponential

# Test 9: Price with trend
run_test "Price with trend" "true" aitbc simulate price --days 90 --trend bullish --volatility 0.15

# Test 10: Network with topology
run_test "Network with topology" "true" aitbc simulate network --nodes 20 --topology mesh --latency 100

# Test 11: AI jobs with GPU
run_test "AI jobs with GPU" "true" aitbc simulate ai-jobs --jobs 30 --gpu-required --duration 600

# Test 12: Run async simulation
run_test "Run async simulation" "true" aitbc simulate run --type network --async --duration 120

# Test 13: Status of non-existent simulation (should handle gracefully)
run_test "Status non-existent simulation" "false" aitbc simulate status sim_nonexistent_12345

# Test 14: Result of non-existent simulation (should handle gracefully)
run_test "Result non-existent simulation" "false" aitbc simulate result sim_nonexistent_12345

# Test 15: Output format JSON
run_test "Output format JSON" "true" aitbc simulate blockchain --blocks 5 --format json

# Test 16: Output format table
run_test "Output format table" "true" aitbc simulate blockchain --blocks 5 --format table

# Summary
echo ""
echo "========================================"
echo "Test Summary"
echo "========================================"
echo "Tests Run: $TESTS_RUN"
echo "Tests Passed: $TESTS_PASSED"
echo "Tests Failed: $TESTS_FAILED"
echo "Tests Skipped: $TESTS_SKIPPED"
echo "========================================"

if [ $TESTS_FAILED -eq 0 ]; then
    log_info "All tests passed!"
    exit 0
else
    log_error "Some tests failed!"
    exit 1
fi
