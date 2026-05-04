#!/bin/bash

# OpenClaw AITBC Training - Common Library
# Shared functions and utilities for all training stage scripts

# Version: 1.0
# Last Updated: 2026-04-02

TRAINING_LIB_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${TRAINING_LIB_DIR}/../.." && pwd)"

# ============================================================================
# CONFIGURATION
# ============================================================================

# Default configuration (can be overridden)
export CLI_PATH="${CLI_PATH:-${REPO_ROOT}/aitbc-cli}"
export LOG_DIR="${LOG_DIR:-/var/log/aitbc}"
export WALLET_NAME="${WALLET_NAME:-openclaw-trainee}"
export WALLET_PASSWORD="${WALLET_PASSWORD:-trainee123}"
export TRAINING_TIMEOUT="${TRAINING_TIMEOUT:-300}"
export GENESIS_NODE="http://localhost:8006"
export FOLLOWER_NODE="http://aitbc1:8006"

# Service endpoints
export SERVICES=(
    "8001:Exchange"
    "9001:Agent-Coordinator"
    "8006:Genesis-Node-RPC"
    "8006:Follower-Node-RPC"
    "11434:Ollama"
)

# ============================================================================
# COLOR OUTPUT
# ============================================================================

export RED='\033[0;31m'
export GREEN='\033[0;32m'
export YELLOW='\033[1;33m'
export BLUE='\033[0;34m'
export CYAN='\033[0;36m'
export BOLD='\033[1m'
export NC='\033[0m'

# ============================================================================
# LOGGING FUNCTIONS
# ============================================================================

# Initialize logging for a training stage
init_logging() {
    local stage_name=$1
    local log_file="$LOG_DIR/training_${stage_name}.log"
    
    mkdir -p "$LOG_DIR"
    export CURRENT_LOG="$log_file"
    
    {
        echo "========================================"
        echo "AITBC Training - $stage_name"
        echo "Started: $(date)"
        echo "Hostname: $(hostname)"
        echo "User: $(whoami)"
        echo "========================================"
        echo
    } >> "$log_file"
    
    echo "$log_file"
}

# Log message with timestamp
log() {
    local level=$1
    local message=$2
    local log_file="${CURRENT_LOG:-$LOG_DIR/training.log}"
    
    echo "$(date '+%Y-%m-%d %H:%M:%S') [$level] $message" | tee -a "$log_file"
}

# Convenience logging functions
log_info() { log "INFO" "$1"; }
log_success() { log "SUCCESS" "$1"; }
log_error() { log "ERROR" "$1"; }
log_warning() { log "WARNING" "$1"; }
log_debug() { 
    if [[ "${DEBUG:-false}" == "true" ]]; then
        log "DEBUG" "$1"
    fi
}

# ============================================================================
# PRINT FUNCTIONS
# ============================================================================

print_header() {
    echo -e "${BOLD}${BLUE}========================================${NC}"
    echo -e "${BOLD}${BLUE}$1${NC}"
    echo -e "${BOLD}${BLUE}========================================${NC}"
}

print_status() {
    echo -e "${BLUE}[TRAINING]${NC} $1"
    log_info "$1"
}

print_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
    log_success "$1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
    log_error "$1"
}

print_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
    log_warning "$1"
}

print_progress() {
    local current=$1
    local total=$2
    local percent=$((current * 100 / total))
    echo -e "${CYAN}[PROGRESS]${NC} $current/$total ($percent%) - $3"
    log_info "Progress: $current/$total ($percent%) - $3"
}

# ============================================================================
# SYSTEM CHECKS
# ============================================================================

# Check if CLI is available and executable
check_cli() {
    if [[ ! -f "$CLI_PATH" ]]; then
        print_error "AITBC CLI not found at $CLI_PATH"
        return 1
    fi
    
    if [[ ! -x "$CLI_PATH" ]]; then
        print_warning "CLI not executable, attempting to fix permissions"
        chmod +x "$CLI_PATH" 2>/dev/null || {
            print_error "Cannot make CLI executable"
            return 1
        }
    fi
    
    # Test CLI (using --help since --version not supported)
    if ! $CLI_PATH --help &>/dev/null; then
        print_error "CLI exists but --help command failed"
        return 1
    fi
    
    print_success "CLI check passed"
    return 0
}

# Check wallet existence
check_wallet() {
    local wallet_name=${1:-$WALLET_NAME}
    
    if $CLI_PATH wallet list 2>/dev/null | grep -q "$wallet_name"; then
        return 0
    else
        return 1
    fi
}

