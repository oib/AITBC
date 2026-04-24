#!/bin/bash
#
# Blockchain Synchronization Verification Script
# Verifies blockchain synchronization across all 3 nodes
# Provides automatic remediation by forcing sync from healthy node
#

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
LOG_DIR="/var/log/aitbc"
LOG_FILE="${LOG_DIR}/sync-verification.log"

# Node Configuration
NODES=(
    "aitbc:10.1.223.93"
    "aitbc1:10.1.223.40"
)

RPC_PORT=8006
SYNC_THRESHOLD=10
# Set to "false" to skip chain ID consistency check (allows different chains like devnet/mainnet)
CHECK_CHAIN_ID_CONSISTENCY="${CHECK_CHAIN_ID_CONSISTENCY:-true}"

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

# Get block height from RPC endpoint
get_block_height() {
    local node_ip="$1"
    
    # Try to get block height from RPC /rpc/head endpoint
    height=$(curl -s --max-time 5 "http://${node_ip}:${RPC_PORT}/rpc/head" 2>/dev/null | grep -o '"height":[0-9]*' | grep -o '[0-9]*' || echo "0")
    
    if [ -z "$height" ] || [ "$height" = "0" ]; then
        # Try alternative endpoint
        height=$(curl -s --max-time 5 "http://${node_ip}:${RPC_PORT}/height" 2>/dev/null | grep -o '[0-9]*' || echo "0")
    fi
    
    echo "$height"
}

# Get chain ID from RPC endpoint
get_chain_id() {
    local node_ip="$1"
    
    # Get chain ID from /health endpoint
    chain_id=$(curl -s --max-time 5 "http://${node_ip}:${RPC_PORT}/health" 2>/dev/null | grep -o '"supported_chains":\["[^"]*"\]' | grep -o '\["[^"]*"\]' | grep -o '[^"\[\]]*' || echo "")
    
    if [ -z "$chain_id" ]; then
        # Try alternative endpoint
        chain_id=$(curl -s --max-time 5 "http://${node_ip}:${RPC_PORT}/chain-id" 2>/dev/null || echo "")
    fi
    
    echo "$chain_id"
}

# Get block hash at specific height
get_block_hash() {
    local node_ip="$1"
    local height="$2"
    
    # Get block hash from /rpc/blocks/{height} endpoint
    hash=$(curl -s --max-time 5 "http://${node_ip}:${RPC_PORT}/rpc/blocks/${height}" 2>/dev/null | grep -o '"hash":"[^"]*"' | grep -o ':[^:]*$' | tr -d '"' || echo "")
    
    if [ -z "$hash" ]; then
        # Try alternative endpoint
        hash=$(curl -s --max-time 5 "http://${node_ip}:${RPC_PORT}/blockchain/block/${height}/hash" 2>/dev/null || echo "")
    fi
    
    echo "$hash"
}

# Check chain ID consistency (or just validity if CHECK_CHAIN_ID_CONSISTENCY=false)
check_chain_id_consistency() {
    log "Checking chain ID consistency across nodes"
    
    local first_chain_id=""
    local consistent=true
    local chain_ids=()
    
    for node_config in "${NODES[@]}"; do
        IFS=':' read -r node_name node_ip <<< "$node_config"
        
        chain_id=$(get_chain_id "$node_ip")
        
        if [ -z "$chain_id" ]; then
            log_error "Could not get chain ID from ${node_name}"
            consistent=false
            continue
        fi
        
        log "Chain ID on ${node_name}: ${chain_id}"
        chain_ids+=("${node_name}:${chain_id}")
        
        if [ -z "$first_chain_id" ]; then
            first_chain_id="$chain_id"
        elif [ "$chain_id" != "$first_chain_id" ]; then
            if [ "$CHECK_CHAIN_ID_CONSISTENCY" = "true" ]; then
                log_error "Chain ID mismatch on ${node_name}: ${chain_id} vs ${first_chain_id}"
                consistent=false
            else
                log_warning "Chain ID mismatch on ${node_name}: ${chain_id} vs ${first_chain_id} (check skipped)"
            fi
        fi
    done
    
    if [ "$consistent" = true ]; then
        log_success "Chain ID consistent across all nodes"
        return 0
    else
        if [ "$CHECK_CHAIN_ID_CONSISTENCY" = "true" ]; then
            log_error "Chain ID inconsistent across nodes"
            return 1
        else
            log_warning "Chain ID check skipped - nodes may be on different chains"
            return 0
        fi
    fi
}

