#!/bin/bash
# ============================================================================
# Environment Configuration Utility for AITBC Scripts
# ============================================================================
# Provides environment-based configuration management
# Source this file: source /opt/aitbc/scripts/utils/env_config.sh
# ============================================================================

# Set default values if not already set
AITBC_ROOT="${AITBC_ROOT:-/opt/aitbc}"
AITBC_ENV="${AITBC_ENV:-development}"
DEBUG_MODE="${DEBUG_MODE:-false}"
DRY_RUN="${DRY_RUN:-false}"

# Directory paths
CONFIG_DIR="${AITBC_ROOT}/config"
LOG_DIR="${AITBC_ROOT}/logs"
BACKUP_DIR="${AITBC_ROOT}/backups"
SCRIPTS_DIR="${AITBC_ROOT}/scripts"
APPS_DIR="${AITBC_ROOT}/apps"
TESTS_DIR="${AITBC_ROOT}/tests"

# Phase-specific directories
CONSENSUS_DIR="${APPS_DIR}/blockchain-node/src/aitbc_chain/consensus"
NETWORK_DIR="${APPS_DIR}/blockchain-node/src/aitbc_chain/network"
ECONOMICS_DIR="${APPS_DIR}/blockchain-node/src/aitbc_chain/economics"
CONTRACTS_DIR="${APPS_DIR}/blockchain-node/src/aitbc_chain/contracts"
AGENT_SERVICES_DIR="${APPS_DIR}/agent-services"

# Default configuration values
DEFAULT_VALIDATOR_COUNT="${DEFAULT_VALIDATOR_COUNT:-5}"
DEFAULT_BLOCK_TIME="${DEFAULT_BLOCK_TIME:-30}"
DEFAULT_MIN_STAKE="${DEFAULT_MIN_STAKE:-1000}"
DEFAULT_GAS_PRICE="${DEFAULT_GAS_PRICE:-0.001}"
DEFAULT_NETWORK_SIZE="${DEFAULT_NETWORK_SIZE:-50}"
DEFAULT_MAX_PEERS="${DEFAULT_MAX_PEERS:-50}"

# Network configuration
BOOTSTRAP_NODES="${BOOTSTRAP_NODES:-10.1.223.93:8000,10.1.223.40:8000}"
DISCOVERY_INTERVAL="${DISCOVERY_INTERVAL:-30}"
HEARTBEAT_INTERVAL="${HEARTBEAT_INTERVAL:-60}"

# Color codes
if [[ -t 1 ]]; then
    RED='\033[0;31m'
    GREEN='\033[0;32m'
    YELLOW='\033[1;33m'
    BLUE='\033[0;34m'
    NC='\033[0m'
else
    RED=''
    GREEN=''
    YELLOW=''
    BLUE=''
    NC=''
fi

# ============================================================================
# Configuration Functions
# ============================================================================

load_env_file() {
    """
    Load environment variables from .env file
    Usage: load_env_file [env_file_path]
    """
    local env_file="${1:-${AITBC_ROOT}/.env}"
    
    if [[ -f "$env_file" ]]; then
        log_info "Loading environment from ${env_file}"
        set -a
        source "$env_file"
        set +a
    else
        log_warn "Environment file not found: ${env_file}"
    fi
}

save_env_file() {
    """
    Save current environment configuration to .env file
    Usage: save_env_file [env_file_path]
    """
    local env_file="${1:-${AITBC_ROOT}/.env}"
    
    log_info "Saving environment configuration to ${env_file}"
    
    cat > "$env_file" << EOF
# AITBC Environment Configuration
# Generated: $(date)
# Environment: ${AITBC_ENV}

AITBC_ROOT=${AITBC_ROOT}
AITBC_ENV=${AITBC_ENV}
DEBUG_MODE=${DEBUG_MODE}
DRY_RUN=${DRY_RUN}

# Default Configuration
DEFAULT_VALIDATOR_COUNT=${DEFAULT_VALIDATOR_COUNT}
DEFAULT_BLOCK_TIME=${DEFAULT_BLOCK_TIME}
DEFAULT_MIN_STAKE=${DEFAULT_MIN_STAKE}
DEFAULT_GAS_PRICE=${DEFAULT_GAS_PRICE}
DEFAULT_NETWORK_SIZE=${DEFAULT_NETWORK_SIZE}
DEFAULT_MAX_PEERS=${DEFAULT_MAX_PEERS}

# Network Configuration
BOOTSTRAP_NODES=${BOOTSTRAP_NODES}
DISCOVERY_INTERVAL=${DISCOVERY_INTERVAL}
HEARTBEAT_INTERVAL=${HEARTBEAT_INTERVAL}
EOF
    
    log_info "Environment configuration saved"
}

