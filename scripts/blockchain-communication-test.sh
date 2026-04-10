#!/bin/bash
#
# Blockchain Communication Test Script
# Tests communication between aitbc (genesis) and aitbc1 (follower) nodes
# Both nodes run on port 8006 on different physical machines
#

set -e

# Configuration
GENESIS_IP="10.1.223.40"
FOLLOWER_IP="<aitbc1-ip>"  # Replace with actual IP
PORT=8006
CLI_PATH="/opt/aitbc/aitbc-cli"
LOG_DIR="/var/log/aitbc"
LOG_FILE="${LOG_DIR}/blockchain-communication-test.log"
MONITOR_LOG="${LOG_DIR}/blockchain-monitor.log"
ERROR_LOG="${LOG_DIR}/blockchain-test-errors.log"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Parse command line arguments
TEST_TYPE="full"
DEBUG=false
MONITOR=false
INTERVAL=300
ALERT_EMAIL=""

while [[ $# -gt 0 ]]; do
    case $1 in
        --type)
            TEST_TYPE="$2"
            shift 2
            ;;
        --debug)
            DEBUG=true
            shift
            ;;
        --monitor)
            MONITOR=true
            shift
            ;;
        --interval)
            INTERVAL="$2"
            shift 2
            ;;
        --alert-email)
            ALERT_EMAIL="$2"
            shift 2
            ;;
        --full)
            TEST_TYPE="full"
            shift
            ;;
        *)
            echo "Unknown option: $1"
            exit 1
            ;;
    esac
done

# Logging functions
log() {
    local level="$1"
    shift
    local message="$@"
    local timestamp=$(date '+%Y-%m-%d %H:%M:%S')
    echo "[${timestamp}] [${level}] ${message}" | tee -a "${LOG_FILE}"
}

log_debug() {
    if [ "$DEBUG" = true ]; then
        log "DEBUG" "$@"
    fi
}

log_info() {
    log "INFO" "$@"
}

log_success() {
    log "SUCCESS" "$@"
    echo -e "${GREEN}$@${NC}"
}

log_error() {
    log "ERROR" "$@"
    echo -e "${RED}$@${NC}" >&2
    echo "[${timestamp}] [ERROR] $@" >> "${ERROR_LOG}"
}

log_warning() {
    log "WARNING" "$@"
    echo -e "${YELLOW}$@${NC}"
}

# Test functions
test_connectivity() {
    log_info "Testing connectivity between nodes..."
    
    # Test genesis node
    log_debug "Testing genesis node at ${GENESIS_IP}:${PORT}"
    if curl -f -s "http://${GENESIS_IP}:${PORT}/health" > /dev/null; then
        log_success "Genesis node (aitbc) is reachable"
    else
        log_error "Genesis node (aitbc) is NOT reachable"
        return 1
    fi
    
    # Test follower node
    log_debug "Testing follower node at ${FOLLOWER_IP}:${PORT}"
    if curl -f -s "http://${FOLLOWER_IP}:${PORT}/health" > /dev/null; then
        log_success "Follower node (aitbc1) is reachable"
    else
        log_error "Follower node (aitbc1) is NOT reachable"
        return 1
    fi
    
    # Test P2P connectivity
    log_debug "Testing P2P connectivity"
    if ${CLI_PATH} network ping --node aitbc1 --host ${FOLLOWER_IP} --port ${PORT} --debug > /dev/null 2>&1; then
        log_success "P2P connectivity between nodes is working"
    else
        log_warning "P2P connectivity test failed (may not be critical)"
    fi
    
    # Check peers
    log_debug "Checking peer list"
    ${CLI_PATH} network peers --verbose >> "${LOG_FILE}" 2>&1
    
    return 0
}

