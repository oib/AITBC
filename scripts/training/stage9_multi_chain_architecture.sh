#!/bin/bash

# hermes AITBC Training - Stage 9: Multi-Chain Architecture
# Cross-chain operations, multi-chain deployment, and interoperability
# Uses Python-based training setup to execute JSON-defined operations

set -e

# Source training library
source "$(dirname "$0")/training_lib.sh"

# Training configuration
TRAINING_STAGE="Stage 9: Multi-Chain Architecture"
SCRIPT_NAME="stage9_multi_chain_architecture"
CURRENT_LOG=$(init_logging "$SCRIPT_NAME")

# Setup traps for cleanup
setup_traps

# Total steps for progress tracking
init_progress 1

# Stage information
print_header "$TRAINING_STAGE"
print_status "Multi-chain architecture and cross-chain operations"
print_status "Skills: Cross-chain transactions, multi-chain deployment, interoperability"
echo

# Execute stage from JSON definition
execute_stage_from_json() {
    local stage_num=9
    local json_file="$SCRIPT_DIR/../docs/agent-training/stage${stage_num}_multi_chain_architecture.json"
    
    print_status "Executing stage from JSON definition: $json_file"
    
    if [ ! -f "$json_file" ]; then
        print_error "Stage JSON file not found: $json_file"
        return 1
    fi
    
    # Use Python training setup to execute stage
    cd "$AITBC_DIR"
    if python3 -m aitbc.training_setup.cli run-stage --json "$json_file" 2>&1 | tee -a "$CURRENT_LOG"; then
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
        output_stage_learnings 9 "Multi-Chain Architecture" \
            "./aitbc-cli cross-chain send|./aitbc-cli multi-chain deploy" \
            "Cross-chain transaction format|Multi-chain deployment|Interoperability" \
            "/opt/aitbc/apps/blockchain-node" \
            "Multi-chain architecture|Cross-chain operations|Interoperability"
        
        return 0
    else
        print_error "$TRAINING_STAGE failed"
        return 1
    fi
}

# Run main function
main
