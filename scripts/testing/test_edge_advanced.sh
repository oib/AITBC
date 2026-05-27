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

run_test "Island bridge" "aitbc edge island bridge --source island_a --target island_b" "true"

# GPU operations
run_test "GPU list" "aitbc edge gpu list_gpus" "true"

run_test "GPU get" "aitbc edge gpu get_gpu --gpu-id gpu_123" "true"

run_test "GPU remove" "aitbc edge gpu remove_gpu --gpu-id gpu_123" "true"

run_test "GPU scan" "aitbc edge gpu scan_gpus" "true"

run_test "GPU metrics" "aitbc edge gpu gpu_metrics --gpu-id gpu_123" "true"

# Database operations
run_test "Database init" "aitbc edge database init_db --db-name test_db" "true"

run_test "Database list" "aitbc edge database list_dbs" "true"

run_test "Database get" "aitbc edge database get_db --db-id db_123" "true"

run_test "Database delete" "aitbc edge database delete_db --db-id db_123" "true"

run_test "Database sync" "aitbc edge database sync_db --db-id db_123" "true"

# Serve operations
run_test "Serve submit request" "aitbc edge serve submit_request --request-type compute --parameters '{\"gpu_count\": 2}'" "true"

run_test "Serve list requests" "aitbc edge serve list_requests" "true"

run_test "Serve get request" "aitbc edge serve get_request --request-id req_123" "true"

run_test "Serve cancel request" "aitbc edge serve cancel_request --request-id req_123" "true"

run_test "Serve get result" "aitbc edge serve get_result --request-id req_123" "true"

# Metrics operations
run_test "Metrics record" "aitbc edge metrics record --metric-name test_metric --value 100" "true"

run_test "Metrics list" "aitbc edge metrics list_metrics" "true"

run_test "Metrics get" "aitbc edge metrics get_metric --metric-id metric_123" "true"

run_test "Metrics delete" "aitbc edge metrics delete_metric --metric-id metric_123" "true"

# Error handling tests (should handle gracefully)
run_test "Island leave nonexistent" "aitbc edge island leave nonexistent_island" "false"

run_test "GPU get nonexistent" "aitbc edge gpu get_gpu --gpu-id nonexistent_gpu" "false"

# Output format tests
run_test "GPU list table format" "aitbc edge gpu list_gpus --format table" "true"

run_test "Database list table format" "aitbc edge database list_dbs --format table" "true"

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
