#!/bin/bash
# AITBC Messaging Authentication Configuration Script
# Sets up messaging service authentication for agent training
#
# DEPRECATED: This script is deprecated in favor of the Python-based setup system.
# Use: python -m aitbc.training_setup.cli setup (includes messaging configuration)
# See: /opt/aitbc/docs/agent-training/ENVIRONMENT_SETUP.md

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
AITBC_DIR="/opt/aitbc"
LOG_DIR="/var/log/aitbc/training-setup"
mkdir -p "$LOG_DIR"

# Configuration
MESSAGING_SERVICE_PORT=9002
AUTH_TOKEN_FILE="/var/lib/aitbc/messaging-auth.token"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

log() {
    local level="$1"
    shift
    local message="$@"
    local timestamp=$(date -Iseconds)
    echo -e "${timestamp} [${level}] ${message}" | tee -a "$LOG_DIR/configure_messaging.log"
}

check_messaging_service() {
    log "INFO" "Checking messaging service status..."
    
    # Check if messaging service is running
    if systemctl is-active --quiet aitbc-messaging 2>/dev/null; then
        log "INFO" "Messaging service is running"
        return 0
    else
        log "WARN" "Messaging service not running or not installed"
        return 1
    fi
}

generate_auth_token() {
    log "INFO" "Generating messaging authentication token..."
    
    # Generate random token
    local token
    token=$(openssl rand -hex 32)
    
    # Store token
    echo "$token" > "$AUTH_TOKEN_FILE"
    chmod 600 "$AUTH_TOKEN_FILE"
    
    log "SUCCESS" "Authentication token generated and stored"
    echo "$token"
}

configure_messaging_auth() {
    local wallet_name="$1"
    local password="$2"
    
    log "INFO" "Configuring messaging authentication for wallet: $wallet_name"
    
    cd "$AITBC_DIR"
    
    # Generate auth token
    local token
    token=$(generate_auth_token)
    
    # Configure wallet for messaging
    log "INFO" "Registering wallet with messaging service..."
    ./aitbc-cli agent message --wallet "$wallet_name" --password "$password" --auth-token "$token" || log "WARN" "Messaging registration may have failed"
    
    log "SUCCESS" "Messaging authentication configured for $wallet_name"
}

test_messaging_connectivity() {
    log "INFO" "Testing messaging connectivity..."
    
    cd "$AITBC_DIR"
    
    # Send test message
    local test_result
    test_result=$(./aitbc-cli agent message --topic "test-topic" --message "test-message" 2>&1 || echo "failed")
    
    if [[ "$test_result" == *"failed"* ]] || [[ "$test_result" == *"error"* ]]; then
        log "WARN" "Messaging connectivity test failed"
        return 1
    else
        log "SUCCESS" "Messaging connectivity test passed"
        return 0
    fi
}

setup_messaging_config() {
    log "INFO" "Setting up messaging configuration..."
    
    # Create messaging config directory
    mkdir -p /var/lib/aitbc/messaging
    
    # Create basic config
    cat > /var/lib/aitbc/messaging/config.json <<EOF
{
  "service_port": $MESSAGING_SERVICE_PORT,
  "auth_required": true,
  "auth_token_file": "$AUTH_TOKEN_FILE",
  "topics": ["test-topic", "training-topic", "agent-coordination"],
  "max_message_size": 1048576,
  "retention_policy": "7d"
}
EOF
    
    log "SUCCESS" "Messaging configuration created"
}

main() {
    log "INFO" "Starting messaging authentication configuration..."
    
    # Setup config
    setup_messaging_config
    
    # Check service
    check_messaging_service || log "WARN" "Messaging service may need to be started"
    
    # Configure authentication for training wallets
    configure_messaging_auth "training-wallet" "training123"
    configure_messaging_auth "exam-wallet" "exam123"
    
    # Test connectivity
    test_messaging_connectivity || log "WARN" "Messaging connectivity may require additional setup"
    
    log "SUCCESS" "Messaging authentication configuration completed"
    echo ""
    echo -e "${GREEN}=== Messaging Configuration Summary ===${NC}"
    echo "Auth token file: $AUTH_TOKEN_FILE"
    echo "Config file: /var/lib/aitbc/messaging/config.json"
    echo "Service port: $MESSAGING_SERVICE_PORT"
    echo ""
    echo "Next steps:"
    echo "1. Start messaging service if not running: systemctl start aitbc-messaging"
    echo "2. Test messaging with: ./aitbc-cli agent message --topic test-topic --message 'test'"
    echo "3. Check service status: systemctl status aitbc-messaging"
}

main "$@"
