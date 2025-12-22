#!/bin/bash
# PostgreSQL Backup Script for AITBC
# Usage: ./backup_postgresql.sh [namespace] [backup_name]

set -euo pipefail

# Configuration
NAMESPACE=${1:-default}
BACKUP_NAME=${2:-postgresql-backup-$(date +%Y%m%d_%H%M%S)}
BACKUP_DIR="/tmp/postgresql-backups"
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
    
    if ! command -v pg_dump &> /dev/null; then
        error "pg_dump is not installed or not in PATH"
        exit 1
    fi
}

# Create backup directory
create_backup_dir() {
    mkdir -p "$BACKUP_DIR"
    log "Created backup directory: $BACKUP_DIR"
}

# Get PostgreSQL pod name
get_postgresql_pod() {
    local pod=$(kubectl get pods -n "$NAMESPACE" -l app.kubernetes.io/name=postgresql -o jsonpath='{.items[0].metadata.name}' 2>/dev/null || echo "")
    if [[ -z "$pod" ]]; then
        pod=$(kubectl get pods -n "$NAMESPACE" -l app=postgresql -o jsonpath='{.items[0].metadata.name}' 2>/dev/null || echo "")
    fi
    
    if [[ -z "$pod" ]]; then
        error "Could not find PostgreSQL pod in namespace $NAMESPACE"
        exit 1
    fi
    
    echo "$pod"
}

# Wait for PostgreSQL to be ready
wait_for_postgresql() {
    local pod=$1
    log "Waiting for PostgreSQL pod $pod to be ready..."
    
    kubectl wait --for=condition=ready pod "$pod" -n "$NAMESPACE" --timeout=300s
    
    # Check if PostgreSQL is accepting connections
    local retries=30
    while [[ $retries -gt 0 ]]; do
        if kubectl exec -n "$NAMESPACE" "$pod" -- pg_isready -U postgres >/dev/null 2>&1; then
            log "PostgreSQL is ready"
            return 0
        fi
        sleep 2
        ((retries--))
    done
    
    error "PostgreSQL did not become ready within timeout"
    exit 1
}

# Perform backup
perform_backup() {
    local pod=$1
    local backup_file="$BACKUP_DIR/${BACKUP_NAME}.sql"
    
    log "Starting PostgreSQL backup to $backup_file"
    
    # Get database credentials from secret
    local db_user=$(kubectl get secret -n "$NAMESPACE" coordinator-postgresql -o jsonpath='{.data.username}' 2>/dev/null | base64 -d || echo "postgres")
    local db_password=$(kubectl get secret -n "$NAMESPACE" coordinator-postgresql -o jsonpath='{.data.password}' 2>/dev/null | base64 -d || echo "")
    local db_name=$(kubectl get secret -n "$NAMESPACE" coordinator-postgresql -o jsonpath='{.data.database}' 2>/dev/null | base64 -d || echo "aitbc")
    
    # Perform the backup
    PGPASSWORD="$db_password" kubectl exec -n "$NAMESPACE" "$pod" -- \
        pg_dump -U "$db_user" -h localhost -d "$db_name" \
        --verbose --clean --if-exists --create --format=custom \
        --file="/tmp/${BACKUP_NAME}.dump"
    
    # Copy backup from pod
    kubectl cp "$NAMESPACE/$pod:/tmp/${BACKUP_NAME}.dump" "$backup_file"
    
    # Clean up remote backup file
    kubectl exec -n "$NAMESPACE" "$pod" -- rm -f "/tmp/${BACKUP_NAME}.dump"
    
    # Compress backup
    gzip "$backup_file"
    backup_file="${backup_file}.gz"
    
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
    find "$BACKUP_DIR" -name "*.sql.gz" -type f -mtime +$RETENTION_DAYS -delete
    log "Cleanup completed"
}

# Upload to cloud storage (optional)
upload_to_cloud() {
    local backup_file="$1"
    
    # Check if AWS CLI is configured
    if command -v aws &> /dev/null && aws sts get-caller-identity &>/dev/null; then
        log "Uploading backup to S3"
        local s3_bucket="aitbc-backups-${NAMESPACE}"
        local s3_key="postgresql/$(basename "$backup_file")"
        
        aws s3 cp "$backup_file" "s3://$s3_bucket/$s3_key" --storage-class GLACIER_IR
        log "Backup uploaded to s3://$s3_bucket/$s3_key"
    else
        warn "AWS CLI not configured, skipping cloud upload"
    fi
}

# Main execution
main() {
    log "Starting PostgreSQL backup process"
    
    check_dependencies
    create_backup_dir
    
    local pod=$(get_postgresql_pod)
    wait_for_postgresql "$pod"
    
    perform_backup "$pod"
    cleanup_old_backups
    
    local backup_file="$BACKUP_DIR/${BACKUP_NAME}.sql.gz"
    upload_to_cloud "$backup_file"
    
    log "PostgreSQL backup process completed successfully"
}

# Run main function
main "$@"