# Check service availability
check_service() {
    local port=$1
    local name=$2
    local timeout=${3:-5}
    
    if timeout "$timeout" bash -c "</dev/tcp/localhost/$port" 2>/dev/null; then
        print_success "$name (port $port) is accessible"
        return 0
    else
        print_warning "$name (port $port) is not accessible"
        return 1
    fi
}

# Check all required services
check_all_services() {
    local failed=0
    
    for service in "${SERVICES[@]}"; do
        local port=$(echo "$service" | cut -d: -f1)
        local name=$(echo "$service" | cut -d: -f2)
        
        if ! check_service "$port" "$name"; then
            (( failed += 1 )) || true
        fi
    done
    
    return $failed
}

# ============================================================================
# PERFORMANCE MEASUREMENT
# ============================================================================

# Measure command execution time
measure_time() {
    local cmd="$1"
    local description="${2:-Operation}"
    local start_time end_time duration
    
    start_time=$(date +%s.%N)
    
    if eval "$cmd" &>/dev/null; then
        end_time=$(date +%s.%N)
        duration=$(echo "$end_time - $start_time" | bc -l 2>/dev/null || echo "0.0")
        
        log_info "$description completed in ${duration}s"
        echo "$duration"
        return 0
    else
        end_time=$(date +%s.%N)
        duration=$(echo "$end_time - $start_time" | bc -l 2>/dev/null || echo "0.0")
        
        log_error "$description failed after ${duration}s"
        echo "$duration"
        return 1
    fi
}

# Benchmark operation with retries
benchmark_with_retry() {
    local cmd="$1"
    local max_retries="${2:-3}"
    local attempt=0
    local success=false
    
    while [[ $attempt -lt $max_retries ]] && [[ "$success" == "false" ]]; do
        (( attempt += 1 )) || true
        
        if eval "$cmd" &>/dev/null; then
            success=true
            log_success "Operation succeeded on attempt $attempt"
        else
            log_warning "Attempt $attempt failed, retrying..."
            sleep $((attempt * 2))  # Exponential backoff
        fi
    done
    
    if [[ "$success" == "true" ]]; then
        return 0
    else
        print_error "Operation failed after $max_retries attempts"
        return 1
    fi
}

# ============================================================================
# NODE OPERATIONS
# ============================================================================

# Execute command on specific node
run_on_node() {
    local node_url=$1
    local cmd="$2"
    
    NODE_URL="$node_url" eval "$cmd"
}

# Test node connectivity
test_node_connectivity() {
    local node_url=$1
    local node_name=$2
    local timeout=${3:-10}
    
    print_status "Testing connectivity to $node_name ($node_url)..."
    
    if timeout "$timeout" curl -s "$node_url/health" &>/dev/null; then
        print_success "$node_name is accessible"
        return 0
    else
        print_warning "$node_name is not accessible"
        return 1
    fi
}

# Compare operations between nodes
compare_nodes() {
    local cmd="$1"
    local description="$2"
    
    print_status "Comparing $description between nodes..."
    
    local genesis_result follower_result
    genesis_result=$(NODE_URL="$GENESIS_NODE" $CLI_PATH $cmd 2>/dev/null) || genesis_result="FAILED"
    follower_result=$(NODE_URL="$FOLLOWER_NODE" $CLI_PATH $cmd 2>/dev/null) || follower_result="FAILED"
    
    log_info "Genesis result: $genesis_result"
    log_info "Follower result: $follower_result"
    
    if [[ "$genesis_result" == "$follower_result" ]] && [[ "$genesis_result" != "FAILED" ]]; then
        print_success "Nodes are synchronized"
        return 0
    else
        print_warning "Node results differ"
        return 1
    fi
}

# ============================================================================
# VALIDATION
# ============================================================================

# Validate stage completion
validate_stage() {
    local stage_name=$1
    local log_file="${2:-$CURRENT_LOG}"
    local min_success_rate=${3:-90}
    
    print_status "Validating $stage_name completion..."
    
    # Count successes and failures
    local success_count fail_count total_count success_rate
    success_count=$(grep -c "SUCCESS" "$log_file" 2>/dev/null || echo "0")
    fail_count=$(grep -c "ERROR" "$log_file" 2>/dev/null || echo "0")
    total_count=$((success_count + fail_count))
    
    if [[ $total_count -gt 0 ]]; then
        success_rate=$((success_count * 100 / total_count))
    else
        success_rate=0
    fi
    
    log_info "Validation results: $success_count successes, $fail_count failures, $success_rate% success rate"
    
    if [[ $success_rate -ge $min_success_rate ]]; then
        print_success "Stage validation passed: $success_rate% success rate"
        return 0
    else
        print_error "Stage validation failed: $success_rate% success rate (minimum $min_success_rate%)"
        return 1
    fi
}

