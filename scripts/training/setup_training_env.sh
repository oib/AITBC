#!/bin/bash
# AITBC Training Environment Setup Script
# Sets up mainnet environment for agent training with funded accounts and messaging
#
# DEPRECATED: This script is deprecated in favor of the Python-based setup system.
# Use: python -m aitbc.training_setup.cli setup
# See: /opt/aitbc/docs/agent-training/ENVIRONMENT_SETUP.md

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
AITBC_DIR="/opt/aitbc"
LOG_DIR="/var/log/aitbc/training-setup"
mkdir -p "$LOG_DIR"

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
    echo -e "${timestamp} [${level}] ${message}" | tee -a "$LOG_DIR/setup.log"
}

check_prerequisites() {
    log "INFO" "Checking prerequisites..."
    
    # Check AITBC CLI
    if [ ! -f "$AITBC_DIR/aitbc-cli" ]; then
        log "ERROR" "AITBC CLI not found at $AITBC_DIR/aitbc-cli"
        return 1
    fi
    
    # Check AITBC node status
    cd "$AITBC_DIR"
    local node_status
    node_status=$(./aitbc-cli blockchain info 2>&1 || echo "node_not_running")
    if [[ "$node_status" == *"node_not_running"* ]] || [[ "$node_status" == *"error"* ]]; then
        log "WARN" "AITBC node may not be running on mainnet"
    else
        log "INFO" "AITBC node detected: $(echo "$node_status" | head -1)"
    fi
    
    log "SUCCESS" "Prerequisites check completed"
    return 0
}

setup_faucet() {
    log "INFO" "Setting up faucet mechanism..."
    
    if [ -f "$SCRIPT_DIR/setup_faucet.sh" ]; then
        bash "$SCRIPT_DIR/setup_faucet.sh"
        log "SUCCESS" "Faucet setup completed"
    else
        log "WARN" "Faucet setup script not found, skipping"
    fi
}

fund_accounts() {
    log "INFO" "Funding training accounts..."
    
    if [ -f "$SCRIPT_DIR/fund_accounts.sh" ]; then
        bash "$SCRIPT_DIR/fund_accounts.sh"
        log "SUCCESS" "Account funding completed"
    else
        log "WARN" "Account funding script not found, skipping"
    fi
}

configure_messaging() {
    log "INFO" "Configuring messaging authentication..."
    
    if [ -f "$SCRIPT_DIR/configure_messaging.sh" ]; then
        bash "$SCRIPT_DIR/configure_messaging.sh"
        log "SUCCESS" "Messaging configuration completed"
    else
        log "WARN" "Messaging configuration script not found, skipping"
    fi
}

verify_environment() {
    log "INFO" "Verifying training environment..."
    
    cd "$AITBC_DIR"
    
    # Check wallet list
    local wallets
    wallets=$(./aitbc-cli wallet list 2>&1 || echo "error")
    if [[ "$wallets" != *"error"* ]]; then
        log "INFO" "Wallets found: $(echo "$wallets" | grep -c "ait1" || echo "0")"
    fi
    
    # Check blockchain status
    local chain_status
    chain_status=$(./aitbc-cli blockchain info 2>&1 || echo "error")
    if [[ "$chain_status" != *"error"* ]]; then
        log "INFO" "Blockchain status: $(echo "$chain_status" | head -1)"
    fi
    
    log "SUCCESS" "Environment verification completed"
}

main() {
    log "INFO" "Starting AITBC training environment setup..."
    
    check_prerequisites || exit 1
    setup_faucet
    fund_accounts
    configure_messaging
    verify_environment
    
    log "SUCCESS" "Training environment setup completed"
    echo ""
    echo -e "${GREEN}=== Setup Summary ===${NC}"
    echo "Training environment is ready for agent training"
    echo "Log file: $LOG_DIR/setup.log"
    echo ""
    echo "Next steps:"
    echo "1. Run Stage 1 training: ./aitbc-cli openclaw-training train agent --agent-id <agent-id> --stage stage1_foundation"
    echo "2. Verify wallet funding before transaction operations"
    echo "3. Check messaging authentication before messaging operations"
}

main "$@"
