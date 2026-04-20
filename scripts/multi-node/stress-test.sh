#!/bin/bash
#
# Multi-Node Stress Testing Script
# Generates high transaction volume and monitors performance
# Uses RPC endpoints only, no SSH access
#

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"

# Node Configuration
NODES=(
    "aitbc:10.1.223.93"
    "aitbc1:10.1.223.40"
    "aitbc2:10.1.223.98"
)

RPC_PORT=8006
CLI_PATH="${CLI_PATH:-${REPO_ROOT}/aitbc-cli}"
LOG_DIR="/var/log/aitbc"
LOG_FILE="${LOG_DIR}/stress-test.log"

# Stress Test Configuration
STRESS_WALLET_NAME="stress-test-wallet"
STRESS_WALLET_PASSWORD="stress123456"
TRANSACTION_COUNT=${TRANSACTION_COUNT:-100}
TRANSACTION_RATE=${TRANSACTION_RATE:-1}  # transactions per second
TARGET_TPS=${TARGET_TPS:-10}
LATENCY_THRESHOLD=${LATENCY_THRESHOLD:-5}
ERROR_RATE_THRESHOLD=${ERROR_RATE_THRESHOLD:-5}

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

# Logging functions
log() {
    local level="$1"
    shift
    local message="$@"
    local timestamp=$(date '+%Y-%m-%d %H:%M:%S')
    echo "[${timestamp}] [${level}] ${message}" | tee -a "${LOG_FILE}"
}

log_success() {
    log "SUCCESS" "$@"
    echo -e "${GREEN}$@${NC}"
}

log_error() {
    log "ERROR" "$@"
    echo -e "${RED}$@${NC}"
}

log_warning() {
    log "WARNING" "$@"
    echo -e "${YELLOW}$@${NC}"
}

# Create stress test wallet
create_stress_wallet() {
    log "Creating stress test wallet: ${STRESS_WALLET_NAME}"
    
    # Remove existing wallet if it exists
    ${CLI_PATH} wallet delete --name "${STRESS_WALLET_NAME}" --yes 2>/dev/null || true
    
    # Create new wallet
    ${CLI_PATH} wallet create --name "${STRESS_WALLET_NAME}" --password "${STRESS_WALLET_PASSWORD}" --yes --no-confirm >> "${LOG_FILE}" 2>&1
    
    log_success "Stress test wallet created: ${STRESS_WALLET_NAME}"
}

# Get wallet balance
get_wallet_balance() {
    local wallet_name="$1"
    ${CLI_PATH} wallet balance --name "${wallet_name}" --output json 2>/dev/null | grep -o '"balance":[0-9.]*' | grep -o '[0-9.]*' || echo "0"
}

# Submit transaction
submit_transaction() {
    local from_wallet="$1"
    local to_address="$2"
    local amount="$3"
    
    ${CLI_PATH} wallet send --from "${from_wallet}" --to "${to_address}" --amount "${amount}" --password "${STRESS_WALLET_PASSWORD}" --yes >> "${LOG_FILE}" 2>&1
}

# Monitor performance metrics
monitor_performance() {
    local start_time="$1"
    local transaction_count="$2"
    
    local end_time=$(date +%s)
    local duration=$((end_time - start_time))
    
    if [ $duration -gt 0 ]; then
        local tps=$(echo "scale=2; $transaction_count / $duration" | bc)
        log "Performance: ${transaction_count} transactions in ${duration}s = ${tps} TPS"
        
        if [ "$(echo "$tps < $TARGET_TPS" | bc)" -eq 1 ]; then
            log_warning "TPS below target: ${tps} < ${TARGET_TPS}"
        else
            log_success "TPS meets target: ${tps} >= ${TARGET_TPS}"
        fi
    fi
}

# Check RPC health on all nodes
check_rpc_health() {
    local healthy_nodes=0
    
    for node_config in "${NODES[@]}"; do
        IFS=':' read -r node_name node_ip <<< "$node_config"
        
        if curl -f -s --max-time 5 "http://${node_ip}:${RPC_PORT}/health" > /dev/null 2>&1; then
            ((healthy_nodes++))
        fi
    done
    
    log "Healthy RPC nodes: ${healthy_nodes} / 3"
    return $((3 - healthy_nodes))
}

# Get block heights from all nodes
get_block_heights() {
    local heights=()
    
    for node_config in "${NODES[@]}"; do
        IFS=':' read -r node_name node_ip <<< "$node_config"
        
        local height=$(curl -s --max-time 5 "http://${node_ip}:${RPC_PORT}/rpc/head" 2>/dev/null | grep -o '"height":[0-9]*' | grep -o '[0-9]*' || echo "0")
        heights+=("${node_name}:${height}")
    done
    
    echo "${heights[@]}"
}

