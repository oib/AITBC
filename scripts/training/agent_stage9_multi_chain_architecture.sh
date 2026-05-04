#!/bin/bash

# OpenClaw AITBC Agent Training - Stage 9: Multi-Chain Architecture
# Agent-Centric Training for Multi-Chain OpenClaw Agents

set -e

# Source training library
source "$(dirname "$0")/training_lib.sh"

# Training configuration
TRAINING_STAGE="Stage 9: Multi-Chain Architecture (Agent-Centric)"
SCRIPT_NAME="agent_stage9_multi_chain_architecture"
CURRENT_LOG=$(init_logging "$SCRIPT_NAME")

# Setup traps for cleanup
setup_traps

# Agent configuration
AGENT_ID="agent_architect_$(date +%s)"
AGENT_TYPE="architect"
STAGE="stage9_multi_chain_architecture"
TRAINING_DATA="/opt/aitbc/docs/agent-training/stage9_multi_chain_architecture.json"
LOG_LEVEL="INFO"

# Logging function with millisecond precision
log_agent() {
    local level=$1
    local message=$2
    local timestamp=$(date '+%Y-%m-%d %H:%M:%S.%3N')
    echo "[$timestamp] [$level] Agent $AGENT_ID: $message" | tee -a "$CURRENT_LOG"
}

# 1. Agent Architecture Training
agent_architecture_training() {
    log_agent "INFO" "Starting agent architecture training for $AGENT_ID"
    log_agent "INFO" "Training data: $TRAINING_DATA"
    
    # Use OpenClaw CLI to train the agent
    if $CLI_PATH openclaw-training train agent \
        --agent-id "$AGENT_ID" \
        --stage "$STAGE" \
        --training-data "$TRAINING_DATA" \
        --log-level "$LOG_LEVEL"; then
        log_agent "SUCCESS" "Agent architecture training completed successfully"
    else
        log_agent "ERROR" "Agent architecture training failed"
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
    
    # Agent Architecture Training
    if agent_architecture_training; then
        log_agent "SUCCESS" "Architecture training completed"
    else
        log_agent "ERROR" "Architecture training failed"
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
