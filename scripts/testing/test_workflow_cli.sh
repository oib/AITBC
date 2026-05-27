#!/bin/bash
# Integration test script for workflow CLI commands
# Tests workflow run, list, status, and stop operations

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

log_info "Starting workflow CLI integration tests"

# Test 1: List workflows
run_test "List workflows" "aitbc workflow list"

# Test 2: List workflows in JSON format
run_test "List workflows (JSON)" "aitbc workflow list --format json | tail -n +2 | jq -e '.'"

# Test 3: Run workflow (dry run)
run_test "Run workflow (dry run)" "aitbc workflow run test_workflow --dry-run"

# Test 4: Run workflow basic
run_test "Run workflow basic" "aitbc workflow run test_workflow"

# Test 5: Get workflow status
run_test "Get workflow status" "aitbc workflow status test_workflow"

# Test 6: Stop workflow
run_test "Stop workflow" "aitbc workflow stop test_workflow"

# Test 7: Run workflow with special characters
run_test "Run workflow with dashes" "aitbc workflow run workflow-with-dashes --dry-run"

# Test 8: Run workflow with underscores
run_test "Run workflow with underscores" "aitbc workflow run workflow_with_underscores --dry-run"

# Test 9: Get status of non-existent workflow
run_test "Status of non-existent workflow" "aitbc workflow status nonexistent_workflow_xyz"

# Test 10: Stop non-existent workflow
run_test "Stop non-existent workflow" "aitbc workflow stop nonexistent_workflow_xyz"

# Test 11: Run workflow with config file (create temp config)
TEMP_CONFIG=$(mktemp)
echo "param1: value1" > "$TEMP_CONFIG"
run_test "Run workflow with config" "aitbc workflow run test_workflow --config $TEMP_CONFIG --dry-run"
rm -f "$TEMP_CONFIG"

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
