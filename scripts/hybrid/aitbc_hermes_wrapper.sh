#!/bin/bash
# AITBC + Hermes Hybrid Script System
# Clean separation: Shell (execution) + Hermes (reasoning)

set -e

# Configuration
AITBC_CLI="/opt/aitbc/aitbc-cli"
HERMES_CMD="hermes agent --agent main"
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

# Analyze output with Hermes
analyze_with_hermes() {
    local data="$@"
    log "INFO" "Analyzing with Hermes..."
    
    local analysis
    analysis=$(echo "$data" | $HERMES_CMD --message "Analyze this AITBC output and provide insights: $data" 2>&1)
    local exit_code=$?
    
    if [ $exit_code -eq 0 ]; then
        log "SUCCESS" "Hermes analysis completed"
        echo "$analysis"
        return 0
    else
        log "WARN" "Hermes analysis failed (non-critical)"
        echo "$analysis" >&2
        return 1
    fi
}

# Hybrid execution with optional analysis
hybrid_execute() {
    local cmd="$@"
    local use_hermes="${USE_HERMES:-false}"
    
    # Execute AITBC command
    local aitbc_output
    aitbc_output=$(execute_aitbc $cmd)
    local aitbc_exit=$?
    
    if [ $aitbc_exit -ne 0 ]; then
        return $aitbc_exit
    fi
    
    # Optionally analyze with Hermes
    if [ "$use_hermes" = "true" ]; then
        echo -e "${BLUE}=== Hermes Analysis ===${NC}"
        analyze_with_hermes "$aitbc_output"
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
            # Analyze existing data with Hermes
            local data="$@"
            analyze_with_hermes "$data"
            ;;
        hybrid)
            # Execute AITBC and analyze with Hermes
            USE_HERMES=true hybrid_execute "$@"
            ;;
        *)
            # Default: execute AITBC only
            hybrid_execute "$command" "$@"
            ;;
    esac
}

main "$@"
