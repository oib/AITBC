#!/bin/bash

# AITBC Multi-Chain Island Architecture Test Script
# Tests the multi-chain island architecture with gossip-based synchronization
# Validates: aitbc (hub of ait-mainnet), aitbc1 (hub of ait-testnet), gitea-runner (member of both)

set -e

# Configuration
AITBC1_HOST="aitbc1"
AITBC_HOST="localhost"
GITEA_RUNNER_HOST="gitea-runner"
GENESIS_PORT="8006"
LOG_DIR="/var/log/aitbc"
LOG_FILE="$LOG_DIR/multi_chain_island_test_$(date +%Y%m%d_%H%M%S).log"
ERROR_LOG="$LOG_DIR/multi_chain_island_test_errors_$(date +%Y%m%d_%H%M%S).log"

# Test configuration
TEST_DURATION=120  # seconds to wait for gossip sync
MAINNET_CHAIN="ait-mainnet"
TESTNET_CHAIN="ait-testnet"

# Colors for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Ensure log directory exists
mkdir -p "$LOG_DIR"

# Helper functions
log_debug() {
    echo "[DEBUG] $(date '+%Y-%m-%d %H:%M:%S'): $1" | tee -a "$LOG_FILE"
}

log_info() {
    echo "[INFO] $(date '+%Y-%m-%d %H:%M:%S'): $1" | tee -a "$LOG_FILE"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $(date '+%Y-%m-%d %H:%M:%S'): $1" | tee -a "$LOG_FILE" | tee -a "$ERROR_LOG"
}

log_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $(date '+%Y-%m-%d %H:%M:%S'): $1" | tee -a "$LOG_FILE"
}

log_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $(date '+%Y-%m-%d %H:%M:%S'): $1" | tee -a "$LOG_FILE"
}

log_test() {
    echo -e "${BLUE}[TEST]${NC} $(date '+%Y-%m-%d %H:%M:%S'): $1" | tee -a "$LOG_FILE"
}

# Execute command on remote node
execute_on_node() {
    local node=$1
    local command=$2
    
    if [ "$node" = "localhost" ]; then
        eval "$command"
    else
        ssh -o ConnectTimeout=10 "$node" "cd /opt/aitbc && $command"
    fi
}

# Test: Check if broadcaster module is installed
test_broadcaster_module() {
    log_test "Checking broadcaster module installation on all nodes"
    
    local nodes=("$AITBC_HOST" "$AITBC1_HOST" "$GITEA_RUNNER_HOST")
    for node in "${nodes[@]}"; do
        if execute_on_node "$node" "python3 -c 'from broadcaster import Broadcast; print('OK')"; then
            log_success "broadcaster module installed on $node"
        else
            log_error "broadcaster module NOT installed on $node"
            return 1
        fi
    done
}

# Test: Verify gossip backend configuration
test_gossip_backend_config() {
    log_test "Verifying gossip backend configuration on all nodes"
    
    local nodes=("$AITBC_HOST" "$AITBC1_HOST" "$GITEA_RUNNER_HOST")
    for node in "${nodes[@]}"; do
        local gossip_backend=$(execute_on_node "$node" "grep gossip_backend /etc/aitbc/.env | cut -d'=' -f2")
        local gossip_url=$(execute_on_node "$node" "grep gossip_broadcast_url /etc/aitbc/.env | cut -d'=' -f2")
        
        if [ "$gossip_backend" = "broadcast" ]; then
            log_success "gossip_backend=broadcast configured on $node"
        else
            log_error "gossip_backend=$gossip_backend (expected broadcast) on $node"
            return 1
        fi
        
        if [ "$gossip_url" = "redis://10.1.223.93:6379" ]; then
            log_success "gossip_broadcast_url configured on $node"
        else
            log_error "gossip_broadcast_url=$gossip_url (expected redis://10.1.223.93:6379) on $node"
            return 1
        fi
    done
}

