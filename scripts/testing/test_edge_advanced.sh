#!/bin/bash
# Integration test script for edge advanced CLI commands
# Tests island leave/bridge, GPU operations, database operations, serve operations, and metrics

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
EDGE_URL="http://127.0.0.1:8200"

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

check_edge() {
    if curl -s -f "$EDGE_URL/health" > /dev/null 2>&1; then
        return 0
    else
        return 1
    fi
}

run_test() {
    local test_name="$1"
    local test_command="$2"
    local require_edge="${3:-true}"

    TESTS_RUN=$((TESTS_RUN + 1))

    if [ "$require_edge" = "true" ] && ! check_edge; then
        log_warn "SKIPPED: $test_name (edge-api not available)"
        TESTS_SKIPPED=$((TESTS_SKIPPED + 1))
        return 0
    fi

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

log_info "Starting edge advanced CLI integration tests"
log_info "Edge API URL: $EDGE_URL"

# Island advanced operations
run_test "Island leave" "aitbc edge island leave test_island_123" "true"

run_test "Island bridge" "aitbc edge island bridge island_b" "true"

# GPU operations
run_test "GPU list" "aitbc edge gpu list-gpus" "true"

run_test "GPU get" "aitbc edge gpu get-gpu gpu_123" "true"

run_test "GPU remove" "aitbc edge gpu remove-gpu gpu_123" "true"

run_test "GPU scan" "aitbc edge gpu scan-gpus miner_123" "true"

run_test "GPU metrics" "aitbc edge gpu gpu-metrics gpu_123" "true"

# Database operations
run_test "Database init" "aitbc edge database init-db test_db island_123 100" "true"

run_test "Database list" "aitbc edge database list-dbs" "true"

run_test "Database get" "aitbc edge database get-db db_123" "true"

run_test "Database delete" "aitbc edge database delete-db db_123" "true"

run_test "Database sync" "aitbc edge database sync-db db_123" "true"

# Serve operations
run_test "Serve submit request" "aitbc edge serve submit-request gpu_123 text-generation '{\"prompt\": \"test\"}'" "true"

run_test "Serve list requests" "aitbc edge serve list-requests" "true"

run_test "Serve get request" "aitbc edge serve get-request req_123" "true"

run_test "Serve cancel request" "aitbc edge serve cancel-request req_123" "true"

run_test "Serve get result" "aitbc edge serve get-result req_123" "true"

# Metrics operations
run_test "Metrics record" "aitbc edge metrics record gpu_123 '{\"metric_name\": \"test_metric\", \"value\": 100}'" "true"

run_test "Metrics list" "aitbc edge metrics list-metrics" "true"

run_test "Metrics get" "aitbc edge metrics get-metric metric_123" "true"

run_test "Metrics delete" "aitbc edge metrics delete-metric metric_123" "true"

# Error handling tests (should handle gracefully)
run_test "Island leave nonexistent" "aitbc edge island leave nonexistent_island" "false"

run_test "GPU get nonexistent" "aitbc edge gpu get-gpu nonexistent_gpu" "false"

# Output format tests
run_test "GPU list table format" "aitbc edge gpu list-gpus --format table" "true"

run_test "Database list table format" "aitbc edge database list-dbs --format table" "true"

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
