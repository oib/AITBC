#!/bin/bash
# Secret Rotation Script for Rolling Release Environment
# This script rotates JWT_SECRET with zero-downtime using dual-secret overlap
# Usage: sudo ./rotate_jwt_secret.sh <new_secret>

set -e

# Configuration
SERVICES=("aitbc-coordinator-api" "aitbc-blockchain-node" "aitbc-marketplace" "aitbc-exchange" "aitbc-gpu")
ROLLBACK_FILE="/tmp/secret_rotation_rollback_$(date +%Y%m%d_%H%M%S).sh"
LOG_FILE="/var/log/aitbc/secret_rotation_$(date +%Y%m%d_%H%M%S).log"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Logging function
log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1" | tee -a "$LOG_FILE"
}

# Error handling
error_exit() {
    log "${RED}ERROR: $1${NC}"
    log "Rollback script saved to: $ROLLBACK_FILE"
    exit 1
}

# Check if running as root
if [ "$EUID" -ne 0 ]; then
    error_exit "This script must be run as root"
fi

# Check if new secret is provided
if [ -z "$1" ]; then
    error_exit "Usage: $0 <new_secret>"
fi

NEW_SECRET="$1"
log "Starting JWT_SECRET rotation for rolling release"
log "New secret length: ${#NEW_SECRET} characters"

# Backup current secrets
log "Backing up current secrets..."
for service in "${SERVICES[@]}"; do
    if [ -f "/etc/aitbc/${service}.env" ]; then
        cp "/etc/aitbc/${service}.env" "/etc/aitbc/${service}.env.backup_$(date +%Y%m%d_%H%M%S)"
        log "Backed up ${service}.env"
    fi
done

# Create rollback script
cat > "$ROLLBACK_FILE" << 'ROLLBACK_EOF'
#!/bin/bash
# Auto-generated rollback script for secret rotation
set -e
echo "Rolling back secret rotation..."
# Restore backups
for backup in /etc/aitbc/*.env.backup_*; do
    if [ -f "$backup" ]; then
        original="${backup%.backup_*}"
        cp "$backup" "$original"
        echo "Restored $original"
    fi
done
# Restart all services
systemctl restart aitbc-coordinator-api aitbc-blockchain-node aitbc-marketplace aitbc-exchange aitbc-gpu
echo "Rollback complete"
ROLLBACK_EOF
chmod +x "$ROLLBACK_FILE"
log "Rollback script created: $ROLLBACK_FILE"

# Phase 1: Add new secret alongside old secret (dual-secret overlap)
log "Phase 1: Adding new secret with dual-secret overlap..."
for service in "${SERVICES[@]}"; do
    env_file="/etc/aitbc/${service}.env"
    if [ -f "$env_file" ]; then
        # Add new secret as JWT_SECRET_NEW
        if ! grep -q "JWT_SECRET_NEW=" "$env_file"; then
            echo "JWT_SECRET_NEW=$NEW_SECRET" >> "$env_file"
            log "Added JWT_SECRET_NEW to ${service}.env"
        else
            log "JWT_SECRET_NEW already exists in ${service}.env, updating..."
            sed -i "s/JWT_SECRET_NEW=.*/JWT_SECRET_NEW=$NEW_SECRET/" "$env_file"
        fi
    fi
done

# Phase 2: Rolling restart services one by one
log "Phase 2: Rolling restart services with dual-secret support..."
for service in "${SERVICES[@]}"; do
    log "Restarting $service..."
    systemctl restart "$service"

    # Wait for service to be healthy
    log "Waiting for $service to be healthy..."
    sleep 10

    # Check service status
    if systemctl is-active --quiet "$service"; then
        log "${GREEN}$service is healthy${NC}"
    else
        error_exit "$service failed to start after restart"
    fi

    # Verify service is accepting requests (if applicable)
    case "$service" in
        "aitbc-coordinator-api")
            if curl -s http://localhost:8203/health > /dev/null; then
                log "${GREEN}$service health check passed${NC}"
            else
                error_exit "$service health check failed"
            fi
            ;;
        "aitbc-marketplace")
            if curl -s http://localhost:8104/health > /dev/null 2>&1; then
                log "${GREEN}$service health check passed${NC}"
            else
                log "${YELLOW}$service health check not available, skipping${NC}"
            fi
            ;;
    esac
done

# Phase 3: Verify all services are healthy with dual-secret support
log "Phase 3: Verifying all services are healthy..."
for service in "${SERVICES[@]}"; do
    if systemctl is-active --quiet "$service"; then
        log "${GREEN}$service is healthy${NC}"
    else
        error_exit "$service is not healthy after dual-secret phase"
    fi
done

# Phase 4: Replace old secret with new secret
log "Phase 4: Replacing old secret with new secret..."
for service in "${SERVICES[@]}"; do
    env_file="/etc/aitbc/${service}.env"
    if [ -f "$env_file" ]; then
        # Replace JWT_SECRET with JWT_SECRET_NEW
        sed -i "s/JWT_SECRET=.*/JWT_SECRET=$NEW_SECRET/" "$env_file"
        # Remove JWT_SECRET_NEW
        sed -i "/JWT_SECRET_NEW=/d" "$env_file"
        log "Updated ${service}.env with new secret"
    fi
done

# Phase 5: Final rolling restart with new secret only
log "Phase 5: Final rolling restart with new secret only..."
for service in "${SERVICES[@]}"; do
    log "Restarting $service with new secret..."
    systemctl restart "$service"

    # Wait for service to be healthy
    log "Waiting for $service to be healthy..."
    sleep 10

    # Check service status
    if systemctl is-active --quiet "$service"; then
        log "${GREEN}$service is healthy with new secret${NC}"
    else
        error_exit "$service failed to start with new secret"
    fi

    # Verify service is accepting requests
    case "$service" in
        "aitbc-coordinator-api")
            if curl -s http://localhost:8203/health > /dev/null; then
                log "${GREEN}$service health check passed${NC}"
            else
                error_exit "$service health check failed with new secret"
            fi
            ;;
    esac
done

# Phase 6: Final verification
log "Phase 6: Final verification..."
for service in "${SERVICES[@]}"; do
    if systemctl is-active --quiet "$service"; then
        log "${GREEN}$service is healthy${NC}"
    else
        error_exit "$service is not healthy after final restart"
    fi
done

# Cleanup
log "Cleaning up backup files..."
find /etc/aitbc -name "*.env.backup_*" -mtime +7 -delete
rm "$ROLLBACK_FILE"
log "Rollback script removed"

log "${GREEN}JWT_SECRET rotation completed successfully${NC}"
log "Rotation log saved to: $LOG_FILE"