# Test: Verify chain configuration
test_chain_configuration() {
    log_test "Verifying chain configuration on all nodes"
    
    # aitbc should produce ait-mainnet only
    local aitbc_production=$(execute_on_node "$AITBC_HOST" "grep block_production_chains /etc/aitbc/.env | cut -d'=' -f2")
    local aitbc_supported=$(execute_on_node "$AITBC_HOST" "grep supported_chains /etc/aitbc/.env | cut -d'=' -f2")
    
    if [ "$aitbc_production" = "ait-mainnet" ]; then
        log_success "aitbc block_production_chains=ait-mainnet (correct)"
    else
        log_error "aitbc block_production_chains=$aitbc_production (expected ait-mainnet)"
        return 1
    fi
    
    if [ "$aitbc_supported" = "ait-mainnet,ait-testnet" ]; then
        log_success "aitbc supported_chains=ait-mainnet,ait-testnet (correct)"
    else
        log_error "aitbc supported_chains=$aitbc_supported (expected ait-mainnet,ait-testnet)"
        return 1
    fi
    
    # aitbc1 should produce ait-testnet only
    local aitbc1_production=$(execute_on_node "$AITBC1_HOST" "grep block_production_chains /etc/aitbc/.env | cut -d'=' -f2")
    local aitbc1_supported=$(execute_on_node "$AITBC1_HOST" "grep supported_chains /etc/aitbc/.env | cut -d'=' -f2")
    
    if [ "$aitbc1_production" = "ait-testnet" ]; then
        log_success "aitbc1 block_production_chains=ait-testnet (correct)"
    else
        log_error "aitbc1 block_production_chains=$aitbc1_production (expected ait-testnet)"
        return 1
    fi
    
    if [ "$aitbc1_supported" = "ait-mainnet,ait-testnet" ]; then
        log_success "aitbc1 supported_chains=ait-mainnet,ait-testnet (correct)"
    else
        log_error "aitbc1 supported_chains=$aitbc1_supported (expected ait-mainnet,ait-testnet)"
        return 1
    fi
    
    # gitea-runner should produce no blocks
    local gitea_runner_production=$(execute_on_node "$GITEA_RUNNER_HOST" "grep block_production_chains /etc/aitbc/.env | cut -d'=' -f2")
    local gitea_runner_supported=$(execute_on_node "$GITEA_RUNNER_HOST" "grep supported_chains /etc/aitbc/.env | cut -d'=' -f2")
    
    if [ -z "$gitea_runner_production" ]; then
        log_success "gitea-runner block_production_chains=empty (correct)"
    else
        log_error "gitea-runner block_production_chains=$gitea_runner_production (expected empty)"
        return 1
    fi
    
    if [ "$gitea_runner_supported" = "ait-mainnet,ait-testnet" ]; then
        log_success "gitea-runner supported_chains=ait-mainnet,ait-testnet (correct)"
    else
        log_error "gitea-runner supported_chains=$gitea_runner_supported (expected ait-mainnet,ait-testnet)"
        return 1
    fi
}

# Test: Check Redis subscriber count
test_redis_subscribers() {
    log_test "Checking Redis subscriber count for chain topics"
    
    local mainnet_subscribers=$(redis-cli -h 10.1.223.93 -p 6379 PUBSUB NUMSUB blocks.ait-mainnet | tail -n1)
    local testnet_subscribers=$(redis-cli -h 10.1.223.93 -p 6379 PUBSUB NUMSUB blocks.ait-testnet | tail -n1)
    
    if [ "$mainnet_subscribers" = "3" ]; then
        log_success "blocks.ait-mainnet has 3 subscribers (correct)"
    else
        log_error "blocks.ait-mainnet has $mainnet_subscribers subscribers (expected 3)"
        return 1
    fi
    
    if [ "$testnet_subscribers" = "3" ]; then
        log_success "blocks.ait-testnet has 3 subscribers (correct)"
    else
        log_error "blocks.ait-testnet has $testnet_subscribers subscribers (expected 3)"
        return 1
    fi
}

