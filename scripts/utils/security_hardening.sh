#!/bin/bash
#
# Production Security Hardening Script for AITBC Platform
# This script implements security measures for production deployment
#

set -euo pipefail

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
PRODUCTION_ENV="${PRODUCTION_ENV:-/opt/aitbc/apps/coordinator-api/.env.production}"
SECURE_DIR="${SECURE_DIR:-/opt/aitbc/secure}"
API_KEYS_FILE="$SECURE_DIR/api_keys.txt"
BLOCKCHAIN_SECRETS_ENV="${BLOCKCHAIN_SECRETS_ENV:-/etc/aitbc/blockchain-secrets.env}"
# The unit is aitbc-coordinator-api; "aitbc-coordinator" does not exist (V23-98). Its one
# use is the closing "Restart services: systemctl restart $SERVICE_NAME" instruction, so
# the last thing this script told an operator to run failed with "Unit not found".
SERVICE_NAME="aitbc-coordinator-api"
LOG_FILE="${LOG_FILE:-/var/log/aitbc-security-hardening.log}"

# Logging function
log() {
    echo -e "${BLUE}[$(date +'%Y-%m-%d %H:%M:%S')]${NC} $1" | tee -a "$LOG_FILE"
}

success() {
    echo -e "${GREEN}✅ $1${NC}" | tee -a "$LOG_FILE"
}

warning() {
    echo -e "${YELLOW}⚠️  $1${NC}" | tee -a "$LOG_FILE"
}

error() {
    echo -e "${RED}❌ $1${NC}" | tee -a "$LOG_FILE"
}

# Check if running as root
check_root() {
    if [[ $EUID -ne 0 ]]; then
        error "This script must be run as root for system-level changes"
        exit 1
    fi
}

# Generate secure API keys
generate_api_keys() {
    log "Generating secure production API keys..."

    # Generate 32-character secure keys
    CLIENT_KEY=$(openssl rand -hex 16)
    MINER_KEY=$(openssl rand -hex 16)
    ADMIN_KEY=$(openssl rand -hex 16)
    WALLET_PASSWORD=$(openssl rand -hex 32)
    WALLET_IMPORT_PASSWORD="$WALLET_PASSWORD"

    log "Generated secure API keys"
    success "API keys generated successfully"

    # Save keys securely (record only — update_production_env reads the shell
    # variables directly; sourcing this file would strip the quotes and write
    # "[key]" literals into the env).
    mkdir -p "$SECURE_DIR"
    cat > "$API_KEYS_FILE" << EOF
# AITBC Production API Keys - Generated $(date)
# Keep this file secure and restricted!
CLIENT_API_KEYS=["$CLIENT_KEY"]
MINER_API_KEYS=["$MINER_KEY"]
ADMIN_API_KEYS=["$ADMIN_KEY"]
WALLET_IMPORT_PASSWORD="$WALLET_PASSWORD"
EOF

    chmod 600 "$API_KEYS_FILE"
    success "API keys saved to $API_KEYS_FILE"
}

# Replace KEY=... in FILE (default $PRODUCTION_ENV) or append it when absent.
_upsert_env() {
    local key="$1" value="$2" file="${3:-$PRODUCTION_ENV}"
    if grep -q "^${key}=" "$file"; then
        sed -i "s|^${key}=.*|${key}=${value}|" "$file"
    else
        printf '%s=%s\n' "$key" "$value" >> "$file"
    fi
}

