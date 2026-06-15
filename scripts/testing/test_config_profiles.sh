#!/bin/bash
# Integration test script for config profiles CLI commands
# Tests profile save, list, load, and delete operations with file system validation

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
PROFILES_DIR="$HOME/.config/aitbc/profiles"
TEST_PROFILE="test_profile_$$"
CONFIG_FILE=".aitbc.yaml"

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

cleanup() {
    log_info "Cleaning up test artifacts..."

    # Remove test profile if it exists
    if [ -f "$PROFILES_DIR/$TEST_PROFILE.yaml" ]; then
        rm -f "$PROFILES_DIR/$TEST_PROFILE.yaml"
        log_info "Removed test profile: $TEST_PROFILE"
    fi

    # Remove test config file if it exists
    if [ -f "$REPO_ROOT/$CONFIG_FILE" ]; then
        rm -f "$REPO_ROOT/$CONFIG_FILE"
        log_info "Removed test config file"
    fi
}

# Setup
cd "$REPO_ROOT"
mkdir -p "$PROFILES_DIR"

log_info "Starting config profiles integration tests"
log_info "Test profile name: $TEST_PROFILE"
log_info "Profiles directory: $PROFILES_DIR"

# Test 1: Save profile
run_test "Save profile" "aitbc config profiles save $TEST_PROFILE"

# Verify profile file was created
if [ -f "$PROFILES_DIR/$TEST_PROFILE.yaml" ]; then
    log_info "Profile file created successfully"
else
    log_error "Profile file was not created"
    TESTS_FAILED=$((TESTS_FAILED + 1))
fi

# Test 2: List profiles (should include our test profile)
run_test "List profiles" "aitbc config profiles list | grep -q $TEST_PROFILE"

# Test 3: Load profile
run_test "Load profile" "aitbc config profiles load $TEST_PROFILE"

# Verify config file was created
if [ -f "$REPO_ROOT/$CONFIG_FILE" ]; then
    log_info "Config file created by profile load"
else
    log_error "Config file was not created by profile load"
    TESTS_FAILED=$((TESTS_FAILED + 1))
fi

# Test 4: Delete profile (with confirmation)
run_test "Delete profile" "echo 'y' | aitbc config profiles delete $TEST_PROFILE"

# Verify profile file was deleted
if [ ! -f "$PROFILES_DIR/$TEST_PROFILE.yaml" ]; then
    log_info "Profile file deleted successfully"
else
    log_error "Profile file was not deleted"
    TESTS_FAILED=$((TESTS_FAILED + 1))
fi

# Test 5: Save again for cancellation test
run_test "Save profile again" "aitbc config profiles save $TEST_PROFILE"

# Test 6: Delete with cancellation
run_test "Delete profile (cancelled)" "echo 'n' | aitbc config profiles delete $TEST_PROFILE"

# Verify profile still exists after cancellation
if [ -f "$PROFILES_DIR/$TEST_PROFILE.yaml" ]; then
    log_info "Profile file preserved after cancellation"
else
    log_error "Profile file was deleted despite cancellation"
    TESTS_FAILED=$((TESTS_FAILED + 1))
fi

# Test 7: Load non-existent profile (should fail)
if aitbc config profiles load nonexistent_profile_$$ 2>&1 | grep -q "not found"; then
    TESTS_PASSED=$((TESTS_PASSED + 1))
    log_info "PASSED: Load non-existent profile fails correctly"
else
    TESTS_FAILED=$((TESTS_FAILED + 1))
    log_error "FAILED: Load non-existent profile should fail"
fi
TESTS_RUN=$((TESTS_RUN + 1))

# Test 8: Delete non-existent profile (should fail)
if aitbc config profiles delete nonexistent_profile_$$ 2>&1 | grep -q "not found"; then
    TESTS_PASSED=$((TESTS_PASSED + 1))
    log_info "PASSED: Delete non-existent profile fails correctly"
else
    TESTS_FAILED=$((TESTS_FAILED + 1))
    log_error "FAILED: Delete non-existent profile should fail"
fi
TESTS_RUN=$((TESTS_RUN + 1))

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
echo "========================================"

if [ $TESTS_FAILED -eq 0 ]; then
    log_info "All tests passed!"
    exit 0
else
    log_error "Some tests failed!"
    exit 1
fi