# ============================================================================
# UTILITY FUNCTIONS
# ============================================================================

# Generate unique identifier
generate_id() {
    echo "$(date +%s)_$RANDOM"
}

# Cleanup function (trap-friendly)
cleanup() {
    local exit_code=$?
    log_info "Training script cleanup (exit code: $exit_code)"
    
    # Kill any background processes
    jobs -p | xargs -r kill 2>/dev/null || true
    
    # Final log entry
    if [[ -n "${CURRENT_LOG:-}" ]]; then
        echo >> "$CURRENT_LOG"
        echo "========================================" >> "$CURRENT_LOG"
        echo "Training completed at $(date)" >> "$CURRENT_LOG"
        echo "Exit code: $exit_code" >> "$CURRENT_LOG"
        echo "========================================" >> "$CURRENT_LOG"
    fi
    
    return $exit_code
}

# Set up signal traps
setup_traps() {
    trap cleanup EXIT
    trap 'echo; print_error "Interrupted by user"; exit 130' INT TERM
}

# Check prerequisites with comprehensive validation
check_prerequisites_full() {
    local errors=0
    
    print_status "Running comprehensive prerequisites check..."
    
    # Check CLI
    if ! check_cli; then
        (( errors += 1 )) || true || true
    fi
    
    # Check services
    if ! check_all_services; then
        (( errors += 1 )) || true || true
    fi
    
    # Check log directory
    if [[ ! -d "$LOG_DIR" ]]; then
        print_status "Creating log directory..."
        mkdir -p "$LOG_DIR" || {
            print_error "Cannot create log directory"
            (( errors += 1 )) || true || true
        }
    fi
    
    # Check disk space
    local available_space
    available_space=$(df "$LOG_DIR" | awk 'NR==2 {print $4}')
    if [[ $available_space -lt 102400 ]]; then  # Less than 100MB
        print_warning "Low disk space: ${available_space}KB available"
    fi
    
    if [[ $errors -eq 0 ]]; then
        print_success "All prerequisites check passed"
        return 0
    else
        print_warning "Prerequisites check found $errors issues - continuing with training"
        log_warning "Continuing despite $errors prerequisite issues"
        return 0  # Continue training despite warnings
    fi
}

# ============================================================================
# PROGRESS TRACKING
# ============================================================================

# Initialize progress tracking
init_progress() {
    export TOTAL_STEPS=$1
    export CURRENT_STEP=0
    export STEP_START_TIME=$(date +%s)
}

# Update progress
update_progress() {
    local step_name="$1"
    (( CURRENT_STEP += 1 )) || true
    
    local elapsed=$(( $(date +%s) - STEP_START_TIME ))
    local percent=$((CURRENT_STEP * 100 / TOTAL_STEPS))
    
    print_progress "$CURRENT_STEP" "$TOTAL_STEPS" "$step_name"
    log_info "Step $CURRENT_STEP/$TOTAL_STEPS completed: $step_name (${elapsed}s elapsed)"
}

# ============================================================================
# COMMAND WRAPPERS
# ============================================================================

# Safe CLI command execution with error handling
cli_cmd() {
    local cmd="$*"
    local max_retries=3
    local attempt=0
    
    while [[ $attempt -lt $max_retries ]]; do
        (( attempt += 1 )) || true
        
        if $CLI_PATH $cmd 2>/dev/null; then
            return 0
        else
            if [[ $attempt -lt $max_retries ]]; then
                log_warning "CLI command failed (attempt $attempt/$max_retries): $cmd"
                sleep $((attempt * 2))
            fi
        fi
    done
    
    print_error "CLI command failed after $max_retries attempts: $cmd"
    return 1
}

# Execute CLI command and capture output
cli_cmd_output() {
    local cmd="$*"
    $CLI_PATH $cmd 2>/dev/null
}

# Execute CLI command with node specification
cli_cmd_node() {
    local node_url=$1
    shift
    # Use eval to properly parse command string with multiple arguments
    NODE_URL="$node_url" eval "$CLI_PATH $*" 2>/dev/null
}