test_blockchain_status() {
    log_info "Testing blockchain status and synchronization..."
    
    # Get genesis node status
    log_debug "Getting genesis node blockchain info"
    GENESIS_HEIGHT=$(NODE_URL="http://${GENESIS_IP}:${PORT}" ${CLI_PATH} blockchain height --output json 2>/dev/null | grep -o '"height":[0-9]*' | grep -o '[0-9]*' || echo "0")
    log_info "Genesis node block height: ${GENESIS_HEIGHT}"
    
    # Get follower node status
    log_debug "Getting follower node blockchain info"
    FOLLOWER_HEIGHT=$(NODE_URL="http://${FOLLOWER_IP}:${PORT}" ${CLI_PATH} blockchain height --output json 2>/dev/null | grep -o '"height":[0-9]*' | grep -o '[0-9]*' || echo "0")
    log_info "Follower node block height: ${FOLLOWER_HEIGHT}"
    
    # Compare heights
    HEIGHT_DIFF=$((GENESIS_HEIGHT - FOLLOWER_HEIGHT))
    HEIGHT_DIFF=${HEIGHT_DIFF#-}  # Absolute value
    
    if [ ${HEIGHT_DIFF} -le 2 ]; then
        log_success "Block synchronization is good (diff: ${HEIGHT_DIFF} blocks)"
        return 0
    elif [ ${HEIGHT_DIFF} -le 10 ]; then
        log_warning "Block synchronization lag (diff: ${HEIGHT_DIFF} blocks)"
        return 1
    else
        log_error "Block synchronization severely lagged (diff: ${HEIGHT_DIFF} blocks)"
        return 1
    fi
}

test_transaction() {
    log_info "Testing transaction propagation..."
    
    # Create test wallets
    log_debug "Creating test wallets"
    ${CLI_PATH} wallet create --name test-comm-sender --password test123 --yes --no-confirm >> "${LOG_FILE}" 2>&1 || true
    ${CLI_PATH} wallet create --name test-comm-receiver --password test123 --yes --no-confirm >> "${LOG_FILE}" 2>&1 || true
    
    # Check if sender has balance
    SENDER_BALANCE=$(${CLI_PATH} wallet balance --name test-comm-sender --output json 2>/dev/null | grep -o '"balance":[0-9.]*' | grep -o '[0-9.]*' || echo "0")
    
    if [ $(echo "${SENDER_BALANCE} < 1" | bc) -eq 1 ]; then
        log_warning "Test sender wallet has insufficient balance, skipping transaction test"
        return 0
    fi
    
    # Send transaction
    log_debug "Sending test transaction"
    TX_START=$(date +%s)
    ${CLI_PATH} wallet send --from test-comm-sender --to test-comm-receiver --amount 1 --password test123 --yes --verbose >> "${LOG_FILE}" 2>&1
    TX_END=$(date +%s)
    TX_TIME=$((TX_END - TX_START))
    
    log_info "Transaction completed in ${TX_TIME} seconds"
    
    if [ ${TX_TIME} -le 30 ]; then
        log_success "Transaction propagation time is good (${TX_TIME}s)"
        return 0
    elif [ ${TX_TIME} -le 60 ]; then
        log_warning "Transaction propagation is slow (${TX_TIME}s)"
        return 1
    else
        log_error "Transaction propagation timeout (${TX_TIME}s)"
        return 1
    fi
}

test_agent_messaging() {
    log_info "Testing agent message propagation..."
    
    # This test requires existing agents
    log_debug "Checking for existing agents"
    AGENTS=$(${CLI_PATH} agent list --output json 2>/dev/null || echo "[]")
    
    if [ "${AGENTS}" = "[]" ]; then
        log_warning "No agents found, skipping agent messaging test"
        return 0
    fi
    
    # Get first agent ID
    AGENT_ID=$(echo "${AGENTS}" | grep -o '"id":"[^"]*"' | head -1 | grep -o ':[^:]*$' | tr -d '"' || echo "")
    
    if [ -z "${AGENT_ID}" ]; then
        log_warning "Could not get agent ID, skipping agent messaging test"
        return 0
    fi
    
    # Send test message
    log_debug "Sending test message to agent ${AGENT_ID}"
    MSG_START=$(date +%s)
    ${CLI_PATH} agent message --to ${AGENT_ID} --content "Blockchain communication test message" --debug >> "${LOG_FILE}" 2>&1
    MSG_END=$(date +%s)
    MSG_TIME=$((MSG_END - MSG_START))
    
    log_info "Agent message sent in ${MSG_TIME} seconds"
    
    if [ ${MSG_TIME} -le 10 ]; then
        log_success "Agent message propagation is good (${MSG_TIME}s)"
        return 0
    else
        log_warning "Agent message propagation is slow (${MSG_TIME}s)"
        return 1
    fi
}

test_sync() {
    log_info "Testing git-based synchronization..."
    
    # Check git status on genesis
    log_debug "Checking git status on genesis node"
    cd /opt/aitbc
    GENESIS_STATUS=$(git status --porcelain 2>/dev/null || echo "error")
    
    if [ "${GENESIS_STATUS}" = "error" ]; then
        log_error "Git status check failed on genesis node"
        return 1
    elif [ -z "${GENESIS_STATUS}" ]; then
        log_success "Genesis node git status is clean"
    else
        log_warning "Genesis node has uncommitted changes"
    fi
    
    # Check git status on follower
    log_debug "Checking git status on follower node"
    FOLLOWER_STATUS=$(ssh aitbc1 'cd /opt/aitbc && git status --porcelain 2>/dev/null' || echo "error")
    
    if [ "${FOLLOWER_STATUS}" = "error" ]; then
        log_error "Git status check failed on follower node"
        return 1
    elif [ -z "${FOLLOWER_STATUS}" ]; then
        log_success "Follower node git status is clean"
    else
        log_warning "Follower node has uncommitted changes"
    fi
    
    # Test git pull
    log_debug "Testing git pull from Gitea"
    git pull origin main --verbose >> "${LOG_FILE}" 2>&1
    ssh aitbc1 'cd /opt/aitbc && git pull origin main --verbose' >> "${LOG_FILE}" 2>&1
    
    log_success "Git synchronization test completed"
    return 0
}

# Main test runner
run_test() {
    local test_name="$1"
    local test_func="$2"
    
    log_info "Running: ${test_name}"
    if ${test_func}; then
        log_success "${test_name} PASSED"
        return 0
    else
        log_error "${test_name} FAILED"
        return 1
    fi
}

# Full test suite
run_full_test() {
    log_info "Starting full blockchain communication test suite"
    
    local failed_tests=0
    
    run_test "Connectivity Test" test_connectivity || ((failed_tests++))
    run_test "Blockchain Status Test" test_blockchain_status || ((failed_tests++))
    run_test "Transaction Test" test_transaction || ((failed_tests++))
    run_test "Agent Messaging Test" test_agent_messaging || ((failed_tests++))
    run_test "Synchronization Test" test_sync || ((failed_tests++))
    
    log_info "Test suite completed with ${failed_tests} failures"
    
    if [ ${failed_tests} -eq 0 ]; then
        log_success "All tests PASSED"
        return 0
    else
        log_error "${failed_tests} test(s) FAILED"
        return 1
    fi
}

# Monitor mode
run_monitor() {
    log_info "Starting continuous monitoring (interval: ${INTERVAL}s)"
    
    while true; do
        log_info "=== Monitoring cycle started at $(date) ==="
        
        if run_full_test; then
            log_info "Monitoring cycle: All checks passed"
        else
            log_error "Monitoring cycle: Some checks failed"
            
            # Send alert if configured
            if [ -n "${ALERT_EMAIL}" ]; then
                echo "Blockchain communication test failed. Check logs at ${LOG_FILE}" | mail -s "AITBC Blockchain Test Alert" ${ALERT_EMAIL} 2>/dev/null || true
            fi
        fi
        
        log_info "=== Monitoring cycle completed ==="
        echo "" >> "${MONITOR_LOG}"
        
        sleep ${INTERVAL}
    done
}

# Main execution
main() {
    log_info "Blockchain Communication Test Script"
    log_info "Genesis IP: ${GENESIS_IP}, Follower IP: ${FOLLOWER_IP}, Port: ${PORT}"
    
    # Create log directory if it doesn't exist
    mkdir -p "${LOG_DIR}"
    
    if [ "$MONITOR" = true ]; then
        run_monitor
    else
        case "${TEST_TYPE}" in
            connectivity)
                run_test "Connectivity Test" test_connectivity
                ;;
            blockchain)
                run_test "Blockchain Status Test" test_blockchain_status
                ;;
            transaction)
                run_test "Transaction Test" test_transaction
                ;;
            sync)
                run_test "Synchronization Test" test_sync
                ;;
            full)
                run_full_test
                ;;
            *)
                log_error "Unknown test type: ${TEST_TYPE}"
                exit 1
                ;;
        esac
    fi
}

# Run main function
main
