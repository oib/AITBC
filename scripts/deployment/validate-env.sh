#!/bin/bash

# AITBC Environment Validation Script
# Validates environment configuration before deployment
#
# Env files are parsed with systemd EnvironmentFile semantics via
# scripts/utils/systemd-env.sh — never `source`d (a sourced file executes
# as shell; a malformed or hostile line ran in the validator). Keys are
# read case-insensitively: systemd units consume the UPPERCASE spellings
# while some legacy files carry lower_case ones, so both are checked.
#
# File locations can be overridden for testing — never validate against
# scratch paths on a live host without meaning to:
#   BLOCKCHAIN_ENV_FILE, NODE_ENV_FILE

set -euo pipefail

# Configuration
REPO_ROOT="${REPO_ROOT:-/opt/aitbc}"
SYSTEMD_ENV_SCRIPT="${SYSTEMD_ENV_SCRIPT:-${REPO_ROOT}/scripts/utils/systemd-env.sh}"
NODE_ENV_FILE="${NODE_ENV_FILE:-/etc/aitbc/node.env}"
BLOCKCHAIN_ENV_FILE="${BLOCKCHAIN_ENV_FILE:-/etc/aitbc/blockchain.env}"

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

# ----------------------------------------------------------------------------
# Read one key from a single env file with systemd EnvironmentFile semantics.
# Accepts the exact spelling first, then the optional alias (lower_case
# legacy). Prints the value; rc 1 = absent.
# Usage: _env_val <file> KEY [lowercase_alias]
# ----------------------------------------------------------------------------
_env_val() {
    local file="$1" key="$2" alias="${3:-}" v
    if v=$("$SYSTEMD_ENV_SCRIPT" get "$file" "$key" 2>/dev/null); then
        printf '%s' "$v"
        return 0
    fi
    if [ -n "$alias" ] && v=$("$SYSTEMD_ENV_SCRIPT" get "$file" "$alias" 2>/dev/null); then
        printf '%s' "$v"
        return 0
    fi
    return 1
}

# Read a key across both env files (blockchain.env first, then node.env —
# the same precedence update.sh uses), then the ambient environment.
_env_val_any() {
    local key="$1" alias="${2:-}" v
    if v=$(_env_val "$BLOCKCHAIN_ENV_FILE" "$key" "$alias"); then
        printf '%s' "$v"
        return 0
    fi
    if v=$(_env_val "$NODE_ENV_FILE" "$key" "$alias"); then
        printf '%s' "$v"
        return 0
    fi
    printf '%s' "${!key:-}"
}

