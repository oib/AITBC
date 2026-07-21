#!/bin/bash
# Post-deployment smoke tests for AITBC.
# Verifies migrations, service health, authentication, and deployed contract
# addresses before a release is considered live.
#
# Usage: run-production-smoke-tests.sh [mainnet|testnet]

set -euo pipefail

NETWORK="${1:-mainnet}"
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
VENV_DIR="${VENV_DIR:-/opt/aitbc/venv}"
PYTHON="${PYTHON:-$VENV_DIR/bin/python}"

# Service health endpoints (overridable via environment)
COORDINATOR_HEALTH_URL="${COORDINATOR_HEALTH_URL:-http://localhost:8203/v1/health}"
BLOCKCHAIN_RPC_URL="${BLOCKCHAIN_RPC_URL:-http://localhost:8202/rpc/head}"
WALLET_HEALTH_URL="${WALLET_HEALTH_URL:-http://localhost:8108/health}"
EXCHANGE_HEALTH_URL="${EXCHANGE_HEALTH_URL:-http://localhost:8106/health}"

# Auth check (overridable)
COORDINATOR_LOGIN_URL="${COORDINATOR_LOGIN_URL:-http://localhost:8203/v1/auth/login}"

FAILED=0

error() {
    echo "FAIL $1" >&2
    FAILED=$((FAILED + 1))
}

pass() {
    echo "PASS $1"
}

skip() {
    echo "SKIP $1"
}

fail_and_exit() {
    echo ""
    echo "Smoke tests failed: $FAILED check(s) failed" >&2
    exit 1
}

# -----------------------------------------------------------------------------
# 1. Alembic migration status for every service that ships migrations
# -----------------------------------------------------------------------------
check_migrations() {
    echo "=== Checking Alembic migration status ==="
    while IFS= read -r alembic_ini; do
        local svc_dir
        svc_dir="$(dirname "$alembic_ini")"
        local svc_name
        svc_name="$(basename "$svc_dir")"

        # Skip services that only have an alembic.ini stub with no env.py
        if [ ! -f "$svc_dir/alembic/env.py" ] && [ ! -f "$svc_dir/migrations/env.py" ]; then
            skip "$svc_name: no Alembic env.py, skipping migration check"
            continue
        fi

        local db_url
        db_url="${DATABASE_URL:-}"
        if [ -z "$db_url" ]; then
            # Try to source the service's environment file if present
            if [ -f "/etc/aitbc/aitbc-${svc_name}.env" ]; then
                # shellcheck source=/dev/null
                db_url="$(grep '^DATABASE_URL=' "/etc/aitbc/aitbc-${svc_name}.env" | cut -d= -f2- | sed 's/^[[:space:]]*//;s/[[:space:]]*$//')"
            fi
        fi

        local env=("PYTHONPATH=$svc_dir/src" "PATH=$VENV_DIR/bin:$PATH")
        [ -n "$db_url" ] && env+=("DATABASE_URL=$db_url")

        local head
        if head="$(cd "$svc_dir" && env "${env[@]}" "$PYTHON" -m alembic current 2>/dev/null)"; then
            if echo "$head" | grep -q 'head'; then
                pass "$svc_name migrations are at head"
            else
                error "$svc_name migrations are not at head: $head"
            fi
        else
            error "$svc_name: could not read Alembic current status"
        fi
    done < <(find "$REPO_ROOT/apps" -maxdepth 3 -name 'alembic.ini' 2>/dev/null | sort)
}

# -----------------------------------------------------------------------------
# 2. Service health endpoints
# -----------------------------------------------------------------------------
check_health() {
    echo "=== Checking service health endpoints ==="
    if ! command -v curl >/dev/null 2>&1; then
        skip "curl not installed, skipping health endpoint checks"
        return
    fi

    for pair in "coordinator-api:$COORDINATOR_HEALTH_URL" "blockchain-rpc:$BLOCKCHAIN_RPC_URL" "wallet:$WALLET_HEALTH_URL" "exchange:$EXCHANGE_HEALTH_URL"; do
        local name="${pair%%:*}"
        local url="${pair#*:}"
        if curl -sf "$url" >/dev/null 2>&1; then
            pass "$name health endpoint is reachable ($url)"
        else
            error "$name health endpoint is not reachable ($url)"
        fi
    done
}

# -----------------------------------------------------------------------------
# 3. Authentication sanity check
# -----------------------------------------------------------------------------
check_auth() {
    echo "=== Checking authentication endpoint ==="
    if ! command -v curl >/dev/null 2>&1; then
        skip "curl not installed, skipping auth check"
        return
    fi

    local http_status
    http_status="$(curl -s -o /dev/null -w '%{http_code}' "$COORDINATOR_LOGIN_URL" 2>/dev/null || echo '000')"

    if [ "$http_status" = "405" ] || [ "$http_status" = "401" ] || [ "$http_status" = "422" ]; then
        pass "auth endpoint is protected and returns expected status $http_status"
    elif [ "$http_status" = "200" ]; then
        error "auth endpoint returned 200 without credentials — authentication may be disabled"
    else
        error "auth endpoint returned unexpected status $http_status"
    fi
}

# -----------------------------------------------------------------------------
# 4. Contract address sanity check
# -----------------------------------------------------------------------------
check_contract_addresses() {
    echo "=== Checking deployed contract addresses ($NETWORK) ==="
    local deployment_file="$REPO_ROOT/deployment-info.json"

    if [ ! -f "$deployment_file" ]; then
        error "$deployment_file not found — contract addresses cannot be verified"
        return
    fi

    local contracts=("PaymentProcessor" "AgentMarketplace" "StakingContract" "TreasuryManager")
    for contract in "${contracts[@]}"; do
        local addr
        addr="$("$PYTHON" - <<PY
import json, sys
try:
    with open('$deployment_file') as f:
        data = json.load(f)
    print(data.get('contracts', {}).get('$contract', ''))
except Exception:
    print('')
PY
        )"

        if [ -z "$addr" ]; then
            error "$contract address is missing from $deployment_file"
        elif [[ ! "$addr" =~ ^0x[0-9a-fA-F]{40}$ ]]; then
            error "$contract address is not a valid 0x40 hex address: $addr"
        elif [ "${addr,,}" = "0x0000000000000000000000000000000000000000" ]; then
            error "$contract address is the zero address"
        else
            pass "$contract address is valid ($addr)"
        fi
    done
}

# -----------------------------------------------------------------------------
# Main
# -----------------------------------------------------------------------------
main() {
    echo "=== AITBC $NETWORK Post-Deployment Smoke Tests ==="
    echo "Started at: $(date -u +%Y-%m-%dT%H:%M:%SZ)"
    echo ""

    check_migrations
    check_health
    check_auth
    check_contract_addresses

    echo ""
    if [ "$FAILED" -gt 0 ]; then
        fail_and_exit
    fi

    echo "All $NETWORK smoke tests passed"
}

main "$@"