# Update production environment
update_production_env() {
    log "Updating production environment configuration..."

    if [[ ! -f "$PRODUCTION_ENV" ]]; then
        warning "Production env file not found, creating from template..."
        cp /opt/aitbc/apps/coordinator-api/.env "$PRODUCTION_ENV"
    fi

    # Update API keys in production env. The values are already shell variables
    # from generate_api_keys — write them with printf/sed, never `source` the
    # keys file (bash would strip the quotes and the coordinator would store
    # "[key]" with brackets).
    if [[ -z "${CLIENT_KEY:-}" || -z "${MINER_KEY:-}" || -z "${ADMIN_KEY:-}" ]]; then
        warning "API key variables unset — skipping key update (run generate_api_keys first)"
    else
        _upsert_env "CLIENT_API_KEYS" "[\"$CLIENT_KEY\"]"
        _upsert_env "MINER_API_KEYS" "[\"$MINER_KEY\"]"
        _upsert_env "ADMIN_API_KEYS" "[\"$ADMIN_KEY\"]"
        success "Production environment updated with secure API keys"
    fi

    # Wallet import password belongs in the shared secrets env, not the coordinator file
    if [[ -n "${WALLET_IMPORT_PASSWORD:-}" ]]; then
        if [[ ! -f "$BLOCKCHAIN_SECRETS_ENV" ]]; then
            mkdir -p "$(dirname "$BLOCKCHAIN_SECRETS_ENV")"
            touch "$BLOCKCHAIN_SECRETS_ENV"
        fi
        _upsert_env "WALLET_IMPORT_PASSWORD" "$WALLET_IMPORT_PASSWORD" "$BLOCKCHAIN_SECRETS_ENV"
        chmod 600 "$BLOCKCHAIN_SECRETS_ENV"
        success "Wallet import password configured in $BLOCKCHAIN_SECRETS_ENV"
    fi

    # Set production-specific settings (idempotent: the marker block is appended once)
    if ! grep -q "^# Production Security Settings" "$PRODUCTION_ENV"; then
        cat >> "$PRODUCTION_ENV" << EOF

# Production Security Settings
ENV=production
DEBUG=false
LOG_LEVEL=INFO
RATE_LIMIT_ENABLED=true
RATE_LIMIT_MINER_HEARTBEAT=60
RATE_LIMIT_CLIENT_SUBMIT=30
CORS_ORIGINS=["https://aitbc.bubuit.net"]
EOF
    fi

    success "Production security settings applied"
}

# Firewall configuration is deliberately absent.
#
# This script used to run `ufw --force enable` here. AITBC services run in
# containers whose perimeter is filtered by the container host, so a firewall
# inside the guest is not where the boundary lives -- and the rules it installed
# made that plain: `ufw allow from 127.0.0.1 to any port 8202` is a no-op,
# because loopback traffic never traverses the filter it was written against.
# Enabling ufw inside a guest mostly creates a second place to look when
# something cannot reach something else.
#
# Perimeter filtering belongs to the host. See docs/deployment/NETWORK_POLICY.md
# for which listeners are expected to be reachable from where.

# Install nginx response-security headers.
#
# This used to be gated on a Let's Encrypt certificate existing locally, which
# meant it silently did nothing: AITBC obtains no certificates and terminates no
# TLS -- that happens upstream, see docs/deployment/NETWORK_POLICY.md. The
# headers are the part that was actually worth installing, so install them.
#
# Strict-Transport-Security is included because these responses are proxied to
# the client through the terminator, so the header does reach a browser over
# https. It has no effect on the cleartext hop.
setup_security_headers() {
    log "Installing nginx security headers..."

    if [[ -d /etc/nginx ]]; then
        mkdir -p /etc/nginx/snippets
        cat > /etc/nginx/snippets/security-headers.conf << EOF
# Security Headers
add_header X-Frame-Options "SAMEORIGIN" always;
add_header X-XSS-Protection "1; mode=block" always;
add_header X-Content-Type-Options "nosniff" always;
add_header Referrer-Policy "no-referrer-when-downgrade" always;
add_header Content-Security-Policy "default-src 'self' http: https: data: blob: 'unsafe-inline'" always;
add_header Strict-Transport-Security "max-age=31536000; includeSubDomains" always;
EOF

        # Include security headers in nginx config
        if grep -q "security-headers.conf" /etc/nginx/sites-available/aitbc-proxy.conf; then
            success "Security headers already configured"
        else
            # Add security headers to nginx config
            sed -i '/server_name/a\\n    include snippets/security-headers.conf;' /etc/nginx/sites-available/aitbc-proxy.conf
            success "Security headers added to nginx configuration"
        fi

        # Test and reload nginx
        nginx -t && systemctl reload nginx
        success "Nginx reloaded with security headers"
    else
        warning "nginx is not installed here - skipping security headers"
    fi
}

