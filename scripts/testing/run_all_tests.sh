#!/bin/bash
set -euo pipefail

# ssh target for the blockchain container on node1. This used to be a private
# ~/.ssh/config alias, so the script only worked on one operator's workstation.
NODE1_CONTAINER_SSH="${AITBC_NODE1_CONTAINER_SSH:?set AITBC_NODE1_CONTAINER_SSH to the ssh target for the container on node1}"

# Fleet node addresses.
#
# These used to be ssh aliases from one operator's ~/.ssh/config, which meant
# the script only ran on that workstation and named the fleet in a public
# repository. Set them for your own deployment; there is deliberately no
# default.
NODE1_HOST="${AITBC_NODE1_HOST:?set AITBC_NODE1_HOST to the address of node1}"

# Master Test Runner for Multi-Site AITBC Testing

echo "🚀 Multi-Site AITBC Test Suite Master Runner"
echo "=========================================="
echo "Testing localhost, aitbc, and ${NODE1_HOST} with all CLI features"
echo ""

# Resolve project root (directory containing this script)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR" && pwd)"

# Function to run a test scenario
run_scenario() {
    local scenario_name=$1
    local script_path=$2

    echo ""
    echo "🔧 Running $scenario_name"
    echo "================================"

    if [ -f "$script_path" ]; then
        bash "$script_path"
        local exit_code=$?
        if [ $exit_code -eq 0 ]; then
            echo "✅ $scenario_name completed successfully"
        else
            echo "❌ $scenario_name failed with exit code $exit_code"
        fi
        return $exit_code
    else
        echo "❌ Script not found: $script_path"
        return 1
    fi
}

# Function to check prerequisites
check_prerequisites() {
    echo "🔍 Checking prerequisites..."
    echo "=========================="

    # Check if aitbc CLI is available
    if command -v aitbc &> /dev/null; then
        echo "✅ AITBC CLI found"
        aitbc --version | head -1
    else
        echo "❌ AITBC CLI not found in PATH"
        echo "Please ensure CLI is installed and in PATH"
        return 1
    fi

    # Check if required services are running
    echo ""
    echo "🌐 Checking service connectivity..."

    # Check aitbc connectivity
    if curl -s http://127.0.0.1:8000/v1/health &> /dev/null; then
        echo "✅ aitbc marketplace accessible (port 8102)"
    else
        echo "❌ aitbc marketplace not accessible (port 8102)"
    fi

    # Check ${NODE1_HOST} connectivity
    if curl -s http://127.0.0.1:8015/v1/health &> /dev/null; then
        echo "✅ ${NODE1_HOST} marketplace accessible (port 8102)"
    else
        echo "❌ ${NODE1_HOST} marketplace not accessible (port 8102)"
    fi

    # Check Ollama
    if ollama list &> /dev/null; then
        echo "✅ Ollama GPU service available"
        ollama list | head -3
    else
        echo "❌ Ollama GPU service not available"
    fi

    # Check SSH access to containers
    echo ""
    echo "🏢 Checking container access..."

    if ssh "${AITBC_NODE1_CONTAINER_SSH:?set AITBC_NODE1_CONTAINER_SSH to the ssh target for the container on node1}" "echo 'SSH OK'" &> /dev/null; then
        echo "✅ SSH access to aitbc container"
    else
        echo "❌ SSH access to aitbc container failed"
    fi

    if ssh ${NODE1_CONTAINER_SSH} "echo 'SSH OK'" &> /dev/null; then
        echo "✅ SSH access to ${NODE1_HOST} container"
    else
        echo "❌ SSH access to ${NODE1_HOST} container failed"
    fi

    echo ""
    echo "📋 Checking user configurations..."

    # Check miner1 and client1 configurations (relative to project root)
    local home_dir="$PROJECT_ROOT/home"
    if [ -f "$home_dir/miner1/miner_wallet.json" ]; then
        echo "✅ miner1 configuration found"
    else
        echo "❌ miner1 configuration missing"
    fi

    if [ -f "$home_dir/client1/client_wallet.json" ]; then
        echo "✅ client1 configuration found"
    else
        echo "❌ client1 configuration missing"
    fi

    echo ""
    echo "🔧 Prerequisite check complete"
    echo "=============================="
}

