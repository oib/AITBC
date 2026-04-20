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
    "aitbc2:10.1.223.98"
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

# SSH execution helper
ssh_exec() {
    local node="$1"
    local command="$2"
    
    # Get local IP address
    local local_ip=$(hostname -I | awk '{print $1}')
    
    # If node is localhost or local IP, execute directly without SSH
    if [ "$node" = "localhost" ] || [ "$node" = "$(hostname)" ] || [ "$node" = "$local_ip" ]; then
        bash -c "$command" 2>&1 || return 1
    else
        ssh -o ConnectTimeout=10 -o StrictHostKeyChecking=no "$node" "$command" 2>&1 || return 1
    fi
}

# Check RPC endpoint health
check_rpc_health() {
    local node_name="$1"
    local node_ip="$2"
    
    log "Checking RPC health for ${node_name} (${node_ip}:${RPC_PORT})"
    
    if curl -f -s --max-time 5 "http://${node_ip}:${RPC_PORT}/health" > /dev/null 2>&1; then
        log_success "RPC endpoint healthy on ${node_name}"
        return 0
    else
        log_error "RPC endpoint unhealthy on ${node_name}"
        return 1
    fi
}

# Check systemd service status
check_service_status() {
    local node="$1"
    local service="$2"
    
    log "Checking ${service} status on ${node}"
    
    status=$(ssh_exec "$node" "systemctl is-active ${service}" 2>&1 || echo "inactive")
    
    if [ "$status" = "active" ]; then
        log_success "${service} is active on ${node}"
        return 0
    else
        log_error "${service} is ${status} on ${node}"
        return 1
    fi
}

# Check resource usage
check_resource_usage() {
    local node="$1"
    
    log "Checking resource usage on ${node}"
    
    memory=$(ssh_exec "$node" "free | grep Mem | awk '{printf \"%.1f\", (\$3/\$2)*100}'" 2>&1 || echo "0")
    cpu=$(ssh_exec "$node" "top -bn1 | grep 'Cpu(s)' | awk '{print \$2}' | cut -d'%' -f1" 2>&1 || echo "0")
    disk=$(ssh_exec "$node" "df /var/lib/aitbc | tail -1 | awk '{print \$5}' | cut -d'%' -f1" 2>&1 || echo "0")
    
    log "Resource usage on ${node}: CPU ${cpu}%, Memory ${memory}%, Disk ${disk}%"
    
    # Check thresholds
    if [ "${disk%.*}" -gt 90 ]; then
        log_warning "Disk usage critical on ${node}: ${disk}%"
        return 1
    fi
    
    if [ "${memory%.*}" -gt 90 ]; then
        log_warning "Memory usage critical on ${node}: ${memory}%"
        return 1
    fi
    
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

# Remediation functions
restart_rpc_service() {
    local node="$1"
    log "Attempting to restart aitbc-blockchain-rpc on ${node}"
    
    ssh_exec "$node" "systemctl restart aitbc-blockchain-rpc" 2>&1 | tee -a "${LOG_FILE}"
    sleep 5
    
    if ssh_exec "$node" "systemctl is-active aitbc-blockchain-rpc" 2>&1 | grep -q "active"; then
        log_success "Successfully restarted aitbc-blockchain-rpc on ${node}"
        return 0
    else
        log_error "Failed to restart aitbc-blockchain-rpc on ${node}"
        return 1
    fi
}

restart_p2p_service() {
    local node="$1"
    log "Attempting to restart aitbc-blockchain-p2p on ${node}"
    
    ssh_exec "$node" "systemctl restart aitbc-blockchain-p2p" 2>&1 | tee -a "${LOG_FILE}"
    sleep 5
    
    if ssh_exec "$node" "systemctl is-active aitbc-blockchain-p2p" 2>&1 | grep -q "active"; then
        log_success "Successfully restarted aitbc-blockchain-p2p on ${node}"
        return 0
    else
        log_error "Failed to restart aitbc-blockchain-p2p on ${node}"
        return 1
    fi
}

restart_node_service() {
    local node="$1"
    log "Attempting to restart aitbc-blockchain-node on ${node}"
    
    ssh_exec "$node" "systemctl restart aitbc-blockchain-node" 2>&1 | tee -a "${LOG_FILE}"
    sleep 10
    
    if ssh_exec "$node" "systemctl is-active aitbc-blockchain-node" 2>&1 | grep -q "active"; then
        log_success "Successfully restarted aitbc-blockchain-node on ${node}"
        return 0
    else
        log_error "Failed to restart aitbc-blockchain-node on ${node}"
        return 1
    fi
}

# Main health check for a node
check_node_health() {
    local node_name="$1"
    local node_ip="$2"
    local node="${node_name}"
    
    local failures=0
    
    # Check RPC health
    if ! check_rpc_health "$node_name" "$node_ip"; then
        ((failures++))
        log "Attempting remediation for RPC on ${node_name}"
        if restart_rpc_service "$node"; then
            # Retry RPC check
            if ! check_rpc_health "$node_name" "$node_ip"; then
                log_error "RPC remediation failed on ${node_name}"
            else
                log_success "RPC remediation successful on ${node_name}"
                ((failures--))
            fi
        fi
    fi
    
    # Check blockchain node service
    if ! check_service_status "$node" "aitbc-blockchain-node"; then
        ((failures++))
        log "Attempting remediation for blockchain node on ${node_name}"
        if restart_node_service "$node"; then
            # Retry service check
            if check_service_status "$node" "aitbc-blockchain-node"; then
                log_success "Blockchain node remediation successful on ${node_name}"
                ((failures--))
            fi
        fi
    fi
    
    # Check P2P service
    if ! check_service_status "$node" "aitbc-blockchain-p2p"; then
        ((failures++))
        log "Attempting remediation for P2P on ${node_name}"
        if restart_p2p_service "$node"; then
            # Retry service check
            if check_service_status "$node" "aitbc-blockchain-p2p"; then
                log_success "P2P remediation successful on ${node_name}"
                ((failures--))
            fi
        fi
    fi
    
    # Check resource usage
    if ! check_resource_usage "$node"; then
        ((failures++))
        log_warning "Resource usage issues on ${node_name}"
    fi
    
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
