#!/bin/bash
# Master Test Runner for Multi-Site AITBC Testing

echo "🚀 Multi-Site AITBC Test Suite Master Runner"
echo "=========================================="
echo "Testing localhost, aitbc, and aitbc1 with all CLI features"
echo ""

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
    if curl -s http://127.0.0.1:18000/v1/health &> /dev/null; then
        echo "✅ aitbc marketplace accessible (port 18000)"
    else
        echo "❌ aitbc marketplace not accessible (port 18000)"
    fi
    
    # Check aitbc1 connectivity
    if curl -s http://127.0.0.1:18001/v1/health &> /dev/null; then
        echo "✅ aitbc1 marketplace accessible (port 18001)"
    else
        echo "❌ aitbc1 marketplace not accessible (port 18001)"
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
    
    if ssh aitbc-cascade "echo 'SSH OK'" &> /dev/null; then
        echo "✅ SSH access to aitbc container"
    else
        echo "❌ SSH access to aitbc container failed"
    fi
    
    if ssh aitbc1-cascade "echo 'SSH OK'" &> /dev/null; then
        echo "✅ SSH access to aitbc1 container"
    else
        echo "❌ SSH access to aitbc1 container failed"
    fi
    
    echo ""
    echo "📋 Checking user configurations..."
    
    # Check miner1 and client1 configurations
    if [ -f "/home/oib/windsurf/aitbc/home/miner1/miner_wallet.json" ]; then
        echo "✅ miner1 configuration found"
    else
        echo "❌ miner1 configuration missing"
    fi
    
    if [ -f "/home/oib/windsurf/aitbc/home/client1/client_wallet.json" ]; then
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
    
    local cli_commands=(
        "chain:list:aitbc chain list --node-endpoint http://127.0.0.1:18000"
        "chain:list:aitbc1:aitbc chain list --node-endpoint http://127.0.0.1:18001"
        "analytics:summary:aitbc:aitbc analytics summary --node-endpoint http://127.0.0.1:18000"
        "analytics:summary:aitbc1:aitbc analytics summary --node-endpoint http://127.0.0.1:18001"
        "marketplace:list:aitbc:aitbc marketplace list --marketplace-url http://127.0.0.1:18000"
        "marketplace:list:aitbc1:aitbc marketplace list --marketplace-url http://127.0.0.1:18001"
        "agent_comm:list:aitbc:aitbc agent_comm list --node-endpoint http://127.0.0.1:18000"
        "agent_comm:list:aitbc1:aitbc agent_comm list --node-endpoint http://127.0.0.1:18001"
        "deploy:overview:aitbc deploy overview --format table"
    )
    
    local passed=0
    local total=0
    
    for cmd_info in "${cli_commands[@]}"; do
        IFS=':' read -r test_name command <<< "$cmd_info"
        total=$((total + 1))
        
        echo "Testing: $test_name"
        if eval "$command" &> /dev/null; then
            echo "✅ $test_name - PASSED"
            passed=$((passed + 1))
        else
            echo "❌ $test_name - FAILED"
        fi
    done
    
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
        "Scenario A: Localhost GPU Miner → aitbc Marketplace:/home/oib/windsurf/aitbc/test_scenario_a.sh"
        "Scenario B: Localhost GPU Client → aitbc1 Marketplace:/home/oib/windsurf/aitbc/test_scenario_b.sh"
        "Scenario C: aitbc Container User Operations:/home/oib/windsurf/aitbc/test_scenario_c.sh"
        "Scenario D: aitbc1 Container User Operations:/home/oib/windsurf/aitbc/test_scenario_d.sh"
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
    if python3 /home/oib/windsurf/aitbc/test_multi_site.py; then
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
        run_scenario "Scenario A" "/home/oib/windsurf/aitbc/test_scenario_a.sh"
        ;;
    "scenario-b")
        run_scenario "Scenario B" "/home/oib/windsurf/aitbc/test_scenario_b.sh"
        ;;
    "scenario-c")
        run_scenario "Scenario C" "/home/oib/windsurf/aitbc/test_scenario_c.sh"
        ;;
    "scenario-d")
        run_scenario "Scenario D" "/home/oib/windsurf/aitbc/test_scenario_d.sh"
        ;;
    "comprehensive")
        python3 /home/oib/windsurf/aitbc/test_multi_site.py
        ;;
    "all"|*)
        main
        ;;
esac
