#!/bin/bash
# PostgreSQL Restore Script for AITBC
# Usage: ./restore_postgresql.sh [namespace] [backup_file]

set -euo pipefail

# Configuration
NAMESPACE=${1:-default}
BACKUP_FILE=${2:-}
BACKUP_DIR="/tmp/postgresql-backups"

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
    
    if ! command -v pg_restore &> /dev/null; then
        error "pg_restore is not installed or not in PATH"
        exit 1
    fi
}

# Validate backup file
validate_backup_file() {
    if [[ -z "$BACKUP_FILE" ]]; then
        error "Backup file must be specified"
        echo "Usage: $0 [namespace] [backup_file]"
        exit 1
    fi
    
    # If file doesn't exist locally, try to find it in backup dir
    if [[ ! -f "$BACKUP_FILE" ]]; then
        local potential_file="$BACKUP_DIR/$(basename "$BACKUP_FILE")"
        if [[ -f "$potential_file" ]]; then
            BACKUP_FILE="$potential_file"
        else
            error "Backup file not found: $BACKUP_FILE"
            exit 1
        fi
    fi
    
    # Check if file is gzipped and decompress if needed
    if [[ "$BACKUP_FILE" == *.gz ]]; then
        info "Decompressing backup file..."
        gunzip -c "$BACKUP_FILE" > "/tmp/restore_$(date +%s).dump"
        BACKUP_FILE="/tmp/restore_$(date +%s).dump"
    fi
    
    log "Using backup file: $BACKUP_FILE"
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

# Create backup of current database before restore
create_pre_restore_backup() {
    local pod=$1
    local pre_restore_backup="pre-restore-$(date +%Y%m%d_%H%M%S)"
    
    warn "Creating backup of current database before restore..."
    
    # Get database credentials
    local db_user=$(kubectl get secret -n "$NAMESPACE" coordinator-postgresql -o jsonpath='{.data.username}' 2>/dev/null | base64 -d || echo "postgres")
    local db_password=$(kubectl get secret -n "$NAMESPACE" coordinator-postgresql -o jsonpath='{.data.password}' 2>/dev/null | base64 -d || echo "")
    local db_name=$(kubectl get secret -n "$NAMESPACE" coordinator-postgresql -o jsonpath='{.data.database}' 2>/dev/null | base64 -d || echo "aitbc")
    
    # Create backup
    PGPASSWORD="$db_password" kubectl exec -n "$NAMESPACE" "$pod" -- \
        pg_dump -U "$db_user" -h localhost -d "$db_name" \
        --format=custom --file="/tmp/${pre_restore_backup}.dump"
    
    # Copy backup locally
    kubectl cp "$NAMESPACE/$pod:/tmp/${pre_restore_backup}.dump" "$BACKUP_DIR/${pre_restore_backup}.dump"
    
    log "Pre-restore backup created: $BACKUP_DIR/${pre_restore_backup}.dump"
}

# Perform restore
perform_restore() {
    local pod=$1
    
    warn "This will replace the current database. Are you sure? (y/N)"
    read -r response
    if [[ ! "$response" =~ ^[Yy]$ ]]; then
        log "Restore cancelled by user"
        exit 0
    fi
    
    # Get database credentials
    local db_user=$(kubectl get secret -n "$NAMESPACE" coordinator-postgresql -o jsonpath='{.data.username}' 2>/dev/null | base64 -d || echo "postgres")
    local db_password=$(kubectl get secret -n "$NAMESPACE" coordinator-postgresql -o jsonpath='{.data.password}' 2>/dev/null | base64 -d || echo "")
    local db_name=$(kubectl get secret -n "$NAMESPACE" coordinator-postgresql -o jsonpath='{.data.database}' 2>/dev/null | base64 -d || echo "aitbc")
    
    # Copy backup file to pod
    local remote_backup="/tmp/restore_$(date +%s).dump"
    kubectl cp "$BACKUP_FILE" "$NAMESPACE/$pod:$remote_backup"
    
    # Drop existing database and recreate
    log "Dropping existing database..."
    PGPASSWORD="$db_password" kubectl exec -n "$NAMESPACE" "$pod" -- \
        psql -U "$db_user" -h localhost -d postgres -c "DROP DATABASE IF EXISTS $db_name;"
    
    log "Creating new database..."
    PGPASSWORD="$db_password" kubectl exec -n "$NAMESPACE" "$pod" -- \
        psql -U "$db_user" -h localhost -d postgres -c "CREATE DATABASE $db_name;"
    
    # Restore database
    log "Restoring database from backup..."
    PGPASSWORD="$db_password" kubectl exec -n "$NAMESPACE" "$pod" -- \
        pg_restore -U "$db_user" -h localhost -d "$db_name" \
        --verbose --clean --if-exists "$remote_backup"
    
    # Clean up remote file
    kubectl exec -n "$NAMESPACE" "$pod" -- rm -f "$remote_backup"
    
    log "Database restore completed successfully"
}

# Verify restore
verify_restore() {
    local pod=$1
    
    log "Verifying database restore..."
    
    # Get database credentials
    local db_user=$(kubectl get secret -n "$NAMESPACE" coordinator-postgresql -o jsonpath='{.data.username}' 2>/dev/null | base64 -d || echo "postgres")
    local db_password=$(kubectl get secret -n "$NAMESPACE" coordinator-postgresql -o jsonpath='{.data.password}' 2>/dev/null | base64 -d || echo "")
    local db_name=$(kubectl get secret -n "$NAMESPACE" coordinator-postgresql -o jsonpath='{.data.database}' 2>/dev/null | base64 -d || echo "aitbc")
    
    # Check table count
    local table_count=$(PGPASSWORD="$db_password" kubectl exec -n "$NAMESPACE" "$pod" -- \
        psql -U "$db_user" -h localhost -d "$db_name" -t -c "SELECT count(*) FROM information_schema.tables WHERE table_schema = 'public';" | tr -d ' ')
    
    log "Database contains $table_count tables"
    
    # Check if key tables exist
    local key_tables=("jobs" "marketplace_offers" "marketplace_bids" "blocks" "transactions")
    for table in "${key_tables[@]}"; do
        local exists=$(PGPASSWORD="$db_password" kubectl exec -n "$NAMESPACE" "$pod" -- \
            psql -U "$db_user" -h localhost -d "$db_name" -t -c "SELECT EXISTS (SELECT FROM information_schema.tables WHERE table_name = '$table');" | tr -d ' ')
        if [[ "$exists" == "t" ]]; then
            log "✓ Table $table exists"
        else
            warn "⚠ Table $table not found"
        fi
    done
}

# Main execution
main() {
    log "Starting PostgreSQL restore process"
    
    check_dependencies
    validate_backup_file
    
    local pod=$(get_postgresql_pod)
    wait_for_postgresql "$pod"
    
    create_pre_restore_backup "$pod"
    perform_restore "$pod"
    verify_restore "$pod"
    
    log "PostgreSQL restore process completed successfully"
    warn "Please verify application functionality after restore"
}

# Run main function
main "$@"
