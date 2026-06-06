#!/bin/bash
# Ledger Storage Restore Script for AITBC
# Usage: ./restore_ledger.sh [namespace] [backup_directory]

set -euo pipefail

# Configuration
NAMESPACE=${1:-default}
BACKUP_DIR=${2:-}
TEMP_DIR="/tmp/ledger-restore-$(date +%s)"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Logging function
log() {
    echo -e "${GREEN}[$(date +'%Y-%m-%d %H:%M:%S')]${NC} $1"
}

error() {
    echo -e "${RED}[$(date +'%Y-%m-%d %H:%M:%S')] ERROR:${NC} $1" >&2
}

warn() {
    echo -e "${YELLOW}[$(date +'%Y-%m-%d %H:%M:%S')] WARNING:${NC} $1"
}

info() {
    echo -e "${BLUE}[$(date +'%Y-%m-%d %H:%M:%S')] INFO:${NC} $1"
}

# Check dependencies
check_dependencies() {
    if ! command -v kubectl &> /dev/null; then
        error "kubectl is not installed or not in PATH"
        exit 1
    fi
    
    if ! command -v jq &> /dev/null; then
        error "jq is not installed or not in PATH"
        exit 1
    fi
}

# Validate backup directory
validate_backup_dir() {
    if [[ -z "$BACKUP_DIR" ]]; then
        error "Backup directory must be specified"
        echo "Usage: $0 [namespace] [backup_directory]"
        exit 1
    fi
    
    if [[ ! -d "$BACKUP_DIR" ]]; then
        error "Backup directory not found: $BACKUP_DIR"
        exit 1
    fi
    
    # Check for required files
    if [[ ! -f "$BACKUP_DIR/metadata.json" ]]; then
        error "metadata.json not found in backup directory"
        exit 1
    fi
    
    if [[ ! -f "$BACKUP_DIR/chain.tar.gz" ]]; then
        error "chain.tar.gz not found in backup directory"
        exit 1
    fi
    
    log "Using backup directory: $BACKUP_DIR"
}

# Get blockchain node pods
get_blockchain_pods() {
    local pods=$(kubectl get pods -n "$NAMESPACE" -l app.kubernetes.io/name=blockchain-node -o jsonpath='{.items[*].metadata.name}' 2>/dev/null || echo "")
    if [[ -z "$pods" ]]; then
        pods=$(kubectl get pods -n "$NAMESPACE" -l app=blockchain-node -o jsonpath='{.items[*].metadata.name}' 2>/dev/null || echo "")
    fi
    
    if [[ -z "$pods" ]]; then
        error "Could not find blockchain node pods in namespace $NAMESPACE"
        exit 1
    fi
    
    echo $pods
}

