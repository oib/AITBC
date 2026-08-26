#!/bin/bash
# Shared helper for AITBC deployment scripts to record warnings/errors and print
# a machine-readable agent follow-up block at the end of a run.
#
# Usage in a script:
#   source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/agent_followup.sh"
#   agent_followup_init
#   # override warning/error/log if desired:
#   warning() { agent_record_warning "$*"; _your_warning "$@"; }
#   error()   { agent_record_error "$*"; _your_error "$@"; }
#   # at the end:
#   agent_print_followup

# Guard against being sourced more than once.
if [ -n "${AITBC_AGENT_FOLLOWUP_SOURCED:-}" ]; then
    return 0
fi
AITBC_AGENT_FOLLOWUP_SOURCED=1

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

agent_followup_init() {
    AITBC_AGENT_FOLLOWUP_WARNINGS=0
    AITBC_AGENT_FOLLOWUP_ERRORS=0
    AITBC_AGENT_FOLLOWUP_ISSUES=()
}

agent_record_warning() {
    AITBC_AGENT_FOLLOWUP_WARNINGS=$((AITBC_AGENT_FOLLOWUP_WARNINGS + 1))
    AITBC_AGENT_FOLLOWUP_ISSUES+=("warning: $*")
}

agent_record_error() {
    AITBC_AGENT_FOLLOWUP_ERRORS=$((AITBC_AGENT_FOLLOWUP_ERRORS + 1))
    AITBC_AGENT_FOLLOWUP_ISSUES+=("error: $*")
}

agent_followup_has_issues() {
    [ "${AITBC_AGENT_FOLLOWUP_WARNINGS:-0}" -gt 0 ] || [ "${AITBC_AGENT_FOLLOWUP_ERRORS:-0}" -gt 0 ]
}

agent_followup_get_node_role() {
    if [ -f /etc/aitbc/blockchain.env ]; then
        # shellcheck disable=SC1091
        source /etc/aitbc/blockchain.env 2>/dev/null || true
    fi
    if [ -f /etc/aitbc/node.env ]; then
        # shellcheck disable=SC1091
        source /etc/aitbc/node.env 2>/dev/null || true
    fi
    if [ "${BLOCKCHAIN_MODE:-}" = "hub" ]; then
        echo "hub"
    elif [ "${MARKET_ROLE:-}" = "shop" ] && [ "${HARDWARE_PROFILE:-}" = "gpu" ]; then
        echo "shop"
    elif [ "${MARKET_ROLE:-}" = "customer" ]; then
        echo "customer"
    else
        echo "follower"
    fi
}

agent_print_followup() {
    if [ "${AITBC_AGENT_FOLLOWUP_PRINTED:-0}" = "1" ]; then
        return 0
    fi
    if ! agent_followup_has_issues; then
        return 0
    fi
    AITBC_AGENT_FOLLOWUP_PRINTED=1

    local script_name="${0##*/}"
    local node_role="$(agent_followup_get_node_role)"
    local repo_commit="unknown"
    local repo_path="${AITBC_ROOT:-/opt/aitbc}"

    if [ -d "$repo_path/.git" ] && command -v git >/dev/null 2>&1; then
        repo_commit=$(git -C "$repo_path" rev-parse --short HEAD 2>/dev/null || echo unknown)
    fi

    local python_version="unknown"
    if command -v python3 >/dev/null 2>&1; then
        python_version=$(python3 --version 2>/dev/null | cut -d' ' -f2 || echo unknown)
    fi

    local poetry_version="unknown"
    if [ -x "$repo_path/venv-poetry/bin/poetry" ]; then
        poetry_version=$("$repo_path/venv-poetry/bin/poetry" --version 2>/dev/null | sed 's/^Poetry //; s/[()]//g; s/version //' || echo unknown)
    elif command -v poetry >/dev/null 2>&1; then
        poetry_version=$(poetry --version 2>/dev/null | sed 's/^Poetry //; s/[()]//g; s/version //' || echo unknown)
    fi

    echo ""
    echo "### AITBC AGENT FOLLOW-UP ###"
    echo "status: needs-investigation"
    echo "script: $script_name"
    echo "node_role: $node_role"
    echo "repo_path: $repo_path"
    echo "repo_commit: $repo_commit"
    echo "python_version: $python_version"
    echo "poetry_version: $poetry_version"
    echo "warnings: ${AITBC_AGENT_FOLLOWUP_WARNINGS:-0}"
    echo "errors: ${AITBC_AGENT_FOLLOWUP_ERRORS:-0}"
    echo "timestamp: $(date -Iseconds)"
    echo ""
    echo "issues:"
    for issue in "${AITBC_AGENT_FOLLOWUP_ISSUES[@]}"; do
        echo "  - $issue"
    done
    echo ""
    echo "diagnostics_to_collect:"
    echo "  - Full output of this script, e.g.: sudo $0 2>&1 | tee /tmp/aitbc-${script_name%.sh}.log"
    if command -v aitbc >/dev/null 2>&1; then
        echo "  - aitbc sync status"
    fi
    if [ -x "$repo_path/scripts/monitoring/health_check.sh" ]; then
        echo "  - $repo_path/scripts/monitoring/health_check.sh"
    fi
    echo "  - journalctl -u 'aitbc-*' -n 100 --no-pager --since '10 min ago'"
    echo "  - systemctl --failed --no-legend --no-pager"
    echo "  - git -C $repo_path status --short"
    echo "  - git -C $repo_path log --oneline -5"
    if [ -x "$repo_path/venv/bin/pip" ]; then
        echo "  - $repo_path/venv/bin/pip list 2>/dev/null | head -50"
    fi
    if [ -d "$repo_path/.requirements" ]; then
        echo "  - ls -la $repo_path/.requirements/"
    fi
    echo ""
    echo "agent_action: investigate the issues above and suggest fixes"
    echo "### END AITBC AGENT FOLLOW-UP ###"
    echo ""
}
