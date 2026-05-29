#!/bin/bash

# AITBC Environment Validation Script
# Validates environment configuration before deployment

set -e

# Configuration
REPO_ROOT="${REPO_ROOT:-/opt/aitbc}"
NODE_ENV_FILE="/etc/aitbc/node.env"
BLOCKCHAIN_ENV_FILE="/etc/aitbc/blockchain.env"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Logging functions
log() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

# Validate port number
validate_port() {
    local port="$1"
    local name="$2"
    
    if [[ ! "$port" =~ ^[0-9]+$ ]]; then
        error "$name: '$port' is not a valid number"
        return 1
    fi
    
    if [[ "$port" -lt 1 ]] || [[ "$port" -gt 65535 ]]; then
        error "$name: '$port' is out of valid range (1-65535)"
        return 1
    fi
    
    # Check if port is already in use
    if command -v ss &> /dev/null; then
        if ss -tuln | grep -q ":$port "; then
            warning "$name: Port $port is already in use"
        fi
    fi
    
    return 0
}

# Validate URL format
validate_url() {
    local url="$1"
    local name="$2"
    
    if [[ ! "$url" =~ ^[a-zA-Z+]+:// ]]; then
        error "$name: '$url' is not a valid URL"
        return 1
    fi
    
    return 0
}

# Validate boolean
validate_boolean() {
    local value="$1"
    local name="$2"
    
    if [[ "$value" != "true" ]] && [[ "$value" != "false" ]]; then
        error "$name: '$value' must be 'true' or 'false'"
        return 1
    fi
    
    return 0
}

# Validate database connectivity
validate_database() {
    local db_url="$1"
    local name="$2"
    
    if [[ "$db_url" =~ postgresql:// ]] || [[ "$db_url" =~ postgresql\+asyncpg:// ]]; then
        log "$name: PostgreSQL URL detected"
        
        # Extract host and port
        local host=$(echo "$db_url" | sed -n 's/.*@\([^:]*\):.*/\1/p')
        local port=$(echo "$db_url" | sed -n 's/.*:\([0-9]*\)\/.*/\1/p')
        
        if [[ -n "$host" ]] && [[ -n "$port" ]]; then
            log "Testing PostgreSQL connectivity to $host:$port..."
            if command -v pg_isready &> /dev/null; then
                if pg_isready -h "$host" -p "$port" &> /dev/null; then
                    success "$name: PostgreSQL is reachable"
                else
                    warning "$name: PostgreSQL is not reachable at $host:$port"
                fi
            fi
        fi
    elif [[ "$db_url" =~ sqlite:// ]] || [[ "$db_url" =~ sqlite\+aiosqlite:// ]]; then
        log "$name: SQLite URL detected"
        
        # Extract database path
        local db_path=$(echo "$db_url" | sed -n 's/.*\/\/\([^?]*\).*/\1/p')
        
        if [[ -n "$db_path" ]]; then
            local db_dir=$(dirname "$db_path")
            if [[ ! -d "$db_dir" ]]; then
                warning "$name: Database directory $db_dir does not exist"
            else
                if [[ ! -w "$db_dir" ]]; then
                    error "$name: Database directory $db_dir is not writable"
                    return 1
                fi
            fi
        fi
    else
        error "$name: Unsupported database URL format"
        return 1
    fi
    
    return 0
}

# Validate Redis connectivity
validate_redis() {
    local redis_host="${1:-localhost}"
    local redis_port="${2:-6379}"
    
    log "Testing Redis connectivity to $redis_host:$redis_port..."
    
    if command -v redis-cli &> /dev/null; then
        if redis-cli -h "$redis_host" -p "$redis_port" ping &> /dev/null; then
            success "Redis is reachable"
        else
            warning "Redis is not reachable at $redis_host:$redis_port"
        fi
    else
        warning "redis-cli not found, skipping Redis connectivity check"
    fi
}

# Validate environment file
validate_env_file() {
    local env_file="$1"
    local file_name="$2"
    
    if [[ ! -f "$env_file" ]]; then
        error "$file_name: File not found at $env_file"
        return 1
    fi
    
    if [[ ! -r "$env_file" ]]; then
        error "$file_name: File is not readable"
        return 1
    fi
    
    log "Validating $file_name..."
    
    # Source the file to validate variables
    source "$env_file"
    
    return 0
}

# Validate blockchain.env file
validate_blockchain_env() {
    log "Validating blockchain.env file..."
    
    if [[ ! -f "$BLOCKCHAIN_ENV_FILE" ]]; then
        error "blockchain.env not found at $BLOCKCHAIN_ENV_FILE"
        error "Please create /etc/aitbc/blockchain.env with blockchain configuration"
        return 1
    fi
    
    # Load environment variables
    source "$BLOCKCHAIN_ENV_FILE"
    
    ERRORS=0
    
    # Validate blockchain configuration
    if [[ -z "$chain_id" ]] && [[ -z "$CHAIN_ID" ]]; then
        error "chain_id or CHAIN_ID is not set"
        ERRORS=$((ERRORS + 1))
    fi
    
    if [[ -n "$rpc_bind_port" ]]; then
        validate_port "$rpc_bind_port" "rpc_bind_port" || ERRORS=$((ERRORS + 1))
    fi
    
    if [[ -n "$p2p_bind_port" ]]; then
        validate_port "$p2p_bind_port" "p2p_bind_port" || ERRORS=$((ERRORS + 1))
    fi
    
    # Validate boolean settings
    if [[ -n "$enable_block_production" ]]; then
        validate_boolean "$enable_block_production" "enable_block_production" || ERRORS=$((ERRORS + 1))
    fi
    
    if [[ $ERRORS -gt 0 ]]; then
        error "Found $ERRORS error(s) in blockchain.env file"
        return 1
    fi
    
    success "blockchain.env file validation passed"
    return 0
}

# Validate node.env file
validate_node_env() {
    log "Validating node.env file..."
    
    if [[ ! -f "$NODE_ENV_FILE" ]]; then
        error "node.env not found at $NODE_ENV_FILE"
        error "Please copy examples/node.env.example to /etc/aitbc/node.env"
        return 1
    fi
    
    # Load environment variables
    source "$NODE_ENV_FILE"
    
    ERRORS=0
    
    # Check for placeholder UUIDs
    if grep -q "node-<unique-uuid-here>" "$NODE_ENV_FILE"; then
        error "NODE_ID contains placeholder UUID. Please set a unique value"
        ERRORS=$((ERRORS + 1))
    fi
    
    if grep -q "ait1<unique-uuid-here>" "$NODE_ENV_FILE"; then
        error "proposer_id contains placeholder UUID. Please set a unique value"
        ERRORS=$((ERRORS + 1))
    fi
    
    # Validate required fields
    if [[ -z "$NODE_ID" ]]; then
        error "NODE_ID is not set"
        ERRORS=$((ERRORS + 1))
    fi
    
    if [[ -z "$p2p_node_id" ]]; then
        error "p2p_node_id is not set"
        ERRORS=$((ERRORS + 1))
    fi
    
    if [[ -z "$proposer_id" ]]; then
        error "proposer_id is not set"
        ERRORS=$((ERRORS + 1))
    fi
    
    if [[ -z "$p2p_peers" ]]; then
        warning "p2p_peers is not set. This node may not connect to the network"
    fi
    
    if [[ $ERRORS -gt 0 ]]; then
        error "Found $ERRORS error(s) in node.env file"
        return 1
    fi
    
    success "node.env file validation passed"
    return 0
}

# Check system prerequisites
check_system_prerequisites() {
    log "Checking system prerequisites..."
    
    ERRORS=0
    
    # Check Python version
    if ! command -v python3 &> /dev/null; then
        error "Python 3 is not installed"
        ERRORS=$((ERRORS + 1))
    else
        PYTHON_VER=$(python3 --version | awk '{print $2}')
        log "Python version: $PYTHON_VER"
    fi
    
    # Check systemd
    if ! command -v systemctl &> /dev/null; then
        error "systemd is not available"
        ERRORS=$((ERRORS + 1))
    fi
    
    # Check PostgreSQL
    if ! command -v psql &> /dev/null; then
        warning "PostgreSQL client not found. Database validation may be limited"
    fi
    
    # Check Redis
    if ! command -v redis-cli &> /dev/null; then
        warning "Redis client not found. Redis validation may be limited"
    fi
    
    if [[ $ERRORS -gt 0 ]]; then
        error "System prerequisites check failed"
        return 1
    fi
    
    success "System prerequisites check passed"
    return 0
}

# Main validation function
main() {
    log "Starting AITBC environment validation..."
    echo ""
    
    TOTAL_ERRORS=0
    
    # Check system prerequisites
    check_system_prerequisites || TOTAL_ERRORS=$((TOTAL_ERRORS + 1))
    echo ""
    
    # Validate environment files (only /etc/aitbc/blockchain.env and /etc/aitbc/node.env are allowed)
    validate_blockchain_env || TOTAL_ERRORS=$((TOTAL_ERRORS + 1))
    echo ""
    
    validate_node_env || TOTAL_ERRORS=$((TOTAL_ERRORS + 1))
    echo ""
    
    # Summary
    if [[ $TOTAL_ERRORS -eq 0 ]]; then
        success "All environment validation checks passed!"
        echo ""
        log "You can proceed with deployment using: scripts/deployment/deploy.sh"
        return 0
    else
        error "Environment validation failed with $TOTAL_ERRORS error(s)"
        echo ""
        log "Please fix the errors above before proceeding with deployment"
        return 1
    fi
}

# Handle script interruption
trap 'error "Script interrupted"' INT TERM

# Run main function
main "$@"