# Create backup of current ledger before restore
create_pre_restore_backup() {
    local pods=($1)
    local pre_restore_backup="pre-restore-ledger-$(date +%Y%m%d_%H%M%S)"
    local pre_restore_dir="/tmp/ledger-backups/$pre_restore_backup"
    
    warn "Creating backup of current ledger before restore..."
    mkdir -p "$pre_restore_dir"
    
    # Use the first ready pod
    for pod in "${pods[@]}"; do
        if kubectl wait --for=condition=ready pod "$pod" -n "$NAMESPACE" --timeout=10s >/dev/null 2>&1; then
            # Get current block height
            local current_height=$(kubectl exec -n "$NAMESPACE" "$pod" -- curl -s http://localhost:8080/v1/blocks/head | jq -r '.height // 0')
            
            # Create metadata
            cat > "$pre_restore_dir/metadata.json" << EOF
{
  "backup_name": "$pre_restore_backup",
  "timestamp": "$(date -u +%Y-%m-%dT%H:%M:%SZ)",
  "namespace": "$NAMESPACE",
  "source_pod": "$pod",
  "latest_block_height": $current_height,
  "backup_type": "pre-restore"
}
EOF
            
            # Backup data directories
            local data_dirs=("chain" "wallets" "receipts")
            for dir in "${data_dirs[@]}"; do
                if kubectl exec -n "$NAMESPACE" "$pod" -- test -d "/app/data/$dir"; then
                    kubectl exec -n "$NAMESPACE" "$pod" -- tar -czf "/tmp/${pre_restore_backup}-${dir}.tar.gz" -C "/app/data" "$dir"
                    kubectl cp "$NAMESPACE/$pod:/tmp/${pre_restore_backup}-${dir}.tar.gz" "$pre_restore_dir/${dir}.tar.gz"
                    kubectl exec -n "$NAMESPACE" "$pod" -- rm -f "/tmp/${pre_restore_backup}-${dir}.tar.gz"
                fi
            done
            
            log "Pre-restore backup created: $pre_restore_dir"
            break
        fi
    done
}

# Perform restore
perform_restore() {
    local pods=($1)
    
    warn "This will replace all current ledger data. Are you sure? (y/N)"
    read -r response
    if [[ ! "$response" =~ ^[Yy]$ ]]; then
        log "Restore cancelled by user"
        exit 0
    fi
    
    # Scale down blockchain nodes
    info "Scaling down blockchain node deployment..."
    kubectl scale deployment blockchain-node --replicas=0 -n "$NAMESPACE"
    
    # Wait for pods to terminate
    kubectl wait --for=delete pod -l app=blockchain-node -n "$NAMESPACE" --timeout=120s
    
    # Scale up blockchain nodes
    info "Scaling up blockchain node deployment..."
    kubectl scale deployment blockchain-node --replicas=3 -n "$NAMESPACE"
    
    # Wait for pods to be ready
    local ready_pods=()
    local retries=30
    while [[ $retries -gt 0 && ${#ready_pods[@]} -eq 0 ]]; do
        local all_pods=$(get_blockchain_pods)
        for pod in $all_pods; do
            if kubectl wait --for=condition=ready pod "$pod" -n "$NAMESPACE" --timeout=10s >/dev/null 2>&1; then
                ready_pods+=("$pod")
            fi
        done
        
        if [[ ${#ready_pods[@]} -eq 0 ]]; then
            sleep 5
            ((retries--))
        fi
    done
    
    if [[ ${#ready_pods[@]} -eq 0 ]]; then
        error "No blockchain nodes became ready after restore"
        exit 1
    fi
    
    # Restore data to all ready pods
    for pod in "${ready_pods[@]}"; do
        info "Restoring ledger data to pod $pod..."
        
        # Create temp directory on pod
        kubectl exec -n "$NAMESPACE" "$pod" -- mkdir -p "$TEMP_DIR"
        
        # Extract and copy chain data
        if [[ -f "$BACKUP_DIR/chain.tar.gz" ]]; then
            kubectl cp "$BACKUP_DIR/chain.tar.gz" "$NAMESPACE/$pod:$TEMP_DIR/chain.tar.gz"
            kubectl exec -n "$NAMESPACE" "$pod" -- mkdir -p /app/data/chain
            kubectl exec -n "$NAMESPACE" "$pod" -- tar -xzf "$TEMP_DIR/chain.tar.gz" -C /app/data/
        fi
        
        # Extract and copy wallet data
        if [[ -f "$BACKUP_DIR/wallets.tar.gz" ]]; then
            kubectl cp "$BACKUP_DIR/wallets.tar.gz" "$NAMESPACE/$pod:$TEMP_DIR/wallets.tar.gz"
            kubectl exec -n "$NAMESPACE" "$pod" -- mkdir -p /app/data/wallets
            kubectl exec -n "$NAMESPACE" "$pod" -- tar -xzf "$TEMP_DIR/wallets.tar.gz" -C /app/data/
        fi
        
        # Extract and copy receipt data
        if [[ -f "$BACKUP_DIR/receipts.tar.gz" ]]; then
            kubectl cp "$BACKUP_DIR/receipts.tar.gz" "$NAMESPACE/$pod:$TEMP_DIR/receipts.tar.gz"
            kubectl exec -n "$NAMESPACE" "$pod" -- mkdir -p /app/data/receipts
            kubectl exec -n "$NAMESPACE" "$pod" -- tar -xzf "$TEMP_DIR/receipts.tar.gz" -C /app/data/
        fi
        
        # Set correct permissions
        kubectl exec -n "$NAMESPACE" "$pod" -- chown -R app:app /app/data/
        
        # Clean up temp directory
        kubectl exec -n "$NAMESPACE" "$pod" -- rm -rf "$TEMP_DIR"
        
        log "Ledger data restored to pod $pod"
    done
    
    log "Ledger restore completed successfully"
}

# Verify restore
verify_restore() {
    local pods=($1)
    
    log "Verifying ledger restore..."
    
    # Read backup metadata
    local backup_height=$(jq -r '.latest_block_height' "$BACKUP_DIR/metadata.json")
    log "Backup contains blocks up to height: $backup_height"
    
    # Verify on each pod
    for pod in "${pods[@]}"; do
        if kubectl wait --for=condition=ready pod "$pod" -n "$NAMESPACE" --timeout=10s >/dev/null 2>&1; then
            # Check if node is responding
            if kubectl exec -n "$NAMESPACE" "$pod" -- curl -s http://localhost:8080/v1/health >/dev/null 2>&1; then
                # Get current block height
                local current_height=$(kubectl exec -n "$NAMESPACE" "$pod" -- curl -s http://localhost:8080/v1/blocks/head | jq -r '.height // 0')
                
                if [[ "$current_height" -eq "$backup_height" ]]; then
                    log "✓ Pod $pod: Block height matches backup ($current_height)"
                else
                    warn "⚠ Pod $pod: Block height mismatch (expected: $backup_height, actual: $current_height)"
                fi
                
                # Check data directories
                local dirs=("chain" "wallets" "receipts")
                for dir in "${dirs[@]}"; do
                    if kubectl exec -n "$NAMESPACE" "$pod" -- test -d "/app/data/$dir"; then
                        local file_count=$(kubectl exec -n "$NAMESPACE" "$pod" -- find "/app/data/$dir" -type f | wc -l)
                        log "✓ Pod $pod: $dir directory contains $file_count files"
                    else
                        warn "⚠ Pod $pod: $dir directory not found"
                    fi
                done
            else
                error "✗ Pod $pod: Not responding to health checks"
            fi
        fi
    done
}

# Main execution
main() {
    log "Starting ledger restore process"
    
    check_dependencies
    validate_backup_dir
    
    local pods=($(get_blockchain_pods))
    create_pre_restore_backup "${pods[*]}"
    perform_restore "${pods[*]}"
    
    # Get updated pod list after restore
    pods=($(get_blockchain_pods))
    verify_restore "${pods[*]}"
    
    log "Ledger restore process completed successfully"
    warn "Please verify blockchain synchronization and application functionality"
}

# Run main function
main "$@"
