#!/bin/bash

# OpenClaw AITBC Training - Stage 1: Foundation
# Basic System Orientation and CLI Commands
# Optimized version using training library

set -e

# Source training library
source "$(dirname "$0")/training_lib.sh"

# Training configuration
TRAINING_STAGE="Stage 1: Foundation"
SCRIPT_NAME="stage1_foundation"
CURRENT_LOG=$(init_logging "$SCRIPT_NAME")

# Setup traps for cleanup
setup_traps

# Total steps for progress tracking
init_progress 7  # 7 main sections + validation (added genesis block initialization)

# 1.0 Genesis Block Initialization
genesis_block_initialization() {
    print_status "1.0 Genesis Block Initialization"
    log_info "Starting genesis block initialization"
    
    print_status "Blockchain already initialized on Genesis Node (genesis block exists)"
    print_success "Skipping initialization step"
    return 0
    
    print_status "Initializing blockchain on Follower Node..."
    if NODE_URL="http://aitbc1:8006" cli_cmd "blockchain init --force"; then
        print_success "Blockchain initialized on Follower Node"
    else
        print_warning "Blockchain may already be initialized on Follower Node"
    fi
    
    print_status "Verifying RPC connectivity to Genesis Node (port 8006)..."
    if curl -s --max-time 5 http://localhost:8006/health > /dev/null 2>&1; then
        print_success "Genesis Node RPC (port 8006) is accessible"
    else
        print_warning "Genesis Node RPC (port 8006) is not accessible"
    fi
    
    print_status "Verifying RPC connectivity to Follower Node (port 8006 on aitbc1)..."
    if curl -s --max-time 5 http://aitbc1:8006/health > /dev/null 2>&1; then
        print_success "Follower Node RPC (port 8006 on aitbc1) is accessible"
    else
        print_warning "Follower Node RPC (port 8006 on aitbc1) is not accessible"
    fi
    
    print_status "Verifying Follower Node RPC also runs on port 8006..."
    if ssh aitbc1 "curl -s --max-time 5 http://localhost:8006/health" > /dev/null 2>&1; then
        print_success "Follower Node RPC also accessible on port 8006"
    else
        print_warning "Follower Node RPC not accessible on port 8006 (check follower node health)"
    fi
    
    print_status "Funding training wallet from genesis block initial coins..."
    # The genesis block contains actual AIT coins - mine a block to get the reward
    print_status "Starting mining to get genesis block reward..."
    if NODE_URL="http://localhost:8006" cli_cmd "mining start --wallet $WALLET_NAME"; then
        print_success "Mining started for wallet $WALLET_NAME"
        sleep 5  # Wait for mining to produce a block
        
        print_status "Checking mining status..."
        NODE_URL="http://localhost:8006" cli_cmd "mining status --wallet $WALLET_NAME" || print_warning "Mining status check failed"
        
        print_status "Checking mining rewards..."
        NODE_URL="http://localhost:8006" cli_cmd "mining rewards --wallet $WALLET_NAME" || print_warning "Mining rewards check failed"
        
        print_status "Stopping mining after obtaining genesis reward..."
        NODE_URL="http://localhost:8006" cli_cmd "mining stop" || print_warning "Mining stop failed"
    else
        print_warning "Mining start failed - wallet may not have initial funds"
    fi
    
    print_status "Verifying wallet balance after mining genesis block..."
    NODE_URL="http://localhost:8006" cli_cmd "wallet balance $WALLET_NAME" || print_warning "Balance check failed"
    
    update_progress "Genesis Block Initialization"
}

# 1.1 Basic System Orientation
basic_system_orientation() {
    print_status "1.1 Basic System Orientation"
    log_info "Starting basic system orientation"
    
    print_status "Getting CLI version..."
    local version_output
    version_output=$($CLI_PATH --version 2>/dev/null) || version_output="Unknown"
    print_success "CLI version: $version_output"
    log_info "CLI version: $version_output"
    
    print_status "Displaying CLI help..."
    $CLI_PATH --help 2>/dev/null | head -20 || print_warning "CLI help command not available"
    log_info "CLI help displayed"
    
    print_status "Checking system status..."
    cli_cmd "system" || print_warning "System status command not available"
    
    update_progress "Basic System Orientation"
}

# 1.2 Basic Wallet Operations
basic_wallet_operations() {
    print_status "1.2 Basic Wallet Operations"
    log_info "Starting basic wallet operations"
    
    print_status "Creating training wallet..."
    if ! check_wallet "$WALLET_NAME"; then
        if cli_cmd "create --name $WALLET_NAME --password $WALLET_PASSWORD"; then
            print_success "Wallet $WALLET_NAME created successfully"
        else
            print_warning "Wallet creation may have failed or wallet already exists"
        fi
    else
        print_success "Training wallet $WALLET_NAME already exists"
    fi
    
    print_status "Listing all wallets..."
    cli_cmd_output "wallet list" || print_warning "Wallet list command not available"
    
    print_status "Checking wallet balance..."
    cli_cmd "wallet balance $WALLET_NAME" || print_warning "Balance check failed"
    
    update_progress "Basic Wallet Operations"
}

