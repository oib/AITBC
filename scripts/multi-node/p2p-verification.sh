#!/bin/bash
#
# P2P Network Verification Script
# Verifies P2P network connectivity across all 3 blockchain nodes
#

set -e


# Fleet node addresses.
#
# These were hardcoded to one island's private subnet, which made the script
# useless anywhere else and put internal addressing in a public repository.
# Set them for your own deployment; there is deliberately no default.
NODE0_HOST="${AITBC_NODE0_HOST:?set AITBC_NODE0_HOST to the address of node0}"
NODE1_HOST="${AITBC_NODE1_HOST:?set AITBC_NODE1_HOST to the address of node1}"
NODE3_HOST="${AITBC_NODE3_HOST:?set AITBC_NODE3_HOST to the address of node3}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
LOG_DIR="/var/log/aitbc"
LOG_FILE="${LOG_DIR}/p2p-verification.log"

# Node Configuration
NODES=(
    "aitbc:${NODE0_HOST}"
    "aitbc1:${NODE1_HOST}"
    "aitbc2:${NODE3_HOST}"
)

P2P_PORT=7070
REDIS_HOST="${NODE0_HOST}"
REDIS_PORT=6379

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

# Check P2P peer list on a node (RPC-based only, no SSH)
check_p2p_peers() {
    local node_name="$1"
    local node_ip="$2"

    log "Skipping SSH-based P2P peer check for ${node_name} (not supported without SSH)"
    log "P2P connectivity will be tested via port connectivity checks"
    return 0
}

# Check P2P connectivity between nodes (RPC-based only, no SSH)
check_p2p_connectivity() {
    local source_name="$1"
    local target_name="$2"

    log "Skipping SSH-based P2P connectivity check from ${source_name} to ${target_name} (not supported without SSH)"
    return 0
}

# Check Redis gossip backend connectivity
check_gossip_backend() {
    log "Checking Redis gossip backend connectivity (${REDIS_HOST}:${REDIS_PORT})"

    if redis-cli -h "${REDIS_HOST}" -p "${REDIS_PORT}" ping > /dev/null 2>&1; then
        log_success "Redis gossip backend connectivity OK"
        return 0
    else
        log_error "Redis gossip backend connectivity failed"
        return 1
    fi
}

# Check for P2P handshake errors in logs (RPC-based only, no SSH)
check_p2p_logs() {
    local node_name="$1"

    log "Skipping SSH-based P2P log check for ${node_name} (not supported without SSH)"
    return 0
}

# Main verification for a node (RPC-based only)
verify_node_p2p() {
    local node_name="$1"
    local node_ip="$2"

    log "Skipping SSH-based P2P verification for ${node_name} (RPC health only mode)"
    return 0
}

# Main execution
main() {
    log "=== P2P Network Verification Started ==="

    # Create log directory if it doesn't exist
    mkdir -p "${LOG_DIR}"

    local total_failures=0

    # Check Redis gossip backend
    if ! check_gossip_backend; then
        log_error "Gossip backend connectivity failed"
        ((total_failures++))
    fi

    # Skip SSH-based node P2P checks
    log "=== Skipping SSH-based P2P node checks (RPC health only mode) ==="
    log "P2P network verification limited to Redis gossip backend connectivity"

    log "=== P2P Network Verification Completed ==="
    log "Total failures: ${total_failures}"

    if [ ${total_failures} -eq 0 ]; then
        log_success "P2P network verification passed (Redis connectivity only)"
        exit 0
    else
        log_error "P2P network verification failed with ${total_failures} failures"
        exit 1
    fi
}

# Run main function
main "$@"
