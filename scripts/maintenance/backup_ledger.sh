#!/bin/bash
# Ledger Storage Backup Script for AITBC
# Usage: ./backup_ledger.sh [namespace] [backup_name]

set -euo pipefail

# Configuration
NAMESPACE=${1:-default}
BACKUP_NAME=${2:-ledger-backup-$(date +%Y%m%d_%H%M%S)}
BACKUP_DIR="/tmp/ledger-backups"
RETENTION_DAYS=30

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
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

# Check dependencies
check_dependencies() {
    if ! command -v kubectl &> /dev/null; then
        error "kubectl is not installed or not in PATH"
        exit 1
    fi
}

# Create backup directory
create_backup_dir() {
    mkdir -p "$BACKUP_DIR"
    log "Created backup directory: $BACKUP_DIR"
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

# Wait for blockchain node to be ready
wait_for_blockchain_node() {
    local pod=$1
    log "Waiting for blockchain node pod $pod to be ready..."
    
    kubectl wait --for=condition=ready pod "$pod" -n "$NAMESPACE" --timeout=300s
    
    # Check if node is responding
    local retries=30
    while [[ $retries -gt 0 ]]; do
        if kubectl exec -n "$NAMESPACE" "$pod" -- curl -s http://localhost:8080/v1/health >/dev/null 2>&1; then
            log "Blockchain node is ready"
            return 0
        fi
        sleep 2
        ((retries--))
    done
    
    error "Blockchain node did not become ready within timeout"
    exit 1
}

# Backup ledger data
backup_ledger_data() {
    local pod=$1
    local ledger_backup_dir="$BACKUP_DIR/${BACKUP_NAME}"
    mkdir -p "$ledger_backup_dir"
    
    log "Starting ledger backup from pod $pod"
    
    # Get the latest block height before backup
    local latest_block=$(kubectl exec -n "$NAMESPACE" "$pod" -- curl -s http://localhost:8080/v1/blocks/head | jq -r '.height // 0')
    log "Latest block height: $latest_block"
    
    # Backup blockchain data directory
    local blockchain_data_dir="/app/data/chain"
    if kubectl exec -n "$NAMESPACE" "$pod" -- test -d "$blockchain_data_dir"; then
        log "Backing up blockchain data directory..."
        kubectl exec -n "$NAMESPACE" "$pod" -- tar -czf "/tmp/${BACKUP_NAME}-chain.tar.gz" -C "$blockchain_data_dir" .
        kubectl cp "$NAMESPACE/$pod:/tmp/${BACKUP_NAME}-chain.tar.gz" "$ledger_backup_dir/chain.tar.gz"
        kubectl exec -n "$NAMESPACE" "$pod" -- rm -f "/tmp/${BACKUP_NAME}-chain.tar.gz"
    fi
    
    # Backup wallet data
    local wallet_data_dir="/app/data/wallets"
    if kubectl exec -n "$NAMESPACE" "$pod" -- test -d "$wallet_data_dir"; then
        log "Backing up wallet data directory..."
        kubectl exec -n "$NAMESPACE" "$pod" -- tar -czf "/tmp/${BACKUP_NAME}-wallets.tar.gz" -C "$wallet_data_dir" .
        kubectl cp "$NAMESPACE/$pod:/tmp/${BACKUP_NAME}-wallets.tar.gz" "$ledger_backup_dir/wallets.tar.gz"
        kubectl exec -n "$NAMESPACE" "$pod" -- rm -f "/tmp/${BACKUP_NAME}-wallets.tar.gz"
    fi
    
    # Backup receipts
    local receipts_data_dir="/app/data/receipts"
    if kubectl exec -n "$NAMESPACE" "$pod" -- test -d "$receipts_data_dir"; then
        log "Backing up receipts directory..."
        kubectl exec -n "$NAMESPACE" "$pod" -- tar -czf "/tmp/${BACKUP_NAME}-receipts.tar.gz" -C "$receipts_data_dir" .
        kubectl cp "$NAMESPACE/$pod:/tmp/${BACKUP_NAME}-receipts.tar.gz" "$ledger_backup_dir/receipts.tar.gz"
        kubectl exec -n "$NAMESPACE" "$pod" -- rm -f "/tmp/${BACKUP_NAME}-receipts.tar.gz"
    fi
    
    # Create metadata file
    cat > "$ledger_backup_dir/metadata.json" << EOF
{
  "backup_name": "$BACKUP_NAME",
  "timestamp": "$(date -u +%Y-%m-%dT%H:%M:%SZ)",
  "namespace": "$NAMESPACE",
  "source_pod": "$pod",
  "latest_block_height": $latest_block,
  "backup_type": "full"
}
EOF
    
    log "Ledger backup completed: $ledger_backup_dir"
    
    # Verify backup
    local total_size=$(du -sh "$ledger_backup_dir" | cut -f1)
    log "Total backup size: $total_size"
}

# Create incremental backup
create_incremental_backup() {
    local pod=$1
    local last_backup_file="$BACKUP_DIR/.last_backup_height"
    
    # Get last backup height
    local last_backup_height=0
    if [[ -f "$last_backup_file" ]]; then
        last_backup_height=$(cat "$last_backup_file")
    fi
    
    # Get current block height
    local current_height=$(kubectl exec -n "$NAMESPACE" "$pod" -- curl -s http://localhost:8080/v1/blocks/head | jq -r '.height // 0')
    
    if [[ $current_height -le $last_backup_height ]]; then
        log "No new blocks since last backup (height: $current_height)"
        return 0
    fi
    
    log "Creating incremental backup from block $((last_backup_height + 1)) to $current_height"
    
    # Export blocks since last backup
    local incremental_file="$BACKUP_DIR/${BACKUP_NAME}-incremental.json"
    kubectl exec -n "$NAMESPACE" "$pod" -- curl -s "http://localhost:8080/v1/blocks?from=$((last_backup_height + 1))&to=$current_height" > "$incremental_file"
    
    # Update last backup height
    echo "$current_height" > "$last_backup_file"
    
    log "Incremental backup created: $incremental_file"
}

# Clean old backups
cleanup_old_backups() {
    log "Cleaning up backups older than $RETENTION_DAYS days"
    find "$BACKUP_DIR" -maxdepth 1 -type d -name "ledger-backup-*" -mtime +$RETENTION_DAYS -exec rm -rf {} \;
    find "$BACKUP_DIR" -name "*-incremental.json" -type f -mtime +$RETENTION_DAYS -delete
    log "Cleanup completed"
}

# Upload to cloud storage (optional)
upload_to_cloud() {
    local backup_dir="$1"
    
    # Check if AWS CLI is configured
    if command -v aws &> /dev/null && aws sts get-caller-identity &>/dev/null; then
        log "Uploading backup to S3"
        local s3_bucket="aitbc-backups-${NAMESPACE}"
        
        # Upload entire backup directory
        aws s3 cp "$backup_dir" "s3://$s3_bucket/ledger/$(basename "$backup_dir")/" --recursive --storage-class GLACIER_IR
        
        log "Backup uploaded to s3://$s3_bucket/ledger/$(basename "$backup_dir")/"
    else
        warn "AWS CLI not configured, skipping cloud upload"
    fi
}

# Main execution
main() {
    local incremental=${3:-false}
    
    log "Starting ledger backup process (incremental=$incremental)"
    
    check_dependencies
    create_backup_dir
    
    local pods=($(get_blockchain_pods))
    
    # Use the first ready pod for backup
    for pod in "${pods[@]}"; do
        if kubectl wait --for=condition=ready pod "$pod" -n "$NAMESPACE" --timeout=10s >/dev/null 2>&1; then
            wait_for_blockchain_node "$pod"
            
            if [[ "$incremental" == "true" ]]; then
                create_incremental_backup "$pod"
            else
                backup_ledger_data "$pod"
            fi
            
            local backup_dir="$BACKUP_DIR/${BACKUP_NAME}"
            upload_to_cloud "$backup_dir"
            
            break
        fi
    done
    
    cleanup_old_backups
    
    log "Ledger backup process completed successfully"
}

# Run main function
main "$@"