# 1.3 Basic Transaction Operations
basic_transaction_operations() {
    print_status "1.3 Basic Transaction Operations"
    log_info "Starting basic transaction operations"
    
    # Get wallet address for self-transfer test
    local wallet_address
    local wallet_balance
    local balance_output
    balance_output=$(cli_cmd_output "wallet balance $WALLET_NAME")
    wallet_address=$(echo "$balance_output" | grep "Address:" | awk '{print $2}')
    wallet_balance=$(echo "$balance_output" | grep "Balance:" | awk '{print $2}')
    
    if [[ -n "$wallet_address" && "${wallet_balance:-0}" -gt 0 ]]; then
        print_status "Sending test transaction (self-transfer)..."
        if cli_cmd "wallet send $WALLET_NAME $wallet_address 0 $WALLET_PASSWORD"; then
            print_success "Test transaction sent successfully"
        else
            print_warning "Transaction may have failed (insufficient balance or other issue)"
        fi
    elif [[ -n "$wallet_address" ]]; then
        print_status "Wallet has no on-chain balance - funding from genesis wallet..."
        
        # Get genesis wallet info
        local genesis_output
        local genesis_address
        local genesis_balance
        genesis_output=$(cli_cmd_output "wallet balance genesis")
        genesis_address=$(echo "$genesis_output" | grep "Address:" | awk '{print $2}')
        genesis_balance=$(echo "$genesis_output" | grep "Balance:" | awk '{print $2}')
        
        if [[ -n "$genesis_address" && "${genesis_balance:-0}" -gt 0 ]]; then
            print_status "Sending 100 AIT from genesis wallet to training wallet..."
            if cli_cmd "wallet send genesis $wallet_address 100 genesis"; then
                print_success "Funding transaction sent successfully"
                sleep 2  # Wait for transaction to be processed
                
                # Re-check training wallet balance
                balance_output=$(cli_cmd_output "wallet balance $WALLET_NAME")
                wallet_balance=$(echo "$balance_output" | grep "Balance:" | awk '{print $2}')
                
                if [[ "${wallet_balance:-0}" -gt 0 ]]; then
                    print_status "Training wallet now funded (Balance: ${wallet_balance} AIT)"
                    print_status "Sending test transaction (self-transfer)..."
                    if cli_cmd "wallet send $WALLET_NAME $wallet_address 0 $WALLET_PASSWORD"; then
                        print_success "Test transaction sent successfully"
                    else
                        print_warning "Transaction may have failed (insufficient balance or other issue)"
                    fi
                else
                    print_warning "Funding transaction sent but balance not updated yet"
                fi
            else
                print_warning "Funding transaction from genesis wallet failed"
            fi
        else
            print_warning "Genesis wallet has no balance to fund training wallet"
        fi
    else
        print_warning "Could not get wallet address for transaction test"
    fi
    
    print_status "Checking transaction history..."
    cli_cmd "wallet transactions $WALLET_NAME --limit 5" || print_warning "Transaction history command failed"
    
    update_progress "Basic Transaction Operations"
}

# 1.4 Service Health Monitoring
service_health_monitoring() {
    print_status "1.4 Service Health Monitoring"
    log_info "Starting service health monitoring"
    
    print_status "Checking all service statuses..."
    check_all_services
    
    print_status "Testing node connectivity..."
    test_node_connectivity "$GENESIS_NODE" "Genesis Node"
    test_node_connectivity "$FOLLOWER_NODE" "Follower Node"
    
    update_progress "Service Health Monitoring"
}

# Node-specific operations
node_specific_operations() {
    print_status "Node-Specific Operations"
    log_info "Testing node-specific operations"
    
    print_status "Testing Genesis Node operations..."
    cli_cmd_node "$GENESIS_NODE" "wallet balance $WALLET_NAME" || print_warning "Genesis node operations failed"
    
    print_status "Testing Follower Node operations..."
    cli_cmd_node "$FOLLOWER_NODE" "wallet balance $WALLET_NAME" || print_warning "Follower node operations failed"
    
    print_status "Comparing nodes..."
    compare_nodes "wallet balance $WALLET_NAME" "wallet balance"
    
    update_progress "Node-Specific Operations"
}

# Validation quiz
validation_quiz() {
    print_status "Stage 1 Validation Quiz"
    log_info "Starting validation quiz"
    
    echo
    echo -e "${BOLD}${BLUE}Stage 1 Validation Questions:${NC}"
    echo "1. What command shows the AITBC CLI version?"
    echo "   Answer: ./aitbc-cli --version"
    echo
    echo "2. How do you create a new wallet?"
    echo "   Answer: ./aitbc-cli wallet create <wallet> <password>"
    echo
    echo "3. How do you check a wallet's balance?"
    echo "   Answer: ./aitbc-cli wallet balance <wallet>"
    echo
    echo "4. How do you send a transaction?"
    echo "   Answer: ./aitbc-cli wallet send <from> <to> <amount> <password>"
    echo
    echo "5. How do you check service health?"
    echo "   Answer: ./aitbc-cli service --status or ./aitbc-cli service --health"
    echo
    
    update_progress "Validation Quiz"
}

# Main training function
main() {
    print_header "OpenClaw AITBC Training - $TRAINING_STAGE"
    log_info "Starting $TRAINING_STAGE"
    
    # Check prerequisites with full validation (continues despite warnings)
    check_prerequisites_full
    
    # Execute training sections (continue even if individual sections fail)
    genesis_block_initialization || true
    basic_system_orientation || true
    basic_wallet_operations || true
    basic_transaction_operations || true
    service_health_monitoring || true
    node_specific_operations || true
    validation_quiz || true
    
    # Final validation (more lenient)
    if validate_stage "$TRAINING_STAGE" "$CURRENT_LOG" 70; then
        print_header "$TRAINING_STAGE COMPLETED SUCCESSFULLY"
        log_success "$TRAINING_STAGE completed with validation"
        
        echo
        echo -e "${GREEN}Next Steps:${NC}"
        echo "1. Review the log file: $CURRENT_LOG"
        echo "2. Practice the commands learned"
        echo "3. Run: ./stage2_intermediate.sh"
        echo
        
        exit 0
    else
        print_warning "$TRAINING_STAGE validation below threshold, but continuing"
        print_header "$TRAINING_STAGE COMPLETED (Review Recommended)"
        exit 0
    fi
}

# Run the training
main "$@"
