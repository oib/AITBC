#!/bin/bash
# Integration test script for workflow CLI commands
# Tests workflow run, list, status, and stop operations with coordinator-api

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
COORDINATOR_URL="http://127.0.0.1:18000"
TEST_WORKFLOW="test_workflow_$$"

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
    log_info "Checking coordinator-api availability..."
    if curl -s -f "$COORDINATOR_URL/health" > /dev/null 2>&1; then
        log_info "coordinator-api is running"
        return 0
    else
        log_warn "coordinator-api is not running at $COORDINATOR_URL"
        return 1
    fi
}

run_test() {
    local test_name="$1"
    local test_command="$2"
    local require_coordinator="${3:-true}"

    TESTS_RUN=$((TESTS_RUN + 1))

    if [ "$require_coordinator" = "true" ] && ! check_coordinator; then
        log_warn "SKIPPED: $test_name (coordinator-api not available)"
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

cleanup() {
    log_info "Cleaning up test workflows..."
    # Attempt to stop test workflow if it exists
    if [ -n "$TEST_WORKFLOW" ]; then
        aitbc workflow stop "$TEST_WORKFLOW" 2>/dev/null || true
    fi
}

# Setup
cd "$REPO_ROOT"

log_info "Starting workflow CLI integration tests"
log_info "Test workflow name: $TEST_WORKFLOW"
log_info "Coordinator URL: $COORDINATOR_URL"

# Test 1: List workflows
run_test "List workflows" "aitbc workflow list" "true"

# Test 2: Run a simple workflow
run_test "Run workflow" "aitbc workflow run $TEST_WORKFLOW" "true"

# Test 3: Get workflow status
run_test "Get workflow status" "aitbc workflow status $TEST_WORKFLOW" "true"

# Test 4: Run workflow with dry-run flag
run_test "Run workflow dry-run" "aitbc workflow run $TEST_WORKFLOW --dry-run" "false"

# Test 5: Run workflow with async flag
run_test "Run workflow async" "aitbc workflow run ${TEST_WORKFLOW}_async --async" "true"

# Test 6: Stop workflow
run_test "Stop workflow" "aitbc workflow stop $TEST_WORKFLOW" "true"

# Test 7: List workflows in table format
run_test "List workflows table format" "aitbc workflow list --format table" "true"

# Test 8: Get workflow status in JSON format
run_test "Get workflow status JSON" "aitbc workflow status $TEST_WORKFLOW --format json" "true"

# Test 9: Run workflow with parameters
run_test "Run workflow with parameters" "aitbc workflow run ${TEST_WORKFLOW}_params --param gpu_count=2 --param timeout=60" "true"

# Test 10: Status of non-existent workflow (should handle gracefully)
run_test "Status of non-existent workflow" "aitbc workflow status nonexistent_workflow_$$" "false"

# Test 11: Stop non-existent workflow (should handle gracefully)
run_test "Stop non-existent workflow" "aitbc workflow stop nonexistent_workflow_$$" "false"

# Test 12: Workflow with special characters in name
run_test "Workflow with special characters" "aitbc workflow run test-workflow-with-dashes" "false"

# Cleanup
cleanup

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
