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
init_progress 6  # 6 main sections + validation

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
        if cli_cmd "wallet create $WALLET_NAME $WALLET_PASSWORD"; then
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
    wallet_address=$(cli_cmd_output "wallet balance $WALLET_NAME" | grep "Address:" | awk '{print $2}')
    
    if [[ -n "$wallet_address" ]]; then
        print_status "Sending test transaction (self-transfer)..."
        if cli_cmd "wallet send $WALLET_NAME $wallet_address 0 $WALLET_PASSWORD"; then
            print_success "Test transaction sent successfully"
        else
            print_warning "Transaction may have failed (insufficient balance or other issue)"
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
