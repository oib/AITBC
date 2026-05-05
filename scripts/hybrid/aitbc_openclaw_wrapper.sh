#!/bin/bash
# AITBC + OpenClaw Hybrid Script System
# Clean separation: Shell (execution) + OpenClaw (reasoning)

set -e

# Configuration
AITBC_CLI="/opt/aitbc/aitbc-cli"
OPENCLAW_CMD="openclaw agent --agent main"
LOG_DIR="/var/log/aitbc/hybrid"
mkdir -p "$LOG_DIR"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Logging function
log() {
    local level="$1"
    shift
    local message="$@"
    local timestamp=$(date -Iseconds)
    echo -e "${timestamp} [${level}] ${message}" | tee -a "$LOG_DIR/hybrid.log"
}

# Execute AITBC CLI command
execute_aitbc() {
    local cmd="$@"
    log "INFO" "Executing AITBC: $cmd"
    
    cd /opt/aitbc
    local output
    output=$(./aitbc-cli $cmd 2>&1)
    local exit_code=$?
    
    if [ $exit_code -eq 0 ]; then
        log "SUCCESS" "AITBC command succeeded"
        echo "$output"
        return 0
    else
        log "ERROR" "AITBC command failed with exit code $exit_code"
        echo "$output" >&2
        return $exit_code
    fi
}

# Analyze output with OpenClaw
analyze_with_openclaw() {
    local data="$@"
    log "INFO" "Analyzing with OpenClaw..."
    
    local analysis
    analysis=$(echo "$data" | $OPENCLAW_CMD --message "Analyze this AITBC output and provide insights: $data" 2>&1)
    local exit_code=$?
    
    if [ $exit_code -eq 0 ]; then
        log "SUCCESS" "OpenClaw analysis completed"
        echo "$analysis"
        return 0
    else
        log "WARN" "OpenClaw analysis failed (non-critical)"
        echo "$analysis" >&2
        return 1
    fi
}

# Hybrid execution with optional analysis
hybrid_execute() {
    local cmd="$@"
    local use_openclaw="${USE_OPENCLAW:-false}"
    
    # Execute AITBC command
    local aitbc_output
    aitbc_output=$(execute_aitbc $cmd)
    local aitbc_exit=$?
    
    if [ $aitbc_exit -ne 0 ]; then
        return $aitbc_exit
    fi
    
    # Optionally analyze with OpenClaw
    if [ "$use_openclaw" = "true" ]; then
        echo -e "${BLUE}=== OpenClaw Analysis ===${NC}"
        analyze_with_openclaw "$aitbc_output"
    fi
    
    return 0
}

# Main CLI interface
main() {
    local command="$1"
    shift || true
    
    case "$command" in
        exec)
            # Execute AITBC command only
            execute_aitbc "$@"
            ;;
        analyze)
            # Analyze existing data with OpenClaw
            local data="$@"
            analyze_with_openclaw "$data"
            ;;
        hybrid)
            # Execute AITBC and analyze with OpenClaw
            USE_OPENCLAW=true hybrid_execute "$@"
            ;;
        *)
            # Default: execute AITBC only
            hybrid_execute "$command" "$@"
            ;;
    esac
}

main "$@"