get_config_value() {
    """
    Get configuration value with fallback to default
    Usage: get_config_value key [default_value]
    """
    local key="$1"
    local default_value="${2:-}"
    local value
    
    # Try environment variable first
    value="${!key}"
    
    # If not set, try config file
    if [[ -z "$value" && -f "${CONFIG_DIR}/env_config.json" ]]; then
        value=$(jq -r ".${key} // empty" "${CONFIG_DIR}/env_config.json" 2>/dev/null)
    fi
    
    # Fallback to default
    if [[ -z "$value" ]]; then
        value="$default_value"
    fi
    
    echo "$value"
}

set_config_value() {
    """
    Set configuration value in environment and config file
    Usage: set_config_value key value
    """
    local key="$1"
    local value="$2"
    
    # Export to environment
    export "${key}=${value}"
    
    # Update config file if it exists
    if [[ -f "${CONFIG_DIR}/env_config.json" ]]; then
        local temp_file=$(mktemp)
        jq --arg key "$key" --arg value "$value" '. + {($key): $value}' \
           "${CONFIG_DIR}/env_config.json" > "$temp_file"
        mv "$temp_file" "${CONFIG_DIR}/env_config.json"
    else
        # Create new config file
        mkdir -p "$CONFIG_DIR"
        echo "{\"${key}\": \"${value}\"}" > "${CONFIG_DIR}/env_config.json"
    fi
    
    log_info "Configuration set: ${key}=${value}"
}

# ============================================================================
# Environment Detection
# ============================================================================

detect_environment() {
    """
    Detect current environment based on hostname, user, or other factors
    Usage: detect_environment
    Returns: environment_name
    """
    local hostname=$(hostname)
    local user=$(whoami)
    
    # Check for production indicators
    if [[ "$hostname" =~ prod|production ]] || [[ "$AITBC_ENV" == "production" ]]; then
        echo "production"
    # Check for staging indicators
    elif [[ "$hostname" =~ staging|stage|test ]] || [[ "$AITBC_ENV" == "staging" ]]; then
        echo "staging"
    # Default to development
    else
        echo "development"
    fi
}

validate_environment() {
    """
    Validate that current environment is supported
    Usage: validate_environment
    Returns: 0 if valid, 1 if invalid
    """
    local valid_envs=("development" "staging" "production" "testing")
    local current_env=$(detect_environment)
    
    for env in "${valid_envs[@]}"; do
        if [[ "$current_env" == "$env" ]]; then
            return 0
        fi
    done
    
    log_error "Invalid environment: ${current_env}"
    log_error "Valid environments: ${valid_envs[*]}"
    return 1
}

# ============================================================================
# Environment-Specific Configuration
# ============================================================================

load_environment_config() {
    """
    Load environment-specific configuration
    Usage: load_environment_config [environment]
    """
    local env="${1:-$(detect_environment)}"
    local config_file="${CONFIG_DIR}/env.${env}.json"
    
    log_info "Loading configuration for environment: ${env}"
    
    if [[ -f "$config_file" ]]; then
        # Load JSON configuration
        while IFS='=' read -r key value; do
            key=$(echo "$key" | tr -d '"')
            value=$(echo "$value" | tr -d '"')
            export "${key}=${value}"
        done < <(jq -r 'to_entries | .[] | "\(.key)=\(.value)"' "$config_file")
        
        log_info "Loaded environment configuration from ${config_file}"
    else
        log_warn "Environment config not found: ${config_file}"
        log_info "Using default configuration"
    fi
}

create_environment_config() {
    """
    Create environment-specific configuration file
    Usage: create_environment_config environment
    """
    local env="$1"
    local config_file="${CONFIG_DIR}/env.${env}.json"
    
    mkdir -p "$CONFIG_DIR"
    
    case "$env" in
        "development")
            cat > "$config_file" << EOF
{
    "AITBC_ENV": "development",
    "DEBUG_MODE": "true",
    "DEFAULT_VALIDATOR_COUNT": "3",
    "DEFAULT_BLOCK_TIME": "10",
    "DEFAULT_NETWORK_SIZE": "10",
    "LOG_LEVEL": "DEBUG"
}
EOF
            ;;
        "staging")
            cat > "$config_file" << EOF
{
    "AITBC_ENV": "staging",
    "DEBUG_MODE": "false",
    "DEFAULT_VALIDATOR_COUNT": "5",
    "DEFAULT_BLOCK_TIME": "30",
    "DEFAULT_NETWORK_SIZE": "20",
    "LOG_LEVEL": "INFO"
}
EOF
            ;;
        "production")
            cat > "$config_file" << EOF
{
    "AITBC_ENV": "production",
    "DEBUG_MODE": "false",
    "DEFAULT_VALIDATOR_COUNT": "10",
    "DEFAULT_BLOCK_TIME": "30",
    "DEFAULT_NETWORK_SIZE": "50",
    "LOG_LEVEL": "WARN"
}
EOF
            ;;
        *)
            log_error "Unknown environment: ${env}"
            return 1
            ;;
    esac
    
    log_info "Created environment configuration: ${config_file}"
}

