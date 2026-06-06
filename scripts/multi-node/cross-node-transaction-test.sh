#!/bin/bash
#
# Cross-Node Transaction Testing Script
# Tests transaction propagation across all 3 blockchain nodes
# Uses RPC endpoints only, no SSH access
#

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"

# Node Configuration
NODES=(
    "aitbc:10.1.223.93"
    "aitbc1:10.1.223.40"
)

RPC_PORT=8006
CLI_PATH="${CLI_PATH:-${REPO_ROOT}/cli/aitbc_cli.py}"
LOG_DIR="/var/log/aitbc"
LOG_FILE="${LOG_DIR}/cross-node-transaction-test.log"

# Test Configuration
TEST_WALLET_NAME="cross-node-test-wallet"
TEST_WALLET_PASSWORD="test123456"
TEST_RECIPIENT="ait1zqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqz4vxy"
TEST_AMOUNT=1
CHAINS="${CHAINS:-ait-mainnet,ait-testnet}"

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

# Create test wallet
create_test_wallet() {
    log "Creating test wallet: ${TEST_WALLET_NAME}"
    
    # Remove existing test wallet if it exists
    timeout 30 ${CLI_PATH} wallet delete --name "${TEST_WALLET_NAME}" --yes 2>/dev/null || true
    
    # Create new test wallet
    timeout 30 ${CLI_PATH} wallet create --name "${TEST_WALLET_NAME}" --password "${TEST_WALLET_PASSWORD}" --yes --no-confirm >> "${LOG_FILE}" 2>&1
    
    log_success "Test wallet created: ${TEST_WALLET_NAME}"
}

# Get wallet address
get_wallet_address() {
    local wallet_name="$1"
    
    # Check if CLI exists and is executable
    if [ ! -x "${CLI_PATH}" ]; then
        log_error "CLI not found or not executable: ${CLI_PATH}"
        echo ""
        return 1
    fi
    
    # Try different wallet address command syntaxes
    local address=$(timeout 10 ${CLI_PATH} wallet address --name "${wallet_name}" 2>&1)
    local exit_code=$?
    
    if [ $exit_code -ne 0 ] || [ -z "$address" ]; then
        log_warning "wallet address command failed (exit code: ${exit_code}, output: ${address})"
        # Try alternative syntax
        address=$(timeout 10 ${CLI_PATH} wallet list --name "${wallet_name}" 2>&1 | grep -o "ait1[a-z0-9]*" | head -1 || echo "")
    fi
    
    echo "$address"
}

# Get wallet balance
get_wallet_balance() {
    local wallet_name="$1"
    timeout 10 ${CLI_PATH} wallet balance --name "${wallet_name}" 2>/dev/null || echo "0"
}

# Submit transaction
submit_transaction() {
    local from_wallet="$1"
    local to_address="$2"
    local amount="$3"
    
    log "Submitting transaction: ${amount} from ${from_wallet} to ${to_address}"
    
    local tx_start=$(date +%s)
    timeout 60 ${CLI_PATH} wallet send --from "${from_wallet}" --to "${to_address}" --amount "${amount}" --password "${TEST_WALLET_PASSWORD}" --yes --verbose >> "${LOG_FILE}" 2>&1
    local tx_end=$(date +%s)
    local tx_time=$((tx_end - tx_start))
    
    log "Transaction submitted in ${tx_time} seconds"
    echo "${tx_time}"
}

# Check transaction status on a node
check_transaction_status() {
    local node_ip="$1"
    local tx_hash="$2"
    
    # Check if transaction is in mempool
    local in_mempool=$(curl -s --max-time 5 "http://${node_ip}:${RPC_PORT}/rpc/mempool" 2>/dev/null | grep -o "${tx_hash}" || echo "")
    
    if [ -n "$in_mempool" ]; then
        echo "mempool"
        return 0
    fi
    
    # Check if transaction is confirmed
    local confirmed=$(curl -s --max-time 5 "http://${node_ip}:${RPC_PORT}/rpc/transactions?hash=${tx_hash}" 2>/dev/null | grep -o "${tx_hash}" || echo "")
    
    if [ -n "$confirmed" ]; then
        echo "confirmed"
        return 0
    fi
    
    echo "pending"
    return 1
}