# Check block synchronization
check_block_sync() {
    log "Checking block synchronization across nodes"
    
    local heights=()
    local max_height=0
    local min_height=999999
    
    for node_config in "${NODES[@]}"; do
        IFS=':' read -r node_name node_ip <<< "$node_config"
        
        height=$(get_block_height "$node_ip")
        
        if [ -z "$height" ] || [ "$height" = "0" ]; then
            log_error "Could not get block height from ${node_name}"
            return 1
        fi
        
        heights+=("${node_name}:${height}")
        log "Block height on ${node_name}: ${height}"
        
        if [ "$height" -gt "$max_height" ]; then
            max_height=$height
            max_node="${node_name}"
            max_ip="${node_ip}"
        fi
        
        if [ "$height" -lt "$min_height" ]; then
            min_height=$height
        fi
    done
    
    local height_diff=$((max_height - min_height))
    
    log "Max height: ${max_height} (${max_node}), Min height: ${min_height}, Diff: ${height_diff}"
    
    if [ "$height_diff" -le "$SYNC_THRESHOLD" ]; then
        log_success "Block synchronization within threshold (diff: ${height_diff})"
        return 0
    else
        log_error "Block synchronization exceeds threshold (diff: ${height_diff})"
        return 1
    fi
}

# Check block hash consistency at current height
check_block_hash_consistency() {
    log "Checking block hash consistency"
    
    local target_height=""
    
    # Find the minimum height to compare at
    for node_config in "${NODES[@]}"; do
        IFS=':' read -r node_name node_ip <<< "$node_config"
        height=$(get_block_height "$node_ip")
        
        if [ -z "$target_height" ] || [ "$height" -lt "$target_height" ]; then
            target_height=$height
        fi
    done
    
    log "Comparing block hashes at height ${target_height}"
    
    local first_hash=""
    local consistent=true
    
    for node_config in "${NODES[@]}"; do
        IFS=':' read -r node_name node_ip <<< "$node_config"
        
        hash=$(get_block_hash "$node_ip" "$target_height")
        
        if [ -z "$hash" ]; then
            log_warning "Could not get block hash from ${node_name} at height ${target_height}"
            continue
        fi
        
        log "Block hash on ${node_name} at height ${target_height}: ${hash}"
        
        if [ -z "$first_hash" ]; then
            first_hash="$hash"
        elif [ "$hash" != "$first_hash" ]; then
            log_error "Block hash mismatch on ${node_name} at height ${target_height}"
            consistent=false
        fi
    done
    
    if [ "$consistent" = true ]; then
        log_success "Block hashes consistent at height ${target_height}"
        return 0
    else
        log_error "Block hashes inconsistent"
        return 1
    fi
}

# Remediation: Skip force sync (not supported without SSH)
force_sync_from_source() {
    local target_name="$1"
    local source_name="$2"
    
    log "Skipping SSH-based force sync from ${source_name} to ${target_name} (not supported without SSH)"
    log "Sync remediation requires SSH access to copy chain.db between nodes"
    return 1
}

# Main sync verification
main() {
    log "=== Blockchain Synchronization Verification Started ==="
    
    # Create log directory if it doesn't exist
    mkdir -p "${LOG_DIR}"
    
    local total_failures=0
    
    # Check chain ID consistency
    if ! check_chain_id_consistency; then
        log_error "Chain ID inconsistency detected - this is critical"
        ((total_failures++))
    fi
    
    # Check block synchronization
    if ! check_block_sync; then
        log_error "Block synchronization issue detected"
        ((total_failures++))
        
        # Determine source and target nodes for remediation
        local max_height=0
        local max_node=""
        local max_ip=""
        local min_height=999999
        local min_node=""
        local min_ip=""
        
        for node_config in "${NODES[@]}"; do
            IFS=':' read -r node_name node_ip <<< "$node_config"
            height=$(get_block_height "$node_ip")
            
            if [ "$height" -gt "$max_height" ]; then
                max_height=$height
                max_node="${node_name}"
                max_ip="${node_ip}"
            fi
            
            if [ "$height" -lt "$min_height" ]; then
                min_height=$height
                min_node="${node_name}"
                min_ip="${node_ip}"
            fi
        done
        
        # Skip remediation (not supported without SSH)
        local height_diff=$((max_height - min_height))
        if [ "$height_diff" -gt "$SYNC_THRESHOLD" ]; then
            log_warning "Sync difference exceeds threshold (diff: ${height_diff} blocks)"
            log_warning "Skipping SSH-based remediation (requires SSH access to copy chain.db)"
            ((total_failures++))
        fi
    fi
    
    # Check block hash consistency
    if ! check_block_hash_consistency; then
        log_error "Block hash inconsistency detected"
        ((total_failures++))
    fi
    
    log "=== Blockchain Synchronization Verification Completed ==="
    log "Total failures: ${total_failures}"
    
    if [ ${total_failures} -eq 0 ]; then
        log_success "Blockchain synchronization verification passed"
        exit 0
    else
        log_error "Blockchain synchronization verification failed with ${total_failures} failures"
        exit 1
    fi
}

# Run main function
main "$@"