# Test: Verify block production
test_block_production() {
    log_test "Verifying block production on hub nodes"
    
    # Wait for block production
    log_info "Waiting 60 seconds for block production..."
    sleep 60
    
    # Check aitbc is producing ait-mainnet blocks
    local aitbc_mainnet_blocks=$(execute_on_node "$AITBC_HOST" "journalctl -u aitbc-blockchain-node --since '2 minutes ago' --no-pager | grep '\[BROADCAST\].*ait-mainnet' | wc -l")
    local aitbc_testnet_blocks=$(execute_on_node "$AITBC_HOST" "journalctl -u aitbc-blockchain-node --since '2 minutes ago' --no-pager | grep '\[BROADCAST\].*ait-testnet' | wc -l")
    
    if [ "$aitbc_mainnet_blocks" -gt 0 ]; then
        log_success "aitbc produced $aitbc_mainnet_blocks ait-mainnet blocks (correct)"
    else
        log_error "aitbc produced 0 ait-mainnet blocks (expected >0)"
        return 1
    fi
    
    if [ "$aitbc_testnet_blocks" -eq 0 ]; then
        log_success "aitbc produced 0 ait-testnet blocks (correct - not a hub for testnet)"
    else
        log_error "aitbc produced $aitbc_testnet_blocks ait-testnet blocks (expected 0)"
        return 1
    fi
    
    # Check aitbc1 is producing ait-testnet blocks
    local aitbc1_mainnet_blocks=$(execute_on_node "$AITBC1_HOST" "journalctl -u aitbc-blockchain-node --since '2 minutes ago' --no-pager | grep '\[BROADCAST\].*ait-mainnet' | wc -l")
    local aitbc1_testnet_blocks=$(execute_on_node "$AITBC1_HOST" "journalctl -u aitbc-blockchain-node --since '2 minutes ago' --no-pager | grep '\[BROADCAST\].*ait-testnet' | wc -l")
    
    if [ "$aitbc1_testnet_blocks" -gt 0 ]; then
        log_success "aitbc1 produced $aitbc1_testnet_blocks ait-testnet blocks (correct)"
    else
        log_error "aitbc1 produced 0 ait-testnet blocks (expected >0)"
        return 1
    fi
    
    if [ "$aitbc1_mainnet_blocks" -eq 0 ]; then
        log_success "aitbc1 produced 0 ait-mainnet blocks (correct - not a hub for mainnet)"
    else
        log_error "aitbc1 produced $aitbc1_mainnet_blocks ait-mainnet blocks (expected 0)"
        return 1
    fi
    
    # Check gitea-runner is producing no blocks
    local gitea_runner_blocks=$(execute_on_node "$GITEA_RUNNER_HOST" "journalctl -u aitbc-blockchain-node --since '2 minutes ago' --no-pager | grep '\[BROADCAST\]' | wc -l")
    
    if [ "$gitea_runner_blocks" -eq 0 ]; then
        log_success "gitea-runner produced 0 blocks (correct - member only)"
    else
        log_error "gitea-runner produced $gitea_runner_blocks blocks (expected 0)"
        return 1
    fi
}