# Check an env file parses cleanly as a systemd EnvironmentFile.
_check_env_file() {
    local env_file="$1" file_name="$2"

    if [[ ! -f "$env_file" ]]; then
        error "$file_name: File not found at $env_file"
        return 1
    fi

    if [[ ! -r "$env_file" ]]; then
        error "$file_name: File is not readable"
        return 1
    fi

    local rc=0
    "$SYSTEMD_ENV_SCRIPT" parse "$env_file" > /dev/null || rc=$?
    if [[ $rc -eq 2 ]]; then
        error "$file_name: contains a malformed KEY=VALUE line"
        return 1
    fi

    return 0
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
        local host
        host=$(echo "$db_url" | sed -n 's/.*@\([^:]*\):.*/\1/p')
        local port
        port=$(echo "$db_url" | sed -n 's/.*:\([0-9]*\)\/.*/\1/p')

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
        local db_path
        db_path=$(echo "$db_url" | sed -n 's/.*\/\/\([^?]*\).*/\1/p')

        if [[ -n "$db_path" ]]; then
            local db_dir
            db_dir=$(dirname "$db_path")
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

# Validate blockchain.env file
validate_blockchain_env() {
    log "Validating blockchain.env file..."

    _check_env_file "$BLOCKCHAIN_ENV_FILE" "blockchain.env" || {
        error "Please create /etc/aitbc/blockchain.env with blockchain configuration"
        return 1
    }

    ERRORS=0

    # chain id — both spellings
    local chain_id
    chain_id=$(_env_val "$BLOCKCHAIN_ENV_FILE" CHAIN_ID chain_id)
    if [[ -z "$chain_id" ]]; then
        error "CHAIN_ID (or chain_id) is not set in blockchain.env"
        ERRORS=$((ERRORS + 1))
    fi

    # bind ports — both spellings
    local rpc_bind_port p2p_bind_port enable_block_production proposer_id
    rpc_bind_port=$(_env_val "$BLOCKCHAIN_ENV_FILE" RPC_BIND_PORT rpc_bind_port)
    if [[ -n "$rpc_bind_port" ]]; then
        validate_port "$rpc_bind_port" "RPC_BIND_PORT" || ERRORS=$((ERRORS + 1))
    fi

    p2p_bind_port=$(_env_val "$BLOCKCHAIN_ENV_FILE" P2P_BIND_PORT p2p_bind_port)
    if [[ -n "$p2p_bind_port" ]]; then
        validate_port "$p2p_bind_port" "P2P_BIND_PORT" || ERRORS=$((ERRORS + 1))
    fi

    enable_block_production=$(_env_val "$BLOCKCHAIN_ENV_FILE" ENABLE_BLOCK_PRODUCTION enable_block_production)
    if [[ -n "$enable_block_production" ]]; then
        validate_boolean "$enable_block_production" "ENABLE_BLOCK_PRODUCTION" || ERRORS=$((ERRORS + 1))
    fi

    # aitbc-blockchain-node reads PROPOSER_ID from blockchain.env — that is
    # the file this check must hit, not node.env.
    proposer_id=$(_env_val "$BLOCKCHAIN_ENV_FILE" PROPOSER_ID proposer_id)
    if [[ -z "$proposer_id" ]]; then
        error "PROPOSER_ID is not set in blockchain.env (the file aitbc-blockchain-node reads)"
        ERRORS=$((ERRORS + 1))
    elif [[ "$proposer_id" == *"<unique"* ]]; then
        error "PROPOSER_ID in blockchain.env still holds the placeholder value"
        ERRORS=$((ERRORS + 1))
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

    _check_env_file "$NODE_ENV_FILE" "node.env" || {
        error "Please copy examples/node.env.open-island to /etc/aitbc/node.env"
        return 1
    }

    ERRORS=0

    # Check for placeholder UUIDs in either file
    for f in "$NODE_ENV_FILE" "$BLOCKCHAIN_ENV_FILE"; do
        if grep -q "node-<unique-uuid-here>" "$f" 2>/dev/null; then
            error "NODE_ID in $f contains a placeholder UUID. Please set a unique value"
            ERRORS=$((ERRORS + 1))
        fi
        if grep -q "0x<unique-uuid-here>\|ait1<unique-proposer-id>" "$f" 2>/dev/null; then
            error "PROPOSER_ID in $f contains a placeholder value. Please set a unique value"
            ERRORS=$((ERRORS + 1))
        fi
    done

    # Required fields — read across both env files (either spelling); setup
    # writes NODE_ID to node.env and P2P_NODE_ID may live in blockchain.env.
    local node_id p2p_node_id p2p_peers
    node_id=$(_env_val_any NODE_ID node_id)
    if [[ -z "$node_id" ]]; then
        error "NODE_ID is not set (checked node.env and blockchain.env)"
        ERRORS=$((ERRORS + 1))
    fi

    p2p_node_id=$(_env_val_any P2P_NODE_ID p2p_node_id)
    if [[ -z "$p2p_node_id" ]]; then
        error "P2P_NODE_ID is not set (checked node.env and blockchain.env)"
        ERRORS=$((ERRORS + 1))
    fi

    p2p_peers=$(_env_val_any P2P_PEERS p2p_peers)
    if [[ -z "$p2p_peers" ]]; then
        warning "P2P_PEERS is not set. This node may not connect to the network"
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

    if [[ ! -x "$SYSTEMD_ENV_SCRIPT" && ! -f "$SYSTEMD_ENV_SCRIPT" ]]; then
        error "EnvironmentFile parser not found at $SYSTEMD_ENV_SCRIPT (set REPO_ROOT or SYSTEMD_ENV_SCRIPT)"
        return 1
    fi

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
        log "You can proceed with deployment using: scripts/deployment/setup.sh"
        return 0
    else
        error "Environment validation failed with $TOTAL_ERRORS error(s)"
        echo ""
        log "Please fix the errors above before proceeding with deployment"
        return 1
    fi
}

# Handle script interruption
trap 'error "Script interrupted"; exit 130' INT TERM

# Run main function (skipped when sourced by tests)
if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
    main "$@"
fi
