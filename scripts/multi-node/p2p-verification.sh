#!/bin/bash
#
# P2P Network Verification Script
# Verifies P2P network connectivity across all 3 blockchain nodes
#

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
LOG_DIR="/var/log/aitbc"
LOG_FILE="${LOG_DIR}/p2p-verification.log"

# Node Configuration
NODES=(
    "aitbc:10.1.223.93"
    "aitbc1:10.1.223.40"
    "aitbc2:10.1.223.98"
)

P2P_PORT=7070
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
    ssh -o ConnectTimeout=10 -o StrictHostKeyChecking=no "$node" "$command" 2>&1 || return 1
}

# Check P2P peer list on a node
check_p2p_peers() {
    local node="$1"
    local node_name="$2"
    
    log "Checking P2P peers on ${node_name}"
    
    # Read node.env to get expected peers
    peers=$(ssh_exec "$node" "grep '^p2p_peers=' /etc/aitbc/node.env | cut -d'=' -f2" 2>&1 || echo "")
    
    if [ -z "$peers" ]; then
        log_error "No p2p_peers configured on ${node_name}"
        return 1
    fi
    
    log "Expected peers on ${node_name}: ${peers}"
    
    # Check P2P service status
    if ! ssh_exec "$node" "systemctl is-active aitbc-blockchain-p2p" | grep -q "active"; then
        log_error "P2P service not active on ${node_name}"
        return 1
    fi
    
    log_success "P2P peers configured on ${node_name}"
    return 0
}

# Check P2P connectivity between nodes
check_p2p_connectivity() {
    local source_node="$1"
    local source_name="$2"
    local target_node="$3"
    local target_name="$4"
    
    log "Checking P2P connectivity from ${source_name} to ${target_name}"
    
    # Try to connect to target P2P port
    if ssh_exec "$source_node" "timeout 5 bash -c '</dev/tcp/${target_node#*:}/${P2P_PORT}'" 2>&1; then
        log_success "P2P connectivity OK from ${source_name} to ${target_name}"
        return 0
    else
        log_error "P2P connectivity FAILED from ${source_name} to ${target_name}"
        return 1
    fi
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

# Check for P2P handshake errors in logs
check_p2p_logs() {
    local node="$1"
    local node_name="$2"
    
    log "Checking P2P logs for errors on ${node_name}"
    
    # Check for handshake errors
    errors=$(ssh_exec "$node" "journalctl -u aitbc-blockchain-p2p --since '1 hour ago' | grep -i 'handshake\|error\|failed' | tail -5" 2>&1 || echo "")
    
    if [ -n "$errors" ]; then
        log_warning "P2P errors found on ${node_name}:"
        echo "$errors" | tee -a "${LOG_FILE}"
        return 1
    else
        log_success "No P2P errors found on ${node_name}"
        return 0
    fi
}

# Remediation: Restart P2P service
remediate_p2p_service() {
    local node="$1"
    local node_name="$2"
    
    log "Attempting P2P remediation on ${node_name}"
    
    ssh_exec "$node" "systemctl restart aitbc-blockchain-p2p" 2>&1 | tee -a "${LOG_FILE}"
    sleep 5
    
    if ssh_exec "$node" "systemctl is-active aitbc-blockchain-p2p" | grep -q "active"; then
        log_success "P2P service remediation successful on ${node_name}"
        return 0
    else
        log_error "P2P service remediation failed on ${node_name}"
        return 1
    fi
}

# Update p2p_peers configuration if needed
update_p2p_peers() {
    local node="$1"
    local node_name="$2"
    
    log "Updating p2p_peers configuration on ${node_name}"
    
    # Determine correct peers based on node name
    case "$node_name" in
        "aitbc")
            peers="aitbc1:7070,aitbc2:7070"
            ;;
        "aitbc1")
            peers="aitbc:7070,aitbc2:7070"
            ;;
        "aitbc2")
            peers="aitbc:7070,aitbc1:7070"
            ;;
        *)
            log_error "Unknown node name: ${node_name}"
            return 1
            ;;
    esac
    
    # Update node.env
    ssh_exec "$node" "sed -i 's/^p2p_peers=.*/p2p_peers=${peers}/' /etc/aitbc/node.env" 2>&1 | tee -a "${LOG_FILE}"
    
    # Restart P2P service to apply changes
    ssh_exec "$node" "systemctl restart aitbc-blockchain-p2p" 2>&1 | tee -a "${LOG_FILE}"
    sleep 5
    
    log_success "Updated p2p_peers on ${node_name} to: ${peers}"
    return 0
}

# Main verification for a node
verify_node_p2p() {
    local node_name="$1"
    local node_ip="$2"
    local node="${node_name}"
    
    local failures=0
    
    # Check P2P peers configuration
    if ! check_p2p_peers "$node" "$node_name"; then
        ((failures++))
        log "Attempting remediation for P2P peers on ${node_name}"
        update_p2p_peers "$node" "$node_name" || true
    fi
    
    # Check P2P logs for errors
    if ! check_p2p_logs "$node" "$node_name"; then
        ((failures++))
        log "Attempting remediation for P2P errors on ${node_name}"
        remediate_p2p_service "$node" "$node_name" || true
    fi
    
    return $failures
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
    
    # Check each node's P2P configuration
    for node_config in "${NODES[@]}"; do
        IFS=':' read -r node_name node_ip <<< "$node_config"
        
        log "=== Verifying P2P on node: ${node_name} (${node_ip}) ==="
        
        if verify_node_p2p "$node_name" "$node_ip"; then
            log_success "P2P verification passed for ${node_name}"
        else
            failures=$?
            log_error "P2P verification failed for ${node_name} with ${failures} issues"
            ((total_failures+=failures))
        fi
        
        echo "" | tee -a "${LOG_FILE}"
    done
    
    # Check P2P connectivity between all node pairs
    log "=== Checking P2P connectivity between node pairs ==="
    
    for source_config in "${NODES[@]}"; do
        IFS=':' read -r source_name source_ip <<< "$source_config"
        
        for target_config in "${NODES[@]}"; do
            IFS=':' read -r target_name target_ip <<< "$target_config"
            
            # Skip self-connectivity check
            if [ "$source_name" = "$target_name" ]; then
                continue
            fi
            
            if ! check_p2p_connectivity "$source_name" "$source_name" "$target_ip" "$target_name"; then
                ((total_failures++))
                log "Attempting remediation for P2P connectivity"
                remediate_p2p_service "$source_name" "$source_name" || true
            fi
        done
    done
    
    log "=== P2P Network Verification Completed ==="
    log "Total failures: ${total_failures}"
    
    if [ ${total_failures} -eq 0 ]; then
        log_success "P2P network verification passed"
        exit 0
    else
        log_error "P2P network verification failed with ${total_failures} failures"
        exit 1
    fi
}

# Run main function
main "$@"
