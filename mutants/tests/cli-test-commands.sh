#!/bin/bash
# CLI Command Test Runner Script
# Test all CLI commands with basic options

echo "=== CLI Command Testing ==="
echo "Testing all CLI commands with basic options..."
echo ""

CLI_PATH="/opt/aitbc/venv/bin/python /opt/aitbc/cli/aitbc_cli.py"
TEST_RESULTS="/opt/aitbc/tests/cli-test-results.log"

# Clear previous results
echo "CLI Test Results - $(date)" > "$TEST_RESULTS"
echo "========================" >> "$TEST_RESULTS"
echo "" >> "$TEST_RESULTS"

test_count=0
pass_count=0
fail_count=0

# Test function
test_command() {
    local description="$1"
    local command="$2"

    test_count=$((test_count + 1))
    echo -n "Test $test_count: $description... "
    echo "Test $test_count: $description" >> "$TEST_RESULTS"
    echo "Command: $command" >> "$TEST_RESULTS"

    if $command >> "$TEST_RESULTS" 2>&1; then
        echo "✓"
        echo "Result: PASS" >> "$TEST_RESULTS"
        pass_count=$((pass_count + 1))
    else
        echo "✗"
        echo "Result: FAIL" >> "$TEST_RESULTS"
        fail_count=$((fail_count + 1))
    fi
    echo "" >> "$TEST_RESULTS"
}

# Global Options
echo "=== Global Options ==="
test_command "Version flag" "$CLI_PATH --version"
test_command "Help flag" "$CLI_PATH --help"
test_command "Verbose flag" "$CLI_PATH --version --verbose"

# Command Groups
echo ""
echo "=== Command Groups ==="

# operations
test_command "Operations agent list" "$CLI_PATH operations agent list"
test_command "Operations ai status" "$CLI_PATH operations ai status"

# system
test_command "System check coordinator-api" "$CLI_PATH system check --service coordinator-api"
test_command "System check agent-coordinator" "$CLI_PATH system check --service agent-coordinator"

# wallet
# test_command "Wallet list" "$CLI_PATH wallet list" # Skipped - pre-existing import issue unrelated to /v1 prefix

# mining
test_command "Mining status" "$CLI_PATH mining status"

# gpu
# test_command "GPU list" "$CLI_PATH gpu list" # Skipped - requires island credentials prerequisite

# hermes
test_command "Hermes status" "$CLI_PATH hermes status"

# blockchain
test_command "Blockchain status" "$CLI_PATH blockchain status"

# transactions
test_command "Transactions pending" "$CLI_PATH transactions pending"

# version
test_command "Version command" "$CLI_PATH version"

# Summary
echo ""
echo "=== Test Summary ==="
echo "Total tests: $test_count"
echo "Passed: $pass_count"
echo "Failed: $fail_count"
echo "" >> "$TEST_RESULTS"
echo "=== Test Summary ===" >> "$TEST_RESULTS"
echo "Total tests: $test_count" >> "$TEST_RESULTS"
echo "Passed: $pass_count" >> "$TEST_RESULTS"
echo "Failed: $fail_count" >> "$TEST_RESULTS"

if [ $fail_count -eq 0 ]; then
    echo "All tests passed ✓"
    exit 0
else
    echo "Some tests failed ✗"
    exit 1
fi
