#!/bin/bash
# Redis Backup Script for AITBC
# Usage: ./backup_redis.sh [namespace] [backup_name]

set -euo pipefail

# Configuration
NAMESPACE=${1:-default}
BACKUP_NAME=${2:-redis-backup-$(date +%Y%m%d_%H%M%S)}
BACKUP_DIR="/tmp/redis-backups"
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

# Get Redis pod name
get_redis_pod() {
    local pod=$(kubectl get pods -n "$NAMESPACE" -l app.kubernetes.io/name=redis -o jsonpath='{.items[0].metadata.name}' 2>/dev/null || echo "")
    if [[ -z "$pod" ]]; then
        pod=$(kubectl get pods -n "$NAMESPACE" -l app=redis -o jsonpath='{.items[0].metadata.name}' 2>/dev/null || echo "")
    fi
    
    if [[ -z "$pod" ]]; then
        error "Could not find Redis pod in namespace $NAMESPACE"
        exit 1
    fi
    
    echo "$pod"
}

# Wait for Redis to be ready
wait_for_redis() {
    local pod=$1
    log "Waiting for Redis pod $pod to be ready..."
    
    kubectl wait --for=condition=ready pod "$pod" -n "$NAMESPACE" --timeout=300s
    
    # Check if Redis is accepting connections
    local retries=30
    while [[ $retries -gt 0 ]]; do
        if kubectl exec -n "$NAMESPACE" "$pod" -- redis-cli ping 2>/dev/null | grep -q PONG; then
            log "Redis is ready"
            return 0
        fi
        sleep 2
        ((retries--))
    done
    
    error "Redis did not become ready within timeout"
    exit 1
}

# Perform backup
perform_backup() {
    local pod=$1
    local backup_file="$BACKUP_DIR/${BACKUP_NAME}.rdb"
    
    log "Starting Redis backup to $backup_file"
    
    # Create Redis backup
    kubectl exec -n "$NAMESPACE" "$pod" -- redis-cli BGSAVE
    
    # Wait for background save to complete
    log "Waiting for background save to complete..."
    local retries=60
    while [[ $retries -gt 0 ]]; do
        local lastsave=$(kubectl exec -n "$NAMESPACE" "$pod" -- redis-cli LASTSAVE)
        local lastbgsave=$(kubectl exec -n "$NAMESPACE" "$pod" -- redis-cli LASTSAVE)
        
        if [[ "$lastsave" -gt "$lastbgsave" ]]; then
            log "Background save completed"
            break
        fi
        sleep 2
        ((retries--))
    done
    
    if [[ $retries -eq 0 ]]; then
        error "Background save did not complete within timeout"
        exit 1
    fi
    
    # Copy RDB file from pod
    kubectl cp "$NAMESPACE/$pod:/data/dump.rdb" "$backup_file"
    
    # Also create an append-only file backup if enabled
    local aof_enabled=$(kubectl exec -n "$NAMESPACE" "$pod" -- redis-cli CONFIG GET appendonly | tail -1)
    if [[ "$aof_enabled" == "yes" ]]; then
        local aof_backup="$BACKUP_DIR/${BACKUP_NAME}.aof"
        kubectl cp "$NAMESPACE/$pod:/data/appendonly.aof" "$aof_backup"
        log "AOF backup created: $aof_backup"
    fi
    
    log "Backup completed: $backup_file"
    
    # Verify backup
    if [[ -f "$backup_file" ]] && [[ -s "$backup_file" ]]; then
        local size=$(du -h "$backup_file" | cut -f1)
        log "Backup size: $size"
    else
        error "Backup file is empty or missing"
        exit 1
    fi
}

# Clean old backups
cleanup_old_backups() {
    log "Cleaning up backups older than $RETENTION_DAYS days"
    find "$BACKUP_DIR" -name "*.rdb" -type f -mtime +$RETENTION_DAYS -delete
    find "$BACKUP_DIR" -name "*.aof" -type f -mtime +$RETENTION_DAYS -delete
    log "Cleanup completed"
}

# Upload to cloud storage (optional)
upload_to_cloud() {
    local backup_file="$1"
    
    # Check if AWS CLI is configured
    if command -v aws &> /dev/null && aws sts get-caller-identity &>/dev/null; then
        log "Uploading backup to S3"
        local s3_bucket="aitbc-backups-${NAMESPACE}"
        local s3_key="redis/$(basename "$backup_file")"
        
        aws s3 cp "$backup_file" "s3://$s3_bucket/$s3_key" --storage-class GLACIER_IR
        log "Backup uploaded to s3://$s3_bucket/$s3_key"
        
        # Upload AOF file if exists
        local aof_file="${backup_file%.rdb}.aof"
        if [[ -f "$aof_file" ]]; then
            local aof_key="redis/$(basename "$aof_file")"
            aws s3 cp "$aof_file" "s3://$s3_bucket/$aof_key" --storage-class GLACIER_IR
            log "AOF backup uploaded to s3://$s3_bucket/$aof_key"
        fi
    else
        warn "AWS CLI not configured, skipping cloud upload"
    fi
}

# Main execution
main() {
    log "Starting Redis backup process"
    
    check_dependencies
    create_backup_dir
    
    local pod=$(get_redis_pod)
    wait_for_redis "$pod"
    
    perform_backup "$pod"
    cleanup_old_backups
    
    local backup_file="$BACKUP_DIR/${BACKUP_NAME}.rdb"
    upload_to_cloud "$backup_file"
    
    log "Redis backup process completed successfully"
}

# Run main function
main "$@"