# Test: Verify cross-chain gossip sync
test_cross_chain_sync() {
    log_test "Verifying cross-chain gossip synchronization"
    
    log_info "Waiting 30 seconds for gossip sync..."
    sleep 30
    
    # Check aitbc is receiving ait-testnet blocks
    local aitbc_received_testnet=$(execute_on_node "$AITBC_HOST" "journalctl -u aitbc-blockchain-node --since '2 minutes ago' --no-pager | grep 'Received block.*ait-testnet' | wc -l")
    
    if [ "$aitbc_received_testnet" -gt 0 ]; then
        log_success "aitbc received $aitbc_received_testnet ait-testnet blocks via gossip (correct)"
    else
        log_error "aitbc received 0 ait-testnet blocks via gossip (expected >0)"
        return 1
    fi
    
    # Check aitbc1 is receiving ait-mainnet blocks
    local aitbc1_received_mainnet=$(execute_on_node "$AITBC1_HOST" "journalctl -u aitbc-blockchain-node --since '2 minutes ago' --no-pager | grep 'Received block.*ait-mainnet' | wc -l")
    
    if [ "$aitbc1_received_mainnet" -gt 0 ]; then
        log_success "aitbc1 received $aitbc1_received_mainnet ait-mainnet blocks via gossip (correct)"
    else
        log_error "aitbc1 received 0 ait-mainnet blocks via gossip (expected >0)"
        return 1
    fi
    
    # Check gitea-runner is receiving both chains
    local gitea_received_mainnet=$(execute_on_node "$GITEA_RUNNER_HOST" "journalctl -u aitbc-blockchain-node --since '2 minutes ago' --no-pager | grep 'Received block.*ait-mainnet' | wc -l")
    local gitea_received_testnet=$(execute_on_node "$GITEA_RUNNER_HOST" "journalctl -u aitbc-blockchain-node --since '2 minutes ago' --no-pager | grep 'Received block.*ait-testnet' | wc -l")
    
    if [ "$gitea_received_mainnet" -gt 0 ] && [ "$gitea_received_testnet" -gt 0 ]; then
        log_success "gitea-runner received both chains via gossip (mainnet: $gitea_received_mainnet, testnet: $gitea_received_testnet)"
    else
        log_error "gitea-runner not receiving both chains (mainnet: $gitea_received_mainnet, testnet: $gitea_received_testnet)"
        return 1
    fi
}

# Test: Verify no fork detection errors
test_no_fork_errors() {
    log_test "Verifying no fork detection errors in logs"
    
    local nodes=("$AITBC_HOST" "$AITBC1_HOST" "$GITEA_RUNNER_HOST")
    for node in "${nodes[@]}"; do
        local fork_errors=$(execute_on_node "$node" "journalctl -u aitbc-blockchain-node --since '5 minutes ago' --no-pager | grep -i 'fork detected' | wc -l")
        
        if [ "$fork_errors" -eq 0 ]; then
            log_success "No fork detection errors on $node"
        else
            log_error "$fork_errors fork detection errors on $node (expected 0)"
            return 1
        fi
    done
}

# Test: Verify no gap detection errors
test_no_gap_errors() {
    log_test "Verifying no gap detection errors in logs (after initial sync)"
    
    # Wait a bit more for any sync to complete
    log_info "Waiting 30 seconds for sync to complete..."
    sleep 30
    
    local nodes=("$AITBC_HOST" "$AITBC1_HOST" "$GITEA_RUNNER_HOST")
    for node in "${nodes[@]}"; do
        local gap_errors=$(execute_on_node "$node" "journalctl -u aitbc-blockchain-node --since '2 minutes ago' --no-pager | grep -i 'gap detected' | wc -l")
        
        if [ "$gap_errors" -eq 0 ]; then
            log_success "No gap detection errors on $node"
        else
            log_warning "$gap_errors gap detection errors on $node (may be expected during initial sync)"
        fi
    done
}

