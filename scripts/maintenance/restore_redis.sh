#!/bin/bash
# Redis Restore Script for AITBC
# Usage: ./restore_redis.sh [namespace] [backup_file]

set -euo pipefail

# Configuration
NAMESPACE=${1:-default}
BACKUP_FILE=${2:-}
BACKUP_DIR="/tmp/redis-backups"

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
    
    log "Using backup file: $BACKUP_FILE"
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

# Create backup of current Redis data before restore
create_pre_restore_backup() {
    local pod=$1
    local pre_restore_backup="pre-restore-redis-$(date +%Y%m%d_%H%M%S)"
    
    warn "Creating backup of current Redis data before restore..."
    
    # Create background save
    kubectl exec -n "$NAMESPACE" "$pod" -- redis-cli BGSAVE
    
    # Wait for save to complete
    local retries=60
    while [[ $retries -gt 0 ]]; do
        local lastsave=$(kubectl exec -n "$NAMESPACE" "$pod" -- redis-cli LASTSAVE)
        local lastbgsave=$(kubectl exec -n "$NAMESPACE" "$pod" -- redis-cli LASTSAVE)
        
        if [[ "$lastsave" -gt "$lastbgsave" ]]; then
            break
        fi
        sleep 2
        ((retries--))
    done
    
    # Copy backup locally
    kubectl cp "$NAMESPACE/$pod:/data/dump.rdb" "$BACKUP_DIR/${pre_restore_backup}.rdb"
    
    # Also backup AOF if exists
    if kubectl exec -n "$NAMESPACE" "$pod" -- test -f /data/appendonly.aof; then
        kubectl cp "$NAMESPACE/$pod:/data/appendonly.aof" "$BACKUP_DIR/${pre_restore_backup}.aof"
    fi
    
    log "Pre-restore backup created: $BACKUP_DIR/${pre_restore_backup}.rdb"
}

# Perform restore
perform_restore() {
    local pod=$1
    
    warn "This will replace all current Redis data. Are you sure? (y/N)"
    read -r response
    if [[ ! "$response" =~ ^[Yy]$ ]]; then
        log "Restore cancelled by user"
        exit 0
    fi
    
    # Scale down Redis to ensure clean restore
    info "Scaling down Redis deployment..."
    kubectl scale deployment redis --replicas=0 -n "$NAMESPACE"
    
    # Wait for pod to terminate
    kubectl wait --for=delete pod -l app=redis -n "$NAMESPACE" --timeout=120s
    
    # Scale up Redis
    info "Scaling up Redis deployment..."
    kubectl scale deployment redis --replicas=1 -n "$NAMESPACE"
    
    # Wait for new pod to be ready
    local new_pod=$(get_redis_pod)
    kubectl wait --for=condition=ready pod "$new_pod" -n "$NAMESPACE" --timeout=300s
    
    # Stop Redis server
    info "Stopping Redis server..."
    kubectl exec -n "$NAMESPACE" "$new_pod" -- redis-cli SHUTDOWN NOSAVE
    
    # Clear existing data
    info "Clearing existing Redis data..."
    kubectl exec -n "$NAMESPACE" "$new_pod" -- rm -f /data/dump.rdb /data/appendonly.aof
    
    # Copy backup file
    info "Copying backup file..."
    local remote_file="/data/restore.rdb"
    kubectl cp "$BACKUP_FILE" "$NAMESPACE/$new_pod:$remote_file"
    
    # Set correct permissions
    kubectl exec -n "$NAMESPACE" "$new_pod" -- chown redis:redis "$remote_file"
    
    # Start Redis server
    info "Starting Redis server..."
    kubectl exec -n "$NAMESPACE" "$new_pod" -- redis-server --daemonize yes
    
    # Wait for Redis to be ready
    local retries=30
    while [[ $retries -gt 0 ]]; do
        if kubectl exec -n "$NAMESPACE" "$new_pod" -- redis-cli ping 2>/dev/null | grep -q PONG; then
            log "Redis is ready"
            break
        fi
        sleep 2
        ((retries--))
    done
    
    if [[ $retries -eq 0 ]]; then
        error "Redis did not start properly after restore"
        exit 1
    fi
    
    log "Redis restore completed successfully"
}

# Verify restore
verify_restore() {
    local pod=$1
    
    log "Verifying Redis restore..."
    
    # Check database size
    local db_size=$(kubectl exec -n "$NAMESPACE" "$pod" -- redis-cli DBSIZE)
    log "Database contains $db_size keys"
    
    # Check memory usage
    local memory=$(kubectl exec -n "$NAMESPACE" "$pod" -- redis-cli INFO memory | grep used_memory_human | cut -d: -f2 | tr -d '\r')
    log "Memory usage: $memory"
    
    # Check if Redis is responding to commands
    if kubectl exec -n "$NAMESPACE" "$pod" -- redis-cli ping 2>/dev/null | grep -q PONG; then
        log "✓ Redis is responding normally"
    else
        error "✗ Redis is not responding"
        exit 1
    fi
}

# Main execution
main() {
    log "Starting Redis restore process"
    
    check_dependencies
    validate_backup_file
    
    local pod=$(get_redis_pod)
    create_pre_restore_backup "$pod"
    perform_restore "$pod"
    
    # Get new pod name after restore
    pod=$(get_redis_pod)
    verify_restore "$pod"
    
    log "Redis restore process completed successfully"
    warn "Please verify application functionality after restore"
}

# Run main function
main "$@"
