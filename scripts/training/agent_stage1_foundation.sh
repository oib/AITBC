#!/bin/bash

# OpenClaw AITBC Agent Training - Stage 1: Foundation
# Agent-Centric Training for OpenClaw Agents

set -e

# Training configuration
TRAINING_STAGE="Stage 1: Foundation (Agent-Centric)"
SCRIPT_NAME="agent_stage1_foundation"
LOG_DIR="/var/log/aitbc"
SCRIPT_LOG="$LOG_DIR/training_${SCRIPT_NAME}.log"

# Agent configuration
AGENT_ID="agent_foundation_$(date +%s)"
AGENT_TYPE="general"
STAGE="stage1_foundation"
TRAINING_DATA="/opt/aitbc/docs/agent-training/stage1_foundation.json"
LOG_LEVEL="INFO"
CLI_PATH="${CLI_PATH:-/opt/aitbc/aitbc-cli}"

# Create log directory
mkdir -p "$LOG_DIR"

# Initialize logging (don't truncate, append instead)
echo "" >> "$SCRIPT_LOG"
echo "========================================" >> "$SCRIPT_LOG"
echo "$TRAINING_STAGE" >> "$SCRIPT_LOG"
echo "Started: $(date)" >> "$SCRIPT_LOG"
echo "Agent ID: $AGENT_ID" >> "$SCRIPT_LOG"
echo "========================================" >> "$SCRIPT_LOG"

# Logging function with millisecond precision
log_agent() {
    local level=$1
    local message=$2
    local timestamp=$(date '+%Y-%m-%d %H:%M:%S.%3N')
    echo "[$timestamp] [$level] Agent $AGENT_ID: $message" | tee -a "$SCRIPT_LOG"
}

# 1. Agent Specialized Training
agent_specialized_training() {
    log_agent "INFO" "Starting agent foundation training for $AGENT_ID"
    log_agent "INFO" "Training data: $TRAINING_DATA"
    
    # Use OpenClaw CLI to train the agent
    if $CLI_PATH openclaw-training train agent \
        --agent-id "$AGENT_ID" \
        --stage "$STAGE" \
        --training-data "$TRAINING_DATA" \
        --log-level "$LOG_LEVEL"; then
        log_agent "SUCCESS" "Agent foundation training completed successfully"
        
        # Also log operation details to script log
        if [ -f "$CURRENT_LOG" ]; then
            echo "" >> "$CURRENT_LOG"
            echo "=== Training Operation Details ===" >> "$CURRENT_LOG"
            # Get the agent log file from CLI output or construct it
            agent_log=$(ls -t /var/log/aitbc/agent-training/agent_${AGENT_ID}_${STAGE}_*.log 2>/dev/null | head -1)
            if [ -f "$agent_log" ]; then
                cat "$agent_log" >> "$CURRENT_LOG"
            fi
        fi
    else
        log_agent "ERROR" "Agent foundation training failed"
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
    
    # Agent Foundation Training
    if agent_specialized_training; then
        log_agent "SUCCESS" "Foundation training completed"
    else
        log_agent "ERROR" "Foundation training failed"
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
    
    # Append agent log details to script log
    echo "" >> "$SCRIPT_LOG"
    echo "=== Training Operation Details ===" >> "$SCRIPT_LOG"
    agent_log=$(ls -t /var/log/aitbc/agent-training/agent_${AGENT_ID}_${STAGE}_*.log 2>/dev/null | head -1)
    if [ -f "$agent_log" ]; then
        cat "$agent_log" >> "$SCRIPT_LOG"
    fi
    echo "=== End Training Operation Details ===" >> "$SCRIPT_LOG"
    
    echo ""
    echo "========================================"
    echo "$TRAINING_STAGE COMPLETED SUCCESSFULLY"
    echo "========================================"
    echo ""
    echo "Agent ID: $AGENT_ID"
    echo "Training Log: $SCRIPT_LOG"
    echo "Agent Training Log: /var/log/aitbc/agent-training/"
    echo ""
}

# Run main
main