# Function to run comprehensive CLI tests
run_cli_tests() {
    echo ""
    echo "🔧 Running Comprehensive CLI Tests"
    echo "================================="

    local passed=0
    local total=0

    run_cli_test() {
        local test_name="$1"
        shift
        total=$((total + 1))

        echo "Testing: $test_name"
        if "$@" &> /dev/null; then
            echo "✅ $test_name - PASSED"
            passed=$((passed + 1))
        else
            echo "❌ $test_name - FAILED"
        fi
    }

    run_cli_test "chain:list:aitbc" aitbc chain list --node-url http://127.0.0.1:8202
    run_cli_test "chain:list:${NODE1_HOST}" aitbc chain list --node-url https://hub.aitbc.bubuit.net/rpc
    run_cli_test "analytics:summary:aitbc" aitbc analytics summary --chain-id ait-hub.aitbc.bubuit.net
    run_cli_test "analytics:summary:${NODE1_HOST}" aitbc analytics summary --chain-id ait-hub.aitbc.bubuit.net
    run_cli_test "marketplace:list:aitbc" aitbc market list
    run_cli_test "marketplace:list:${NODE1_HOST}" aitbc market list --service-type ollama
    run_cli_test "system:check:blockchain-node" aitbc system check --service blockchain-node
    run_cli_test "system:check:gpu" aitbc system check --service gpu
    run_cli_test "system:check:marketplace" aitbc system check --service marketplace

    echo ""
    echo "CLI Test Results: $passed/$total passed"
    return $((total - passed))
}

# Function to generate final report
generate_report() {
    local total_scenarios=$1
    local passed_scenarios=$2
    local failed_scenarios=$((total_scenarios - passed_scenarios))

    echo ""
    echo "📊 FINAL TEST REPORT"
    echo "==================="
    echo "Total Scenarios: $total_scenarios"
    echo "Passed: $passed_scenarios"
    echo "Failed: $failed_scenarios"

    if [ $failed_scenarios -eq 0 ]; then
        echo ""
        echo "🎉 ALL TESTS PASSED!"
        echo "Multi-site AITBC ecosystem is fully functional"
        return 0
    else
        echo ""
        echo "⚠️ SOME TESTS FAILED"
        echo "Please check the failed scenarios and fix issues"
        return 1
    fi
}

# Main execution
main() {
    local scenario_count=0
    local passed_count=0

    # Check prerequisites
    if ! check_prerequisites; then
        echo "❌ Prerequisites not met. Exiting."
        exit 1
    fi

    # Run CLI tests first
    echo ""
    if run_cli_tests; then
        echo "✅ All CLI tests passed"
        passed_count=$((passed_count + 1))
    else
        echo "❌ Some CLI tests failed"
    fi
    scenario_count=$((scenario_count + 1))

    # Run scenario tests
    local scenarios=(
        "Scenario A: Localhost GPU Miner → aitbc Marketplace:$PROJECT_ROOT/test_scenario_a.sh"
        "Scenario B: Localhost GPU Client → ${NODE1_HOST} Marketplace:$PROJECT_ROOT/test_scenario_b.sh"
        "Scenario C: aitbc Container User Operations:$PROJECT_ROOT/test_scenario_c.sh"
        "Scenario D: ${NODE1_HOST} Container User Operations:$PROJECT_ROOT/test_scenario_d.sh"
    )

    for scenario_info in "${scenarios[@]}"; do
        IFS=':' read -r scenario_name script_path <<< "$scenario_info"
        scenario_count=$((scenario_count + 1))

        if run_scenario "$scenario_name" "$script_path"; then
            passed_count=$((passed_count + 1))
        fi
    done

    # Run comprehensive test suite
    echo ""
    echo "🔧 Running Comprehensive Test Suite"
    echo "=================================="
    if python3 "$PROJECT_ROOT/test_multi_site.py"; then
        echo "✅ Comprehensive test suite passed"
        passed_count=$((passed_count + 1))
    else
        echo "❌ Comprehensive test suite failed"
    fi
    scenario_count=$((scenario_count + 1))

    # Generate final report
    generate_report $scenario_count $passed_count
}

# Parse command line arguments
case "${1:-all}" in
    "prereq")
        check_prerequisites
        ;;
    "cli")
        run_cli_tests
        ;;
    "scenario-a")
        run_scenario "Scenario A" "$PROJECT_ROOT/test_scenario_a.sh"
        ;;
    "scenario-b")
        run_scenario "Scenario B" "$PROJECT_ROOT/test_scenario_b.sh"
        ;;
    "scenario-c")
        run_scenario "Scenario C" "$PROJECT_ROOT/test_scenario_c.sh"
        ;;
    "scenario-d")
        run_scenario "Scenario D" "$PROJECT_ROOT/test_scenario_d.sh"
        ;;
    "comprehensive")
        python3 "$PROJECT_ROOT/test_multi_site.py"
        ;;
    "all"|*)
        main
        ;;
esac