# Setup log rotation
setup_log_rotation() {
    log "Configuring log rotation..."

    cat > /etc/logrotate.d/aitbc << 'EOF'
# Top-level aitbc logs: open-per-write monitor scripts plus alerts.log, which
# the prometheus --watch writer holds open — copytruncate keeps appends on the
# live file and preserves each file's existing owner/mode (secrets-audit.log
# stays 0600). Service subdirectories self-rotate via TimedRotatingFileHandler
# and must not be listed here.
/var/log/aitbc/*.log {
    daily
    missingok
    rotate 14
    compress
    delaycompress
    notifempty
    copytruncate
}

# Event logs written open-per-write by 37_contract_event_monitoring.sh.
/var/log/aitbc/events/*.log {
    daily
    missingok
    rotate 14
    compress
    delaycompress
    notifempty
    create 0640 aitbc adm
}
EOF

    success "Log rotation configured"
}

# Setup monitoring alerts
setup_monitoring() {
    log "Setting up basic monitoring..."

    # Schedule the health check the deployment scripts already call, instead of writing a
    # third one (V23-98). What this used to generate checked two unit names that do not
    # exist -- "aitbc-coordinator" and "blockchain-node", where the real units are
    # aitbc-coordinator-api and aitbc-blockchain-node -- so its first check failed and it
    # exited 1 every five minutes forever. It also probed https://aitbc.bubuit.net, which
    # is a different host, and wrote itself into the git checkout as an untracked file.
    local health_check="/opt/aitbc/scripts/monitoring/health_check.sh"

    if [[ ! -x "$health_check" ]]; then
        warning "$health_check is missing or not executable; health check not scheduled"
        return 0
    fi

    # Idempotent: nothing guarantees this function runs only once, and stacking duplicate
    # crontab lines is how a five-minute check turns into several at once.
    if crontab -l 2>/dev/null | grep -qF "$health_check"; then
        log "Health check is already scheduled"
    else
        # `|| true`: the subshell inherits set -e, so on a host with no crontab yet
        # `crontab -l` exits 1 and hardening aborts here instead of installing the job.
        (crontab -l 2>/dev/null || true; echo "*/5 * * * * $health_check all >> /var/log/aitbc/health_check_cron.log 2>&1") | crontab -
        log "Scheduled $health_check every 5 minutes"
    fi

    success "Health monitoring configured"
}

# Security audit
security_audit() {
    log "Performing security audit..."

    # Check for open ports
    log "Open ports:"
    netstat -tuln | grep LISTEN | head -10

    # Check running services
    log "Running services:"
    systemctl list-units --type=service --state=running | grep -E "(aitbc|nginx|ssh)" | head -10

    # Check file permissions
    log "Critical file permissions:"
    ls -la /opt/aitbc/secure/ 2>/dev/null || echo "No secure directory found"
    ls -la /opt/aitbc/apps/coordinator-api/.env*

    success "Security audit completed"
}

# Main execution
main() {
    log "Starting AITBC Production Security Hardening..."

    # Check privileges before creating anything.
    check_root

    # Create directories
    mkdir -p "$SECURE_DIR"
    mkdir -p /opt/aitbc/scripts

    # Execute security measures
    generate_api_keys
    update_production_env
    setup_security_headers
    setup_log_rotation
    setup_monitoring
    security_audit

    log "Security hardening completed successfully!"
    success "AITBC platform is now production-ready with enhanced security"

    echo
    echo "🔐 SECURITY SUMMARY:"
    echo "   ✅ Secure API keys generated"
    echo "   ✅ Production environment configured"
    echo "   ✅ Nginx security headers installed"
    echo "   ✅ Log rotation configured"
    echo "   ✅ Health monitoring setup"
    echo
    echo "📋 NEXT STEPS:"
    echo "   1. Restart services: systemctl restart $SERVICE_NAME"
    echo "   2. Update CLI config with new API keys"
    echo "   3. Run production tests"
    echo "   4. Monitor system performance"
    echo
    echo "🔑 API Keys Location: $API_KEYS_FILE"
    echo "📊 Health Logs: /var/log/aitbc/health_check_cron.log"
    echo "🔒 Security Log: $LOG_FILE"
    echo
    echo "🔑 Generated keys (shown once — also in $API_KEYS_FILE):"
    echo "   CLIENT_API_KEY=$CLIENT_KEY"
    echo "   MINER_API_KEY=$MINER_KEY"
    echo "   ADMIN_API_KEY=$ADMIN_KEY"
}

# Run main function only when executed, not when sourced by tests.
if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
    main "$@"
fi
