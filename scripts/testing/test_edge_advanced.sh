#!/bin/bash
# Integration test script for edge advanced CLI commands
# Tests island leave/bridge, GPU operations, database operations, serve operations, and metrics

set -euo pipefail

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
    local require_edge="$2"
    shift 2

    TESTS_RUN=$((TESTS_RUN + 1))

    if [ "$require_edge" = "true" ] && ! check_edge; then
        log_warn "SKIPPED: $test_name (edge-api not available)"
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

log_info "Starting edge advanced CLI integration tests"
log_info "Edge API URL: $EDGE_URL"

# Island advanced operations
run_test "Island leave" "true" aitbc edge island leave test_island_123

run_test "Island bridge" "true" aitbc edge island bridge island_b

# GPU operations
run_test "GPU list" "true" aitbc edge gpu list-gpus

run_test "GPU get" "true" aitbc edge gpu get-gpu gpu_123

run_test "GPU remove" "true" aitbc edge gpu remove-gpu gpu_123

run_test "GPU scan" "true" aitbc edge gpu scan-gpus miner_123

run_test "GPU metrics" "true" aitbc edge gpu gpu-metrics gpu_123

# Database operations
run_test "Database init" "true" aitbc edge database init-db test_db island_123 100

run_test "Database list" "true" aitbc edge database list-dbs

run_test "Database get" "true" aitbc edge database get-db db_123

run_test "Database delete" "true" aitbc edge database delete-db db_123

run_test "Database sync" "true" aitbc edge database sync-db db_123

# Serve operations
run_test "Serve submit request" "true" aitbc edge serve submit-request gpu_123 text-generation '{"prompt": "test"}'

run_test "Serve list requests" "true" aitbc edge serve list-requests

run_test "Serve get request" "true" aitbc edge serve get-request req_123

run_test "Serve cancel request" "true" aitbc edge serve cancel-request req_123

run_test "Serve get result" "true" aitbc edge serve get-result req_123

# Metrics operations
run_test "Metrics record" "true" aitbc edge metrics record gpu_123 '{"metric_name": "test_metric", "value": 100}'

run_test "Metrics list" "true" aitbc edge metrics list-metrics

run_test "Metrics get" "true" aitbc edge metrics get-metric metric_123

run_test "Metrics delete" "true" aitbc edge metrics delete-metric metric_123

# Error handling tests (should handle gracefully)
run_test "Island leave nonexistent" "false" aitbc edge island leave nonexistent_island

run_test "GPU get nonexistent" "false" aitbc edge gpu get-gpu nonexistent_gpu

# Output format tests
run_test "GPU list table format" "true" aitbc edge gpu list-gpus --format table

run_test "Database list table format" "true" aitbc edge database list-dbs --format table

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
