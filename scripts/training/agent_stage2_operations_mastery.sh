#!/bin/bash

# Agent AITBC Agent Training - Stage 2: Operations Mastery
# Agent-Centric Training for Agent Agents on AITBC Operations

set -e

# Source scenario configuration
if [ -f "/etc/aitbc/.env.scenario" ]; then
    source /etc/aitbc/.env.scenario
    echo "✅ Loaded scenario configuration from /etc/aitbc/.env.scenario"
else
    # Fallback to defaults
    export HUB_URL="${HUB_URL:-https://hub.aitbc.bubuit.net}"
    export SHOP_URL="${SHOP_URL:-https://aitbc3.aitbc.bubuit.net}"
    export BLOCKCHAIN_RPC="${BLOCKCHAIN_RPC:-http://localhost:8202}"
    echo "⚠️  Using default configuration (env file not found)"
fi

# Source training library
source "$(dirname "$0")/training_lib.sh"

# Training configuration
TRAINING_STAGE="Stage 2: Operations Mastery (Agent-Centric)"
SCRIPT_NAME="agent_stage2_operations_mastery"
CURRENT_LOG=$(init_logging "$SCRIPT_NAME")

# Setup traps for cleanup
setup_traps

# Agent configuration
AGENT_ID="agent_operations_$(date +%s)"
AGENT_TYPE="general"
STAGE="stage2_operations_mastery"
TRAINING_DATA="/opt/aitbc/docs/agent-training/stage2_operations_mastery.json"
LOG_LEVEL="INFO"

# Logging function with millisecond precision
log_agent() {
    local level=$1
    local message=$2
    local timestamp=$(date '+%Y-%m-%d %H:%M:%S.%3N')
    echo "[$timestamp] [$level] Agent $AGENT_ID: $message" | tee -a "$CURRENT_LOG"
}

# 1. Agent Operations Training
agent_operations_training() {
    log_agent "INFO" "Starting agent operations training for $AGENT_ID"
    log_agent "INFO" "Training data: $TRAINING_DATA"

    # Use Agent CLI to train the agent
    if $CLI_PATH agent-training train agent \
        --agent-id "$AGENT_ID" \
        --stage "$STAGE" \
        --training-data "$TRAINING_DATA" \
        --log-level "$LOG_LEVEL"; then
        log_agent "SUCCESS" "Agent operations training completed successfully"
    else
        log_agent "ERROR" "Agent operations training failed"
        return 1
    fi
}

# 2. Agent Validation
agent_validation() {
    log_agent "INFO" "Starting agent validation for stage $STAGE"

    # Use Agent CLI to validate the agent
    if $CLI_PATH agent-training train validate \
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

    # Use Agent CLI to certify the agent
    if $CLI_PATH agent-training train certify \
        --agent-id "$AGENT_ID"; then
        log_agent "SUCCESS" "Agent certification completed"
    else
        log_agent "WARNING" "Agent certification not yet complete (other stages pending)"
    fi
}

# Main execution
main() {
    log_agent "INFO" "Starting $TRAINING_STAGE"

    # Agent Operations Training
    if agent_operations_training; then
        log_agent "SUCCESS" "Operations training completed"
    else
        log_agent "ERROR" "Operations training failed"
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
