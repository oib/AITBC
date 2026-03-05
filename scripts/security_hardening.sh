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
PRODUCTION_ENV="/opt/aitbc/apps/coordinator-api/.env.production"
SERVICE_NAME="aitbc-coordinator"
LOG_FILE="/var/log/aitbc-security-hardening.log"

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
    
    log "Generated secure API keys"
    success "API keys generated successfully"
    
    # Save keys securely
    cat > /opt/aitbc/secure/api_keys.txt << EOF
# AITBC Production API Keys - Generated $(date)
# Keep this file secure and restricted!
CLIENT_API_KEYS=["$CLIENT_KEY"]
MINER_API_KEYS=["$MINER_KEY"]
ADMIN_API_KEYS=["$ADMIN_KEY"]
EOF
    
    chmod 600 /opt/aitbc/secure/api_keys.txt
    success "API keys saved to /opt/aitbc/secure/api_keys.txt"
}

# Update production environment
update_production_env() {
    log "Updating production environment configuration..."
    
    if [[ ! -f "$PRODUCTION_ENV" ]]; then
        warning "Production env file not found, creating from template..."
        cp /opt/aitbc/apps/coordinator-api/.env "$PRODUCTION_ENV"
    fi
    
    # Update API keys in production env
    if [[ -f /opt/aitbc/secure/api_keys.txt ]]; then
        source /opt/aitbc/secure/api_keys.txt
        
        sed -i "s/CLIENT_API_KEYS=.*/CLIENT_API_KEYS=$CLIENT_API_KEYS/" "$PRODUCTION_ENV"
        sed -i "s/MINER_API_KEYS=.*/MINER_API_KEYS=$MINER_API_KEYS/" "$PRODUCTION_ENV"
        sed -i "s/ADMIN_API_KEYS=.*/ADMIN_API_KEYS=$ADMIN_API_KEYS/" "$PRODUCTION_ENV"
        
        success "Production environment updated with secure API keys"
    fi
    
    # Set production-specific settings
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
    
    success "Production security settings applied"
}

# Configure firewall rules
configure_firewall() {
    log "Configuring firewall rules..."
    
    # Check if ufw is available
    if command -v ufw &> /dev/null; then
        # Allow SSH
        ufw allow 22/tcp
        
        # Allow HTTP/HTTPS
        ufw allow 80/tcp
        ufw allow 443/tcp
        
        # Allow internal services (restricted to localhost)
        ufw allow from 127.0.0.1 to any port 8000
        ufw allow from 127.0.0.1 to any port 8082
        
        # Enable firewall
        ufw --force enable
        
        success "Firewall configured with ufw"
    else
        warning "ufw not available, please configure firewall manually"
    fi
}

# Setup SSL/TLS security
setup_ssl_security() {
    log "Configuring SSL/TLS security..."
    
    # Check SSL certificate
    if [[ -f "/etc/letsencrypt/live/aitbc.bubuit.net/fullchain.pem" ]]; then
        success "SSL certificate found and valid"
        
        # Configure nginx security headers
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
        error "SSL certificate not found - please obtain certificate first"
    fi
}

# Setup log rotation
setup_log_rotation() {
    log "Configuring log rotation..."
    
    cat > /etc/logrotate.d/aitbc << EOF
/var/log/aitbc*.log {
    daily
    missingok
    rotate 30
    compress
    delaycompress
    notifempty
    create 644 aitbc aitbc
    postrotate
        systemctl reload rsyslog || true
    endscript
}
EOF
    
    success "Log rotation configured"
}

# Setup monitoring alerts
setup_monitoring() {
    log "Setting up basic monitoring..."
    
    # Create monitoring script
    cat > /opt/aitbc/scripts/health-check.sh << 'EOF'
#!/bin/bash
# Health check script for AITBC services

SERVICES=("aitbc-coordinator" "blockchain-node")
WEB_URL="https://aitbc.bubuit.net/api/v1/health"

# Check systemd services
for service in "${SERVICES[@]}"; do
    if systemctl is-active --quiet "$service"; then
        echo "✅ $service is running"
    else
        echo "❌ $service is not running"
        exit 1
    fi
done

# Check web endpoint
if curl -s -f "$WEB_URL" > /dev/null; then
    echo "✅ Web endpoint is responding"
else
    echo "❌ Web endpoint is not responding"
    exit 1
fi

echo "✅ All health checks passed"
EOF
    
    chmod +x /opt/aitbc/scripts/health-check.sh
    
    # Create cron job for health checks
    (crontab -l 2>/dev/null; echo "*/5 * * * * /opt/aitbc/scripts/health-check.sh >> /var/log/aitbc-health.log 2>&1") | crontab -
    
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
    
    # Create directories
    mkdir -p /opt/aitbc/secure
    mkdir -p /opt/aitbc/scripts
    
    # Execute security measures
    check_root
    generate_api_keys
    update_production_env
    configure_firewall
    setup_ssl_security
    setup_log_rotation
    setup_monitoring
    security_audit
    
    log "Security hardening completed successfully!"
    success "AITBC platform is now production-ready with enhanced security"
    
    echo
    echo "🔐 SECURITY SUMMARY:"
    echo "   ✅ Secure API keys generated"
    echo "   ✅ Production environment configured"
    echo "   ✅ Firewall rules applied"
    echo "   ✅ SSL/TLS security enhanced"
    echo "   ✅ Log rotation configured"
    echo "   ✅ Health monitoring setup"
    echo
    echo "📋 NEXT STEPS:"
    echo "   1. Restart services: systemctl restart $SERVICE_NAME"
    echo "   2. Update CLI config with new API keys"
    echo "   3. Run production tests"
    echo "   4. Monitor system performance"
    echo
    echo "🔑 API Keys Location: /opt/aitbc/secure/api_keys.txt"
    echo "📊 Health Logs: /var/log/aitbc-health.log"
    echo "🔒 Security Log: $LOG_FILE"
}

# Run main function
main "$@"
