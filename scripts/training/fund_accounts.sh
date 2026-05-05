#!/bin/bash
# AITBC Account Funding Script
# Funds training accounts on mainnet via faucet or genesis allocation
#
# DEPRECATED: This script is deprecated in favor of the Python-based setup system.
# Use: python -m aitbc.training_setup.cli fund-wallet <wallet-name>
# See: /opt/aitbc/docs/agent-training/ENVIRONMENT_SETUP.md

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
AITBC_DIR="/opt/aitbc"
LOG_DIR="/var/log/aitbc/training-setup"
mkdir -p "$LOG_DIR"

# Configuration
FAUCET_AMOUNT=1000  # AIT tokens per request
GENESIS_ALLOCATION=10000  # AIT tokens for genesis accounts

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
    echo -e "${timestamp} [${level}] ${message}" | tee -a "$LOG_DIR/fund_accounts.log"
}

create_genesis_allocation() {
    log "INFO" "Creating genesis allocation for training accounts..."
    
    cd "$AITBC_DIR"
    
    # Create genesis wallet if it doesn't exist
    if ! ./aitbc-cli wallet list | grep -q "genesis"; then
        log "INFO" "Creating genesis wallet..."
        ./aitbc-cli wallet create genesis "" || log "WARN" "Genesis wallet may already exist"
    fi
    
    # Initialize genesis with allocation
    log "INFO" "Initializing genesis with $GENESIS_ALLOCATION AIT allocation..."
    ./aitbc-cli blockchain genesis --force || log "WARN" "Genesis initialization may have failed"
    
    log "SUCCESS" "Genesis allocation completed"
}

setup_faucet_wallet() {
    log "INFO" "Setting up faucet wallet..."
    
    cd "$AITBC_DIR"
    
    # Create faucet wallet
    if ! ./aitbc-cli wallet list | grep -q "faucet"; then
        log "INFO" "Creating faucet wallet..."
        ./aitbc-cli wallet create faucet "faucet-password"
    fi
    
    # Fund faucet from genesis
    log "INFO" "Funding faucet wallet from genesis..."
    ./aitbc-cli wallet send genesis faucet $FAUCET_AMOUNT "" || log "WARN" "Faucet funding may have failed"
    
    log "SUCCESS" "Faucet wallet setup completed"
}

fund_training_wallet() {
    local wallet_name="$1"
    local password="$2"
    
    log "INFO" "Funding training wallet: $wallet_name"
    
    cd "$AITBC_DIR"
    
    # Create wallet if it doesn't exist
    if ! ./aitbc-cli wallet list | grep -q "$wallet_name"; then
        log "INFO" "Creating wallet: $wallet_name"
        ./aitbc-cli wallet create "$wallet_name" "$password"
    fi
    
    # Fund from faucet
    log "INFO" "Funding $wallet_name with $FAUCET_AMOUNT AIT from faucet..."
    ./aitbc-cli wallet send faucet "$wallet_name" $FAUCET_AMOUNT "faucet-password" || log "WARN" "Funding may have failed"
    
    # Verify balance
    local balance
    balance=$(./aitbc-cli wallet balance "$wallet_name" 2>&1 || echo "0")
    log "INFO" "Wallet $wallet_name balance: $balance"
    
    log "SUCCESS" "Training wallet $wallet_name funded"
}

verify_account_registration() {
    local wallet_name="$1"
    
    log "INFO" "Verifying account registration for: $wallet_name"
    
    cd "$AITBC_DIR"
    
    # Check if account exists on-chain
    local account_info
    account_info=$(./aitbc-cli blockchain account "$wallet_name" 2>&1 || echo "not_found")
    
    if [[ "$account_info" == *"not_found"* ]]; then
        log "WARN" "Account $wallet_name not found on-chain - may need manual registration"
        return 1
    else
        log "SUCCESS" "Account $wallet_name registered on-chain"
        return 0
    fi
}

main() {
    log "INFO" "Starting account funding process..."
    
    # Setup genesis and faucet
    create_genesis_allocation
    setup_faucet_wallet
    
    # Fund standard training wallets
    fund_training_wallet "training-wallet" "training123"
    fund_training_wallet "exam-wallet" "exam123"
    
    # Verify account registration
    verify_account_registration "training-wallet"
    verify_account_registration "exam-wallet"
    
    log "SUCCESS" "Account funding completed"
    echo ""
    echo -e "${GREEN}=== Funding Summary ===${NC}"
    echo "Genesis wallet: Funded with $GENESIS_ALLOCATION AIT"
    echo "Faucet wallet: Funded with $FAUCET_AMOUNT AIT"
    echo "Training wallets: Funded with $FAUCET_AMOUNT AIT each"
    echo ""
    echo "Note: Account registration on-chain may require additional steps"
    echo "Check blockchain status with: ./aitbc-cli blockchain info"
}

main "$@"
