#!/bin/bash
#
# Multi-Node Blockchain Health Check Script
# Checks health of all 3 blockchain nodes (aitbc, aitbc1, aitbc2)
# Provides automatic remediation for failed services
#

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
LOG_DIR="/var/log/aitbc"
LOG_FILE="${LOG_DIR}/multi-node-health.log"

# Node Configuration
NODES=(
    "aitbc:10.1.223.93"
    "aitbc1:10.1.223.40"
    "aitbc2:gitea-runner"
)

RPC_PORT=8006
REDIS_HOST="10.1.223.93"
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

# Check RPC endpoint health
check_rpc_health() {
    local node_name="$1"
    local node_ip="$2"
    local chain_id="${3:-}"

    if [ -n "$chain_id" ]; then
        log "Checking RPC health for ${node_name} (${node_ip}:${RPC_PORT}) on chain ${chain_id}"
        local url="http://${node_ip}:${RPC_PORT}/rpc/head?chain_id=${chain_id}"
    else
        log "Checking RPC health for ${node_name} (${node_ip}:${RPC_PORT})"
        local url="http://${node_ip}:${RPC_PORT}/health"
    fi

    if curl -f -s --max-time 5 "$url" > /dev/null 2>&1; then
        log_success "RPC endpoint healthy on ${node_name}${chain_id:+ (chain: ${chain_id})}"
        return 0
    else
        log_error "RPC endpoint unhealthy on ${node_name}${chain_id:+ (chain: ${chain_id})}"
        return 1
    fi
}

# Check systemd service status (RPC-based only, no SSH)
check_service_status() {
    local node_name="$1"
    local node_ip="$2"
    local service="$3"
    
    # Skip SSH-based service checks - use RPC health instead
    log "Skipping SSH-based service check for ${service} on ${node_name} (using RPC health instead)"
    return 0
}

# Check resource usage (RPC-based only, no SSH)
check_resource_usage() {
    local node_name="$1"
    local node_ip="$2"
    
    # Skip SSH-based resource checks
    log "Skipping SSH-based resource usage check for ${node_name} (not supported without SSH)"
    return 0
}

# Check Redis connectivity
check_redis_connectivity() {
    log "Checking Redis connectivity (${REDIS_HOST}:${REDIS_PORT})"
    
    if redis-cli -h "${REDIS_HOST}" -p "${REDIS_PORT}" ping > /dev/null 2>&1; then
        log_success "Redis connectivity OK"
        return 0
    else
        log_error "Redis connectivity failed"
        return 1
    fi
}

# Main health check for a node (RPC-based only)
check_node_health() {
    local node_name="$1"
    local node_ip="$2"

    local failures=0

    # Check RPC health for each chain
    IFS=',' read -ra CHAIN_ARRAY <<< "$CHAINS"
    for chain in "${CHAIN_ARRAY[@]}"; do
        chain=$(echo "$chain" | xargs)  # Trim whitespace
        if ! check_rpc_health "$node_name" "$node_ip" "$chain"; then
            ((failures++))
            log_error "RPC endpoint unhealthy on ${node_name} for chain ${chain}"
        fi
    done

    # Skip SSH-based service and resource checks
    log "Skipping SSH-based checks for ${node_name} (RPC health only mode)"

    return $failures
}

# Main execution
main() {
    log "=== Multi-Node Blockchain Health Check Started ==="
    
    # Create log directory if it doesn't exist
    mkdir -p "${LOG_DIR}"
    
    local total_failures=0
    
    # Check Redis connectivity (shared resource)
    if ! check_redis_connectivity; then
        log_error "Redis connectivity failed - this affects all nodes"
        ((total_failures++))
    fi
    
    # Check each node
    for node_config in "${NODES[@]}"; do
        IFS=':' read -r node_name node_ip <<< "$node_config"
        
        log "=== Checking node: ${node_name} (${node_ip}) ==="
        
        if check_node_health "$node_name" "$node_ip"; then
            log_success "Node ${node_name} is healthy"
        else
            failures=$?
            log_error "Node ${node_name} has ${failures} health issues"
            ((total_failures+=failures))
        fi
        
        echo "" | tee -a "${LOG_FILE}"
    done
    
    log "=== Multi-Node Blockchain Health Check Completed ==="
    log "Total failures: ${total_failures}"
    
    if [ ${total_failures} -eq 0 ]; then
        log_success "All nodes are healthy"
        exit 0
    else
        log_error "Health check completed with ${total_failures} failures"
        exit 1
    fi
}

# Run main function
main "$@"
