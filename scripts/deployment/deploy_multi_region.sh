#!/bin/bash
# Multi-Region Deployment Automation Framework
# Deploys AITBC node services across multiple global regions using systemd over SSH

set -euo pipefail

# Configuration
REGIONS=("us-east" "eu-central" "ap-northeast")
NODE_MAP=(
    "us-east:10.1.0.100"
    "eu-central:10.2.0.100"
    "ap-northeast:10.3.0.100"
)
SSH_USER="aitbc-admin"
SSH_KEY="~/.ssh/aitbc-deploy-key"
APP_DIR="/var/www/aitbc"
SERVICES=("aitbc-coordinator-api" "aitbc-marketplace" "aitbc-agent-worker")

# Logging
log() {
    echo "[$(date +'%Y-%m-%dT%H:%M:%S%z')] $1"
}

error() {
    echo "[$(date +'%Y-%m-%dT%H:%M:%S%z')] ERROR: $1" >&2
    exit 1
}

# Main deployment loop
deploy_to_region() {
    local region=$1
    local ip=$2
    log "Starting deployment to region: $region ($ip)"

    # 1. Sync code to remote node
    log "[$region] Syncing codebase..."
    rsync -avz -e "ssh -i $SSH_KEY" \
        --exclude '.git' --exclude 'node_modules' --exclude '.venv' \
        ../../ $SSH_USER@$ip:$APP_DIR/ || error "Failed to sync to $region"

    # 2. Update dependencies
    log "[$region] Updating dependencies..."
    ssh -i "$SSH_KEY" $SSH_USER@$ip "cd $APP_DIR && poetry install --no-dev" || error "Failed dependency install in $region"

    # 3. Apply regional configurations (mocking via sed/echo)
    log "[$region] Applying regional configurations..."
    ssh -i "$SSH_KEY" $SSH_USER@$ip "sed -i 's/^REGION=.*/REGION=$region/' $APP_DIR/.env"
    
    # 4. Restart systemd services
    log "[$region] Restarting systemd services..."
    for svc in "${SERVICES[@]}"; do
        ssh -i "$SSH_KEY" $SSH_USER@$ip "sudo systemctl restart $svc" || error "Failed to restart $svc in $region"
        log "[$region] Service $svc restarted."
    done

    # 5. Run health check
    log "[$region] Verifying health..."
    local status
    status=$(ssh -i "$SSH_KEY" $SSH_USER@$ip "curl -s -o /dev/null -w '%{http_code}' http://localhost:8000/health")
    if [ "$status" != "200" ]; then
        error "Health check failed in $region (HTTP $status)"
    fi
    log "[$region] Deployment successful."
}

# Execute deployments
log "Starting global multi-region deployment..."

for entry in "${NODE_MAP[@]}"; do
    region="${entry%%:*}"
    ip="${entry##*:}"
    
    # Run deployments sequentially for safety, could be parallelized with &
    deploy_to_region "$region" "$ip"
done

log "Global deployment completed successfully across ${#REGIONS[@]} regions."
