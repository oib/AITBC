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

    # The fleet is inconsistent about the spelling: node0 uses lowercase
    # supported_chains=, node1/node2/hub2 use SUPPORTED_CHAINS=, and hub declares
    # neither (only CHAIN_ID). Accept either, and treat "not declared" as
    # unknown rather than as a violation -- a missing key is a config gap, not
    # evidence that this node is serving someone else's chain.
    supported_chains=$(grep -iE "^supported_chains=" "$blockchain_env" | head -1 | cut -d'=' -f2- | tr -d '"'"'"'"')

    if [ -z "$supported_chains" ]; then
        log_warning "$node_name declares no supported_chains/SUPPORTED_CHAINS in $blockchain_env; skipping list check"
        return 0
    fi

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

    # Ask the node which chain it is on instead of guessing from its hostname.
    # The previous version mapped the hostnames "aitbc" and "aitbc1" to
    # ait-mainnet/ait-testnet and fell back to ait-mainnet for anything else.
    # No host in the fleet is named either of those any more, and the live chain
    # is ait-hub.aitbc.bubuit.net -- so every node took the fallback and was
    # checked against a chain it does not serve, reporting a violation every run.
    local hostname=$(hostname)
    local expected_chain=""
    expected_chain=$(grep -iE "^chain_id=" /etc/aitbc/blockchain.env 2>/dev/null | head -1 | cut -d'=' -f2- | tr -d '"'"'"'"')

    if [ -z "$expected_chain" ]; then
        log_error "No CHAIN_ID in /etc/aitbc/blockchain.env; cannot determine which chain $hostname should serve"
        exit 1
    fi

    log "Running on node: $hostname (expected chain: $expected_chain)"

    # Check local node configuration
    check_node_configuration "$hostname" "/etc/aitbc/blockchain.env" "$expected_chain"
    check_database_isolation "$DATA_DIR/$expected_chain/chain.db" "$expected_chain"

    # The cross-node checks that used to live here shelled out to `ssh aitbc`
    # and `ssh aitbc1` -- hosts that no longer exist -- and would in any case not
    # work from the sandboxed systemd unit that now runs this. Each node verifies
    # itself; the timer runs on all of them.

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