# Verify consensus under load
verify_consensus() {
    local heights=("$@")
    
    local first_height=$(echo "${heights[0]}" | cut -d':' -f2)
    local consistent=true
    
    for height_info in "${heights[@]}"; do
        local h=$(echo "$height_info" | cut -d':' -f2)
        if [ "$h" != "$first_height" ]; then
            consistent=false
            log_warning "Height mismatch under load: ${height_info}"
        fi
    done
    
    if [ "$consistent" = true ]; then
        log_success "Consensus maintained under load (all nodes at height ${first_height})"
        return 0
    else
        log_error "Consensus lost under load"
        return 1
    fi
}

# Clean up stress test wallet
cleanup_wallet() {
    log "Cleaning up stress test wallet: ${STRESS_WALLET_NAME}"
    ${CLI_PATH} wallet delete --name "${STRESS_WALLET_NAME}" --yes >> "${LOG_FILE}" 2>&1 || true
    log_success "Stress test wallet deleted"
}

# Main execution
main() {
    log "=== Multi-Node Stress Test Started ==="
    log "Configuration: ${TRANSACTION_COUNT} transactions, ${TRANSACTION_RATE} TPS target"
    
    # Create log directory if it doesn't exist
    mkdir -p "${LOG_DIR}"
    
    local total_failures=0
    
    # Check initial RPC health
    log "=== Checking initial RPC health ==="
    check_rpc_health || ((total_failures++))
    
    # Create stress test wallet
    if ! create_stress_wallet; then
        log_error "Failed to create stress test wallet"
        exit 1
    fi
    
    # Check wallet balance
    local balance=$(get_wallet_balance "${STRESS_WALLET_NAME}")
    log "Stress test wallet balance: ${balance}"
    
    if [ "$(echo "$balance < $TRANSACTION_COUNT" | bc)" -eq 1 ]; then
        log_warning "Insufficient balance for ${TRANSACTION_COUNT} transactions (have ${balance})"
        log "Reducing transaction count to ${balance%%.*}"
        TRANSACTION_COUNT=${balance%%.*}
    fi
    
    if [ "$TRANSACTION_COUNT" -lt 1 ]; then
        log_error "Insufficient balance for stress testing"
        cleanup_wallet
        exit 1
    fi
    
    # Get initial block heights
    log "=== Getting initial block heights ==="
    local initial_heights=($(get_block_heights))
    for height_info in "${initial_heights[@]}"; do
        log "Initial: ${height_info}"
    done
    
    # Generate transactions
    log "=== Generating ${TRANSACTION_COUNT} transactions ==="
    local start_time=$(date +%s)
    local successful_transactions=0
    local failed_transactions=0
    
    for i in $(seq 1 $TRANSACTION_COUNT); do
        local recipient="ait1zqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqz4vxy"
        local amount=1
        
        if submit_transaction "${STRESS_WALLET_NAME}" "${recipient}" "${amount}"; then
            ((successful_transactions++))
        else
            ((failed_transactions++))
            log_warning "Transaction ${i} failed"
        fi
        
        # Rate limiting
        if [ $((i % TRANSACTION_RATE)) -eq 0 ]; then
            sleep 1
        fi
    done
    
    local end_time=$(date +%s)
    
    log "Transaction generation completed: ${successful_transactions} successful, ${failed_transactions} failed"
    
    # Calculate error rate
    local error_rate=$(echo "scale=2; $failed_transactions * 100 / $TRANSACTION_COUNT" | bc)
    log "Error rate: ${error_rate}%"
    
    if [ "$(echo "$error_rate > $ERROR_RATE_THRESHOLD" | bc)" -eq 1 ]; then
        log_error "Error rate exceeds threshold: ${error_rate}% > ${ERROR_RATE_THRESHOLD}%"
        ((total_failures++))
    fi
    
    # Monitor performance
    monitor_performance "$start_time" "$successful_transactions"
    
    # Wait for transactions to be processed
    log "=== Waiting for transactions to be processed (30s) ==="
    sleep 30
    
    # Check RPC health after load
    log "=== Checking RPC health after load ==="
    check_rpc_health || ((total_failures++))
    
    # Verify consensus under load
    log "=== Verifying consensus after load ==="
    local final_heights=($(get_block_heights))
    for height_info in "${final_heights[@]}"; do
        log "Final: ${height_info}"
    done
    
    if ! verify_consensus "${final_heights[@]}"; then
        ((total_failures++))
    fi
    
    # Check if blocks increased
    local initial_first=$(echo "${initial_heights[0]}" | cut -d':' -f2)
    local final_first=$(echo "${final_heights[0]}" | cut -d':' -f2)
    local block_increase=$((final_first - initial_first))
    
    log "Block height increase: ${block_increase}"
    
    if [ $block_increase -lt 1 ]; then
        log_warning "No blocks produced during stress test"
    else
        log_success "${block_increase} blocks produced during stress test"
    fi
    
    # Clean up
    cleanup_wallet
    
    log "=== Multi-Node Stress Test Completed ==="
    log "Total failures: ${total_failures}"
    
    if [ ${total_failures} -eq 0 ]; then
        log_success "Multi-Node Stress Test passed"
        exit 0
    else
        log_error "Multi-Node Stress Test failed with ${total_failures} failures"
        exit 1
    fi
}

# Run main function
main "$@"
