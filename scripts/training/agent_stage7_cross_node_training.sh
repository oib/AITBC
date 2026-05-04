#!/bin/bash

# OpenClaw AITBC Agent Training - Stage 7: Cross-Node Training
# Agent-Centric Training for OpenClaw Agents on AITBC Operations

set -e

# Source training library
source "$(dirname "$0")/training_lib.sh"

# Training configuration
TRAINING_STAGE="Stage 7: Cross-Node Training (Agent-Centric)"
SCRIPT_NAME="agent_stage7_cross_node_training"
CURRENT_LOG=$(init_logging "$SCRIPT_NAME")

# Setup traps for cleanup
setup_traps

# Agent configuration
AGENT_ID="agent_crossnode_$(date +%s)"
AGENT_TYPE="coordinator"
STAGE="stage7_cross_node_training"
TRAINING_DATA="/opt/aitbc/docs/agent-training/stage7_cross_node_training.json"
LOG_LEVEL="INFO"

# Logging function with millisecond precision
log_agent() {
    local level=$1
    local message=$2
    local timestamp=$(date '+%Y-%m-%d %H:%M:%S.%3N')
    echo "[$timestamp] [$level] Agent $AGENT_ID: $message" | tee -a "$CURRENT_LOG"
}

# 1. Agent Cross-Node Training
agent_crossnode_training() {
    log_agent "INFO" "Starting agent cross-node training for $AGENT_ID"
    log_agent "INFO" "Training data: $TRAINING_DATA"
    
    # Use OpenClaw CLI to train the agent
    if $CLI_PATH openclaw-training train agent \
        --agent-id "$AGENT_ID" \
        --stage "$STAGE" \
        --training-data "$TRAINING_DATA" \
        --log-level "$LOG_LEVEL"; then
        log_agent "SUCCESS" "Agent cross-node training completed successfully"
    else
        log_agent "ERROR" "Agent cross-node training failed"
        return 1
    fi
}

# 2. Agent Validation
agent_validation() {
    log_agent "INFO" "Starting agent validation for stage $STAGE"
    
    # Use OpenClaw CLI to validate the agent
    if $CLI_PATH openclaw-training train validate \
        --agent-id "$AGENT_ID" \
        --stage "$STAGE"; then
        log_agent "SUCCESS" "Agent validation passed"
    else
        log_agent "ERROR" "Agent validation failed"
        return 1
    fi
}

# 3. Agent Certification
agent_certification() {
    log_agent "INFO" "Starting agent certification"
    
    # Use OpenClaw CLI to certify the agent
    if $CLI_PATH openclaw-training train certify \
        --agent-id "$AGENT_ID"; then
        log_agent "SUCCESS" "Agent certification completed"
    else
        log_agent "WARNING" "Agent certification not yet complete (other stages pending)"
    fi
}

# Main execution
main() {
    log_agent "INFO" "Starting $TRAINING_STAGE"
    
    # Agent Cross-Node Training
    if agent_crossnode_training; then
        log_agent "SUCCESS" "Cross-node training completed"
    else
        log_agent "ERROR" "Cross-node training failed"
        exit 1
    fi
    
    # Agent Validation
    if agent_validation; then
        log_agent "SUCCESS" "Validation completed"
    else
        log_agent "ERROR" "Validation failed"
        exit 1
    fi
    
    # Agent Certification
    agent_certification
    
    log_agent "INFO" "$TRAINING_STAGE completed successfully"
    
    echo ""
    echo "========================================"
    echo "$TRAINING_STAGE COMPLETED SUCCESSFULLY"
    echo "========================================"
    echo ""
    echo "Agent ID: $AGENT_ID"
    echo "Training Log: $CURRENT_LOG"
    echo "Agent Training Log: /var/log/aitbc/agent-training/"
    echo ""
}

# Run main
main
