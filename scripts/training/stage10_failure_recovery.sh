#!/bin/bash

# hermes AITBC Training - Stage 10: Failure Recovery & Production Operations
# Transaction failure debugging, node recovery, production monitoring, backup procedures
# Uses Python-based training setup to execute JSON-defined operations

set -e

# Source training library
source "$(dirname "$0")/training_lib.sh"

# Training configuration
TRAINING_STAGE="Stage 10: Failure Recovery & Production Operations"
SCRIPT_NAME="stage10_failure_recovery"
CURRENT_LOG=$(init_logging "$SCRIPT_NAME")

# Setup traps for cleanup
setup_traps

# Total steps for progress tracking
init_progress 1

# Stage information
print_header "$TRAINING_STAGE"
print_status "Failure recovery, production monitoring, and advanced debugging"
print_status "Skills: Transaction debugging, node recovery, monitoring, backup procedures"
echo

# Execute stage from JSON definition
execute_stage_from_json() {
    local stage_num=10
    local json_file="${REPO_ROOT}/docs/agent-training/stage${stage_num}_failure_recovery.json"
    
    print_status "Executing stage from JSON definition: $json_file"
    
    if [ ! -f "$json_file" ]; then
        print_error "Stage JSON file not found: $json_file"
        return 1
    fi
    
    # Use Python training setup to execute stage
    cd "$AITBC_DIR"
    if python3 -m aitbc.training_setup.cli run-stage "$json_file" 2>&1 | tee -a "$CURRENT_LOG"; then
        print_success "Stage $stage_num executed successfully"
        return 0
    else
        print_error "Stage $stage_num execution failed"
        return 1
    fi
}

# Main execution
main() {
    print_status "Starting $TRAINING_STAGE"
    echo
    
    if execute_stage_from_json; then
        print_success "$TRAINING_STAGE completed"
        
        # Output learnings for skill update
        output_stage_learnings 10 "Failure Recovery" \
            "aitbc-cli blockchain transaction <tx_id> --verbose|aitbc-cli wallet nonce <wallet>|curl -s http://localhost:8006/health|aitbc-cli blockchain sync --status|systemctl status aitbc-blockchain-node.service|aitbc-cli wallet export <wallet> --backup|aitbc-cli blockchain mempool|aitbc-cli blockchain transaction <tx_id> --trace|journalctl -fu aitbc-*|tail -f /var/log/aitbc/blockchain-node.log" \
            "Nonce too low: check current nonce and pending transactions|Insufficient funds: check balance and fees before transaction|Node health: check /health endpoint and systemctl status|Wallet backup: export wallet and backup keystore file|Network partition: check peer connections and sync status|Log monitoring: use journalctl -fu aitbc-* or grep ERROR on /var/log/aitbc/" \
            "/var/lib/aitbc/keystore|/var/log/aitbc|/opt/aitbc/backups|/etc/aitbc/.env|/etc/aitbc/node.env" \
            "Transaction failure debugging|Node recovery procedures|Production monitoring|Backup and restore|Mempool inspection|Network partition handling"
        
        return 0
    else
        print_error "$TRAINING_STAGE failed"
        return 1
    fi
}

# Run main function
main