# ============================================================================
# Validation Functions
# ============================================================================

validate_required_vars() {
    """
    Validate that required environment variables are set
    Usage: validate_required_vars var1 var2 var3 ...
    """
    local missing_vars=()
    
    for var in "$@"; do
        if [[ -z "${!var}" ]]; then
            missing_vars+=("$var")
        fi
    done
    
    if [[ ${#missing_vars[@]} -gt 0 ]]; then
        log_error "Missing required environment variables:"
        for var in "${missing_vars[@]}"; do
            log_error "  - ${var}"
        done
        return 1
    fi
    
    return 0
}

validate_paths() {
    """
    Validate that required paths exist
    Usage: validate_paths
    """
    local required_paths=(
        "$AITBC_ROOT"
        "$CONFIG_DIR"
        "$APPS_DIR"
        "$SCRIPTS_DIR"
    )
    
    local missing_paths=()
    
    for path in "${required_paths[@]}"; do
        if [[ ! -d "$path" ]]; then
            missing_paths+=("$path")
        fi
    done
    
    if [[ ${#missing_paths[@]} -gt 0 ]]; then
        log_error "Missing required directories:"
        for path in "${missing_paths[@]}"; do
            log_error "  - ${path}"
        done
        return 1
    fi
    
    return 0
}

# ============================================================================
# Logging Functions
# ============================================================================

log_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

log_debug() {
    if [[ "${DEBUG_MODE}" == "true" ]]; then
        echo -e "${BLUE}[DEBUG]${NC} $1"
    fi
}

# ============================================================================
# Utility Functions
# ============================================================================

print_environment() {
    """
    Print current environment configuration
    Usage: print_environment
    """
    echo ""
    echo "============================================"
    echo "AITBC Environment Configuration"
    echo "============================================"
    echo "AITBC_ROOT:        ${AITBC_ROOT}"
    echo "AITBC_ENV:         ${AITBC_ENV}"
    echo "DEBUG_MODE:        ${DEBUG_MODE}"
    echo "DRY_RUN:           ${DRY_RUN}"
    echo ""
    echo "Default Configuration:"
    echo "  Validator Count: ${DEFAULT_VALIDATOR_COUNT}"
    echo "  Block Time:      ${DEFAULT_BLOCK_TIME}"
    echo "  Min Stake:       ${DEFAULT_MIN_STAKE}"
    echo "  Gas Price:       ${DEFAULT_GAS_PRICE}"
    echo "  Network Size:    ${DEFAULT_NETWORK_SIZE}"
    echo ""
    echo "Network Configuration:"
    echo "  Bootstrap Nodes: ${BOOTSTRAP_NODES}"
    echo "  Discovery Interval: ${DISCOVERY_INTERVAL}"
    echo "  Heartbeat Interval: ${HEARTBEAT_INTERVAL}"
    echo "============================================"
    echo ""
}

is_dry_run() {
    """
    Check if running in dry-run mode
    Usage: is_dry_run
    Returns: 0 if dry-run, 1 otherwise
    """
    [[ "${DRY_RUN}" == "true" ]]
}

is_debug() {
    """
    Check if running in debug mode
    Usage: is_debug
    Returns: 0 if debug, 1 otherwise
    """
    [[ "${DEBUG_MODE}" == "true" ]]
}

# ============================================================================
# Initialization
# ============================================================================

init_env_config() {
    """
    Initialize environment configuration
    Usage: init_env_config
    """
    # Load .env file if it exists
    load_env_file
    
    # Detect and set environment
    AITBC_ENV=$(detect_environment)
    export AITBC_ENV
    
    # Load environment-specific configuration
    load_environment_config "$AITBC_ENV"
    
    # Validate environment
    validate_environment || exit 1
    
    # Validate paths
    validate_paths || exit 1
    
    log_info "Environment configuration initialized"
    log_info "Environment: ${AITBC_ENV}"
    
    # Print configuration if debug mode
    is_debug && print_environment
}

# Initialize if this script is sourced
if [[ "${BASH_SOURCE[0]}" != "${0}" ]]; then
    init_env_config
fi