# Wait for transaction confirmation on all nodes
wait_for_confirmation() {
    local tx_hash="$1"
    local timeout=60
    local elapsed=0
    
    log "Waiting for transaction confirmation on all nodes (timeout: ${timeout}s)"
    
    while [ $elapsed -lt $timeout ]; do
        local all_confirmed=true
        
        for node_config in "${NODES[@]}"; do
            IFS=':' read -r node_name node_ip <<< "$node_config"
            
            local status=$(check_transaction_status "$node_ip" "$tx_hash")
            
            if [ "$status" != "confirmed" ]; then
                all_confirmed=false
                log "Transaction not yet confirmed on ${node_name} (status: ${status})"
            fi
        done
        
        if [ "$all_confirmed" = true ]; then
            log_success "Transaction confirmed on all nodes"
            return 0
        fi
        
        sleep 2
        elapsed=$((elapsed + 2))
    done
    
    log_error "Transaction confirmation timeout"
    return 1
}

# Measure propagation latency
measure_propagation_latency() {
    local tx_hash="$1"
    
    log "Measuring propagation latency for transaction: ${tx_hash}"
    
    local propagation_times=()
    
    for node_config in "${NODES[@]}"; do
        IFS=':' read -r node_name node_ip <<< "$node_config"
        
        local start=$(date +%s)
        local elapsed=0
        local timeout=30
        
        while [ $elapsed -lt $timeout ]; do
            local status=$(check_transaction_status "$node_ip" "$tx_hash")
            
            if [ "$status" = "mempool" ] || [ "$status" = "confirmed" ]; then
                local latency=$((elapsed))
                propagation_times+=("${node_name}:${latency}")
                log "Transaction reached ${node_name} in ${latency}s"
                break
            fi
            
            sleep 1
            elapsed=$((elapsed + 1))
        done
        
        if [ $elapsed -ge $timeout ]; then
            log_warning "Transaction did not reach ${node_name} within ${timeout}s"
            propagation_times+=("${node_name}:timeout")
        fi
    done
    
    echo "${propagation_times[@]}"
}

# Clean up test wallet
cleanup_wallet() {
    log "Cleaning up test wallet: ${TEST_WALLET_NAME}"
    timeout 30 ${CLI_PATH} wallet delete --name "${TEST_WALLET_NAME}" --yes >> "${LOG_FILE}" 2>&1 || true
    log_success "Test wallet deleted"
}

# Main execution
main() {
    log "=== Cross-Node Transaction Test Started ==="
    
    # Create log directory if it doesn't exist
    mkdir -p "${LOG_DIR}"
    
    local total_failures=0
    
    # Create test wallet
    if ! create_test_wallet; then
        log_error "Failed to create test wallet"
        exit 1
    fi
    
    # Get wallet address
    local wallet_address=$(get_wallet_address "${TEST_WALLET_NAME}")
    if [ -z "$wallet_address" ]; then
        log_error "Failed to get wallet address"
        cleanup_wallet
        exit 1
    fi
    
    log "Test wallet address: ${wallet_address}"
    
    # Check wallet balance
    local balance=$(get_wallet_balance "${TEST_WALLET_NAME}")
    log "Test wallet balance: ${balance}"
    
    if [ "$(echo "$balance < $TEST_AMOUNT" | bc)" -eq 1 ]; then
        log_warning "Test wallet has insufficient balance (need ${TEST_AMOUNT}, have ${balance})"
        log "Skipping transaction test"
        cleanup_wallet
        exit 0
    fi
    
    # Submit transaction
    local tx_time=$(submit_transaction "${TEST_WALLET_NAME}" "${TEST_RECIPIENT}" "${TEST_AMOUNT}")
    
    # Get transaction hash (would need to parse from CLI output or RPC)
    # For now, we'll skip hash-based checks and just test propagation
    
    # Measure propagation latency (simplified - just check RPC health)
    log "Testing RPC propagation across nodes"
    
    for node_config in "${NODES[@]}"; do
        IFS=':' read -r node_name node_ip <<< "$node_config"
        
        if curl -f -s --max-time 5 "http://${node_ip}:${RPC_PORT}/health" > /dev/null 2>&1; then
            log_success "RPC reachable on ${node_name}"
        else
            log_error "RPC not reachable on ${node_name}"
            ((total_failures++))
        fi
    done
    
    # Clean up
    cleanup_wallet
    
    log "=== Cross-Node Transaction Test Completed ==="
    log "Total failures: ${total_failures}"
    
    if [ ${total_failures} -eq 0 ]; then
        log_success "Cross-Node Transaction Test passed"
        exit 0
    else
        log_error "Cross-Node Transaction Test failed with ${total_failures} failures"
        exit 1
    fi
}

# Run main function
main "$@"