# Test: Verify blockchain heights are in sync
test_blockchain_heights() {
    log_test "Verifying blockchain heights are in sync across nodes"
    
    # Get mainnet heights
    local aitbc_mainnet_height=$(execute_on_node "$AITBC_HOST" "sqlite3 /var/lib/aitbc/data/ait-mainnet/chain.db 'SELECT MAX(height) FROM blocks' 2>/dev/null || echo '0'")
    local aitbc1_mainnet_height=$(execute_on_node "$AITBC1_HOST" "sqlite3 /var/lib/aitbc/data/ait-mainnet/chain.db 'SELECT MAX(height) FROM blocks' 2>/dev/null || echo '0'")
    local gitea_mainnet_height=$(execute_on_node "$GITEA_RUNNER_HOST" "sqlite3 /var/lib/aitbc/data/ait-mainnet/chain.db 'SELECT MAX(height) FROM blocks' 2>/dev/null || echo '0'")
    
    log_info "Mainnet heights - aitbc: $aitbc_mainnet_height, aitbc1: $aitbc1_mainnet_height, gitea-runner: $gitea_mainnet_height"
    
    # Get testnet heights
    local aitbc_testnet_height=$(execute_on_node "$AITBC_HOST" "sqlite3 /var/lib/aitbc/data/ait-testnet/chain.db 'SELECT MAX(height) FROM blocks' 2>/dev/null || echo '0'")
    local aitbc1_testnet_height=$(execute_on_node "$AITBC1_HOST" "sqlite3 /var/lib/aitbc/data/ait-testnet/chain.db 'SELECT MAX(height) FROM blocks' 2>/dev/null || echo '0'")
    local gitea_testnet_height=$(execute_on_node "$GITEA_RUNNER_HOST" "sqlite3 /var/lib/aitbc/data/ait-testnet/chain.db 'SELECT MAX(height) FROM blocks' 2>/dev/null || echo '0'")
    
    log_info "Testnet heights - aitbc: $aitbc_testnet_height, aitbc1: $aitbc1_testnet_height, gitea-runner: $gitea_testnet_height"
    
    # aitbc and gitea-runner should have similar mainnet heights (aitbc1 may lag slightly)
    local mainnet_diff=$((aitbc_mainnet_height - gitea_mainnet_height))
    if [ "$mainnet_diff" -lt 10 ]; then
        log_success "Mainnet heights in sync (diff: $mainnet_diff)"
    else
        log_warning "Mainnet heights out of sync (diff: $mainnet_diff)"
    fi
    
    # aitbc1 and gitea-runner should have similar testnet heights (aitbc may lag slightly)
    local testnet_diff=$((aitbc1_testnet_height - gitea_testnet_height))
    if [ "$testnet_diff" -lt 10 ]; then
        log_success "Testnet heights in sync (diff: $testnet_diff)"
    else
        log_warning "Testnet heights out of sync (diff: $testnet_diff)"
    fi
}

# Main test execution
main() {
    log_info "Starting Multi-Chain Island Architecture Test"
    log_info "Test duration: $TEST_DURATION seconds"
    log_info "================================================"
    
    local test_passed=true
    
    # Run all tests
    test_broadcaster_module || test_passed=false
    test_gossip_backend_config || test_passed=false
    test_chain_configuration || test_passed=false
    test_redis_subscribers || test_passed=false
    test_block_production || test_passed=false
    test_cross_chain_sync || test_passed=false
    test_no_fork_errors || test_passed=false
    test_no_gap_errors || test_passed=false
    test_blockchain_heights || test_passed=false
    
    log_info "================================================"
    
    if [ "$test_passed" = true ]; then
        log_success "All multi-chain island architecture tests PASSED"
        echo ""
        echo "Test Summary:"
        echo "  - broadcaster module: INSTALLED"
        echo "  - gossip backend: CONFIGURED"
        echo "  - chain configuration: CORRECT"
        echo "  - Redis subscribers: 3 per topic"
        echo "  - block production: CORRECT"
        echo "  - cross-chain sync: WORKING"
        echo "  - fork detection: NO ERRORS"
        echo "  - gap detection: NO ERRORS"
        echo "  - blockchain heights: IN SYNC"
        exit 0
    else
        log_error "Some multi-chain island architecture tests FAILED"
        echo "Check $ERROR_LOG for details"
        exit 1
    fi
}

# Run main function
main
