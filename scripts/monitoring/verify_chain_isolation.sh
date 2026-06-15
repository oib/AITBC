#!/bin/bash
# Chain Isolation Verification Script
# Checks for chain isolation violations across AITBC blockchain nodes

set -e

DATA_DIR="/var/lib/aitbc/data"
LOG_FILE="/var/log/aitbc/chain-isolation-verification.log"
VIOLATION_COUNT=0

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1" | tee -a "$LOG_FILE"
}

log_error() {
    echo -e "${RED}[ERROR] $1${NC}" | tee -a "$LOG_FILE"
}

log_success() {
    echo -e "${GREEN}[OK] $1${NC}" | tee -a "$LOG_FILE"
}

log_warning() {
    echo -e "${YELLOW}[WARN] $1${NC}" | tee -a "$LOG_FILE"
}

# Check database for cross-chain blocks
check_database_isolation() {
    local chain_db="$1"
    local expected_chain="$2"

    log "Checking database: $chain_db (expected chain: $expected_chain)"

    if [ ! -f "$chain_db" ]; then
        log_warning "Database file not found: $chain_db"
        return 0
    fi

    # Check for blocks from other chains
    cross_chain_blocks=$(sqlite3 "$chain_db" "SELECT chain_id, COUNT(*) FROM block GROUP BY chain_id HAVING chain_id != '$expected_chain';" 2>/dev/null || echo "")

    if [ -n "$cross_chain_blocks" ]; then
        log_error "Cross-chain blocks found in $chain_db:"
        echo "$cross_chain_blocks" | while read -r line; do
            log_error "  $line"
        done
        ((VIOLATION_COUNT++))
    else
        log_success "No cross-chain blocks in $chain_db"
    fi

    # Check for accounts from other chains
    cross_chain_accounts=$(sqlite3 "$chain_db" "SELECT chain_id, COUNT(*) FROM account GROUP BY chain_id HAVING chain_id != '$expected_chain';" 2>/dev/null || echo "")

    if [ -n "$cross_chain_accounts" ]; then
        log_error "Cross-chain accounts found in $chain_db:"
        echo "$cross_chain_accounts" | while read -r line; do
            log_error "  $line"
        done
        ((VIOLATION_COUNT++))
    else
        log_success "No cross-chain accounts in $chain_db"
    fi

    # Check for transactions from other chains
    cross_chain_txs=$(sqlite3 "$chain_db" "SELECT chain_id, COUNT(*) FROM \"transaction\" GROUP BY chain_id HAVING chain_id != '$expected_chain';" 2>/dev/null || echo "")

    if [ -n "$cross_chain_txs" ]; then
        log_error "Cross-chain transactions found in $chain_db:"
        echo "$cross_chain_txs" | while read -r line; do
            log_error "  $line"
        done
        ((VIOLATION_COUNT++))
    else
        log_success "No cross-chain transactions in $chain_db"
    fi
}

# Check node configuration
check_node_configuration() {
    local node_name="$1"
    local blockchain_env="$2"
    local expected_chain="$3"

    log "Checking $node_name configuration (expected chain: $expected_chain)"

    if [ ! -f "$blockchain_env" ]; then
        log_warning "Blockchain env file not found: $blockchain_env"
        return 0
    fi

    supported_chains=$(grep "^supported_chains=" "$blockchain_env" | cut -d'=' -f2)

    # Check if expected chain is in the supported chains list (handles comma-separated values)
    if [[ ",$supported_chains," == *",$expected_chain,"* ]]; then
        log_success "$node_name supported_chains=$supported_chains (includes $expected_chain)"
    else
        log_error "$node_name supported_chains=$supported_chains (expected to include: $expected_chain)"
        ((VIOLATION_COUNT++))
    fi
}

# Main verification
main() {
    log "=== Chain Isolation Verification Started ==="

    # Detect which node this script is running on
    local hostname=$(hostname)
    local expected_chain=""

    if [ "$hostname" = "aitbc" ]; then
        expected_chain="ait-mainnet"
    elif [ "$hostname" = "aitbc1" ]; then
        expected_chain="ait-testnet"
    else
        log_warning "Unknown hostname: $hostname, defaulting to ait-mainnet check"
        expected_chain="ait-mainnet"
    fi

    log "Running on node: $hostname (expected chain: $expected_chain)"

    # Check local node configuration
    check_node_configuration "$hostname" "/etc/aitbc/blockchain.env" "$expected_chain"
    check_database_isolation "$DATA_DIR/$expected_chain/chain.db" "$expected_chain"

    # Check remote node if accessible
    if [ "$hostname" = "aitbc" ]; then
        # On aitbc, check aitbc1 (testnet)
        if ssh aitbc1 test -f "/etc/aitbc/blockchain.env" 2>/dev/null; then
            REMOTE_CHAINS=$(ssh aitbc1 'cat /etc/aitbc/blockchain.env | grep "^supported_chains=" | cut -d"=" -f2')
            # Check if expected chain is in the supported chains list (handles comma-separated values)
            if [[ ",$REMOTE_CHAINS," == *",ait-testnet,"* ]]; then
                log_success "aitbc1 supported_chains=$REMOTE_CHAINS (includes ait-testnet)"
            else
                log_error "aitbc1 supported_chains=$REMOTE_CHAINS (expected to include: ait-testnet)"
                ((VIOLATION_COUNT++))
            fi
            check_database_isolation "$DATA_DIR/ait-testnet/chain.db" "ait-testnet"
        else
            log_warning "aitbc1 not accessible, skipping remote checks"
        fi
    elif [ "$hostname" = "aitbc1" ]; then
        # On aitbc1, check aitbc (mainnet)
        if ssh aitbc test -f "/etc/aitbc/blockchain.env" 2>/dev/null; then
            REMOTE_CHAINS=$(ssh aitbc 'cat /etc/aitbc/blockchain.env | grep "^supported_chains=" | cut -d"=" -f2')
            # Check if expected chain is in the supported chains list (handles comma-separated values)
            if [[ ",$REMOTE_CHAINS," == *",ait-mainnet,"* ]]; then
                log_success "aitbc supported_chains=$REMOTE_CHAINS (includes ait-mainnet)"
            else
                log_error "aitbc supported_chains=$REMOTE_CHAINS (expected to include: ait-mainnet)"
                ((VIOLATION_COUNT++))
            fi
            check_database_isolation "$DATA_DIR/ait-mainnet/chain.db" "ait-mainnet"
        else
            log_warning "aitbc not accessible, skipping remote checks"
        fi
    fi

    log "=== Chain Isolation Verification Completed ==="
    log "Total violations found: $VIOLATION_COUNT"

    if [ $VIOLATION_COUNT -gt 0 ]; then
        log_error "CHAIN ISOLATION VIOLATIONS DETECTED"
        exit 1
    else
        log_success "No chain isolation violations detected"
        exit 0
    fi
}

# Create log directory if needed
mkdir -p "$(dirname "$LOG_FILE")"

# Run verification
main
