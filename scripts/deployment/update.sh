#!/bin/bash

# ============================================================================
# AITBC Update Script
# ----------------------------------------------------------------------------
# Safely updates an already-installed AITBC node after `git pull`.
#
# This is the update counterpart to setup.sh. It is idempotent and safe to
# run after every pull. It performs:
#   1. Trigger pre-update backup (aitbc-backup.service)
#   2. git pull (with stash safety for local changes)
#   3. Sync Python venv (reinstall requirements + CLI)
#   4. Relink systemd unit files (role-aware, via link-systemd.sh)
#   5. daemon-reload + enable services for this role
#   6. Run Alembic DB migrations for all services with alembic.ini, each with its own
#      /etc/aitbc/aitbc-<svc>.env and with the service stopped for the duration.
#      blockchain-node is skipped unless DATABASE_URL is given: it has one database per
#      island and its Alembic default points at a file no node uses.
#   7. Restart all aitbc services
#   8. Run health check
#   9. Print summary + manual follow-up reminders
#
# Usage:
#   sudo /opt/aitbc/scripts/deployment/update.sh
#   sudo /opt/aitbc/scripts/deployment/update.sh --no-pull     # skip git pull
#   sudo /opt/aitbc/scripts/deployment/update.sh --no-restart  # skip service restart
#   sudo /opt/aitbc/scripts/deployment/update.sh --no-migrate  # skip DB migrations
#   sudo /opt/aitbc/scripts/deployment/update.sh --skip-backup # skip pre-update backup
#   sudo /opt/aitbc/scripts/deployment/update.sh --gitea       # pull from the canonical Gitea repo
#   sudo /opt/aitbc/scripts/deployment/update.sh --remote URL  # override git remote
#
# Prerequisites:
#   - Node already set up via setup.sh
#   - /etc/aitbc/node.env and/or /etc/aitbc/blockchain.env present
#
# Git remote:
#   Defaults to `origin` (which setup.sh sets to the public GitHub mirror by default,
#   or to the canonical Gitea URL when --gitea is used).
#   GitHub is `github`; the canonical Gitea source is `gitea` (or `origin` when --gitea
#   was used for the initial clone).
#   Override with --gitea, --remote <name|url>, or AITBC_GIT_REMOTE env var.
# ============================================================================

set -u  # error on unset vars; do NOT use -e (we want to continue past soft failures)
set -o pipefail
# pipefail is new here and is not a behaviour change. Without `set -e` a pipeline's status
# only matters where it is tested, and this script tests four: two are `systemctl ... |
# grep -q`, where a failing systemctl produces no output and the grep fails anyway, and the
# other two are `||` between commands rather than pipelines. Until V23-79 the only
# `set -o pipefail` in this file sat inside the migration subshell, which has moved to
# run-migrations.sh; this replaces it at the top rather than losing it.

AITBC_ROOT="${AITBC_ROOT:-/opt/aitbc}"
VENV_DIR="$AITBC_ROOT/venv"
NODE_ENV_FILE="/etc/aitbc/node.env"
BLOCKCHAIN_ENV_FILE="/etc/aitbc/blockchain.env"
HEALTH_CHECK_SCRIPT="$AITBC_ROOT/scripts/monitoring/health_check.sh"
LINK_SYSTEMD_SCRIPT="$AITBC_ROOT/scripts/utils/link-systemd.sh"
INSTALL_PROFILES_SCRIPT="$AITBC_ROOT/scripts/deployment/install-profiles.sh"
RUN_MIGRATIONS_SCRIPT="$AITBC_ROOT/scripts/deployment/run-migrations.sh"

# Public mirror and canonical Gitea source.
GITHUB_REMOTE="https://github.com/oib/AITBC.git"
GITEA_REMOTE="https://gitea.bubuit.net/oib/AITBC.git"

# Git remote to pull from. setup.sh sets `origin` to whichever source was used
# (GitHub by default, or Gitea with --gitea). Override with --gitea, --remote
# <name|url>, or AITBC_GIT_REMOTE.
GIT_REMOTE="${AITBC_GIT_REMOTE:-origin}"
GITEA_REMOTE_ARG=""

# Flags
DO_PULL=true
DO_RESTART=true
DO_BACKUP=true
DO_MIGRATE=true

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

log()     { echo -e "${BLUE}[$(date +'%H:%M:%S')]${NC} $*"; }
success() { echo -e "${GREEN}[$(date +'%H:%M:%S')] ✓${NC} $*"; }
warning() { echo -e "${YELLOW}[$(date +'%H:%M:%S')] ⚠${NC} $*" >&2; }
error()   { echo -e "${RED}[$(date +'%H:%M:%S')] ✗${NC} $*" >&2; }

# Record warnings/errors for an end-of-run agent follow-up block.
__update_agent_followup_path="$AITBC_ROOT/scripts/utils/agent_followup.sh"
if [ -f "$__update_agent_followup_path" ]; then
    # shellcheck disable=SC1090
    source "$__update_agent_followup_path"
    agent_followup_init

    __update_warning() {
        agent_record_warning "$*"
        echo -e "${YELLOW}[$(date +'%H:%M:%S')] ⚠${NC} $*" >&2
    }
    __update_error() {
        agent_record_error "$*"
        echo -e "${RED}[$(date +'%H:%M:%S')] ✗${NC} $*" >&2
    }
    warning() { __update_warning "$@"; }
    error()   { __update_error "$@"; }

    # update.sh intentionally does not use set -e, so catch explicit exit(1) paths.
    __update_exit_trap() {
        local exit_code=$?
        if [ "$exit_code" -ne 0 ]; then
            agent_record_error "update.sh exited with code $exit_code"
            agent_print_followup
        fi
    }
    trap '__update_exit_trap' EXIT
fi

# Detect if an NVIDIA GPU is present and accessible via nvidia-smi.
# Sets DETECTED_HARDWARE to "gpu" or "nogpu".
# Sets GPU_NAME and GPU_COUNT if a GPU is detected.
# Usage: detect_gpu; echo "$DETECTED_HARDWARE $GPU_NAME"
detect_gpu() {
    GPU_NAME=""
    GPU_COUNT=0
    DETECTED_HARDWARE="nogpu"
    if command -v nvidia-smi >/dev/null 2>&1 && nvidia-smi --query-gpu=name --format=csv,noheader >/dev/null 2>&1; then
        GPU_NAME=$(nvidia-smi --query-gpu=name --format=csv,noheader 2>/dev/null | head -1)
        GPU_COUNT=$(nvidia-smi --query-gpu=count --format=csv,noheader,nounits 2>/dev/null | head -1)
        GPU_COUNT="${GPU_COUNT:-1}"
        DETECTED_HARDWARE="gpu"
    fi
}

# ----------------------------------------------------------------------------
# Parse arguments
# ----------------------------------------------------------------------------
parse_args() {
    local use_gitea=false

    while [ $# -gt 0 ]; do
        case "$1" in
            --no-pull)    DO_PULL=false; shift ;;
            --no-restart) DO_RESTART=false; shift ;;
            --no-migrate) DO_MIGRATE=false; shift ;;
            --skip-backup) DO_BACKUP=false; shift ;;
            --remote)     GIT_REMOTE="$2"; shift 2 ;;
            --gitea)
                use_gitea=true
                if [ $# -gt 1 ] && [[ "$2" != --* ]]; then
                    GITEA_REMOTE_ARG="$2"
                    shift 2
                else
                    GITEA_REMOTE_ARG=""
                    shift
                fi
                ;;
            -h|--help)
                sed -n '3,25p' "$0"
                exit 0
                ;;
            *)
                error "Unknown argument: $1"
                exit 2
                ;;
        esac
    done

    # If --gitea was given and no --remote override was provided, use the Gitea source.
    # --remote is detected by the fact that GIT_REMOTE would no longer equal the default.
    if [ "$use_gitea" = true ] && [ "$GIT_REMOTE" = "${AITBC_GIT_REMOTE:-origin}" ]; then
        GIT_REMOTE="${GITEA_REMOTE_ARG:-$GITEA_REMOTE}"
    fi
}

# ----------------------------------------------------------------------------
# Pre-flight checks
# ----------------------------------------------------------------------------
check_root() {
    if [ "$(id -u)" -ne 0 ]; then
        error "This script must be run as root (use sudo)"
        exit 1
    fi
}

check_repo() {
    if [ ! -d "$AITBC_ROOT/.git" ]; then
        error "AITBC repository not found at $AITBC_ROOT"
        error "Run setup.sh first, or set AITBC_ROOT"
        exit 1
    fi
    if [ ! -d "$VENV_DIR" ]; then
        error "Virtual environment not found at $VENV_DIR"
        error "Run setup.sh first"
        exit 1
    fi
}

# ----------------------------------------------------------------------------
# Load node role from env files (mirrors link-systemd.sh logic)
# Returns: "blockchain_mode:market_role:hardware_profile"
# ----------------------------------------------------------------------------
get_node_role() {
    local blockchain_mode="" market_role="" hardware_profile=""
    if [ -f "$BLOCKCHAIN_ENV_FILE" ]; then
        # shellcheck disable=SC1090
        source "$BLOCKCHAIN_ENV_FILE" 2>/dev/null
        blockchain_mode="${BLOCKCHAIN_MODE:-}"
        market_role="${MARKET_ROLE:-}"
        hardware_profile="${HARDWARE_PROFILE:-}"
    fi
    if [ -f "$NODE_ENV_FILE" ]; then
        # shellcheck disable=SC1090
        source "$NODE_ENV_FILE" 2>/dev/null
        blockchain_mode="${blockchain_mode:-${BLOCKCHAIN_MODE:-}}"
        market_role="${market_role:-${MARKET_ROLE:-}}"
        hardware_profile="${hardware_profile:-${HARDWARE_PROFILE:-}}"
    fi

    # Auto-detect GPU via nvidia-smi. If the env file says nogpu but a GPU
    # is present, override to gpu so the correct profile (provider-gpu) is
    # used and GPU dependencies (pycuda, torch, etc.) get installed.
    detect_gpu
    if [ "$DETECTED_HARDWARE" = "gpu" ] && [ "${hardware_profile:-nogpu}" != "gpu" ]; then
        warning "GPU detected (${GPU_NAME:-unknown}) but HARDWARE_PROFILE=${hardware_profile:-nogpu} — overriding to gpu"
        hardware_profile="gpu"
    elif [ "$DETECTED_HARDWARE" = "gpu" ]; then
        log "GPU confirmed: ${GPU_NAME:-unknown} (${GPU_COUNT:-1} device(s))"
    fi

    echo "${blockchain_mode:-follower}:${market_role:-customer}:${hardware_profile:-$DETECTED_HARDWARE}"
}

# Detect install-profiles.sh profile name from role (mirrors setup.sh)
get_profile() {
    local role_spec="$1"
    local blockchain_mode="${role_spec%%:*}"
    local rest="${role_spec#*:}"
    local market_role="${rest%%:*}"
    local hardware_profile="${rest##*:}"

    # Map role axes to valid install-profiles.sh profile names:
    #   provider-gpu    — any node with GPU (gets ai-ml.txt with pycuda, torch, etc.)
    #   hub             — hub node without GPU (full install with dev deps)
    #   customer-no-gpu — follower + customer, no GPU (lightweight CLI + wallet)
    #   server-no-gpu   — follower + shop, no GPU (core blockchain services)
    if [ "$hardware_profile" = "gpu" ]; then
        echo "provider-gpu"
    elif [ "$blockchain_mode" = "hub" ]; then
        echo "hub"
    elif [ "$market_role" = "customer" ]; then
        echo "customer-no-gpu"
    else
        echo "server-no-gpu"
    fi
}

# ----------------------------------------------------------------------------
# Step 0: Pre-update backup (trigger aitbc-backup.service)
# ----------------------------------------------------------------------------
run_pre_update_backup() {
    log "Step 0: Triggering pre-update backup..."
    if ! systemctl list-unit-files 2>/dev/null | grep -q '^aitbc-backup\.service'; then
        warning "aitbc-backup.service not installed — skipping pre-update backup"
        return 0
    fi

    log "Starting aitbc-backup.service (oneshot)..."
    if systemctl start aitbc-backup.service 2>/dev/null; then
        # Wait for the oneshot to finish (it exits when backup is done)
        log "Waiting for backup to complete..."
        local waited=0
        while systemctl is-active --quiet aitbc-backup.service 2>/dev/null; do
            sleep 2
            waited=$((waited + 2))
            if [ "$waited" -ge 300 ]; then
                warning "Backup still running after ${waited}s — proceeding with update"
                return 0
            fi
        done

        if systemctl is-success --quiet aitbc-backup.service 2>/dev/null \
           || systemctl show -p Result --value aitbc-backup.service 2>/dev/null | grep -q '^success$'; then
            success "Pre-update backup completed"
        else
            warning "aitbc-backup.service did not report success — check journalctl -u aitbc-backup.service"
            warning "Proceeding with update anyway (use --skip-backup to bypass next time)"
        fi
    else
        warning "Failed to start aitbc-backup.service — proceeding without pre-update backup"
        warning "Check: journalctl -u aitbc-backup.service -n 20"
    fi
}

# ----------------------------------------------------------------------------
# Step 1: git pull (with stash safety)
# ----------------------------------------------------------------------------
do_git_pull() {
    log "Step 1: Pulling latest code from $GIT_REMOTE (main)..."
    cd "$AITBC_ROOT" || { error "Cannot cd to $AITBC_ROOT"; return 1; }

    # Check for local changes
    if ! git diff --quiet || ! git diff --cached --quiet; then
        warning "Local changes detected — stashing before pull..."
        if ! git stash push -m "update.sh auto-stash $(date +%Y%m%d-%H%M%S)"; then
            error "Failed to stash local changes. Aborting pull."
            return 1
        fi
        local stashed=true
    fi

    local prev_head
    prev_head=$(git rev-parse HEAD)

    log "Step 1: Pulling latest code from $GIT_REMOTE (main)..."

    # Fetch first, then merge — works with URL directly (no remote ref needed)
    if ! git fetch "$GIT_REMOTE" main 2>/dev/null; then
        error "git fetch failed (network issue or bad remote: $GIT_REMOTE)"
        error "Check the URL or override with --gitea, --remote <url>, or AITBC_GIT_REMOTE env var"
        return 1
    fi

    if ! git merge --ff-only FETCH_HEAD; then
        error "git merge --ff-only failed (non-fast-forward or local commits diverged)"
        error "Resolve manually: cd $AITBC_ROOT && git pull --rebase $GIT_REMOTE main"
        if [ "${stashed:-}" = "true" ]; then
            warning "Your stashed changes are preserved: git stash list"
        fi
        return 1
    fi

    local new_head
    new_head=$(git rev-parse HEAD)

    if [ "$prev_head" = "$new_head" ]; then
        success "Already up to date (no changes pulled)"
        NO_CHANGES=true
    else
        success "Pulled new commits: $prev_head -> $new_head"
        git log --oneline "$prev_head".."$new_head" | head -20
        NO_CHANGES=false
    fi

    # Restore stashed changes
    if [ "${stashed:-}" = "true" ]; then
        warning "Attempting to restore stashed local changes..."
        if git stash pop; then
            success "Stashed changes restored"
        else
            error "Conflict restoring stash — resolve manually: git stash pop"
            error "Stash preserved: git stash list"
        fi
    fi
}

# ----------------------------------------------------------------------------
# Step 2: Sync Python venv
# ----------------------------------------------------------------------------
sync_venv() {
    log "Step 2: Syncing Python virtual environment..."
    if [ ! -f "$VENV_DIR/bin/activate" ]; then
        error "venv broken (no activate script). Run setup.sh to recreate."
        return 1
    fi

    # shellcheck disable=SC1091
    if ! source "$VENV_DIR/bin/activate"; then
        error "Failed to activate venv"
        return 1
    fi

    # Upgrade pip quietly
    pip install --upgrade pip --quiet 2>/dev/null || warning "pip upgrade failed (continuing)"

    # Try install-profiles.sh with detected profile (mirrors setup.sh)
    local role profile
    role=$(get_node_role)
    profile=$(get_profile "$role")
    log "Detected install profile: $profile"

    if [ -x "$INSTALL_PROFILES_SCRIPT" ]; then
        log "Running install-profiles.sh $profile..."
        if ! "$INSTALL_PROFILES_SCRIPT" "$profile" >/dev/null 2>&1; then
            warning "install-profiles.sh failed for profile '$profile' — falling back to requirements.txt"
            fallback_pip_install
        else
            success "Profile dependencies installed"
        fi
    else
        warning "install-profiles.sh not found — using requirements.txt fallback"
        fallback_pip_install
    fi

    # Always reinstall CLI (it's editable, but -e ensures entry points refresh)
    if [ -f "$AITBC_ROOT/cli/setup.py" ] || [ -f "$AITBC_ROOT/cli/pyproject.toml" ]; then
        log "Reinstalling AITBC CLI..."
        # shellcheck disable=SC2015
        ( cd "$AITBC_ROOT/cli" && pip install -e . --quiet 2>/dev/null ) \
            && success "CLI reinstalled" \
            || warning "CLI reinstall failed (continuing)"
    fi

    # Refresh editable local packages so imports like aitbc_agent_core resolve
    # even when install-profiles.sh falls back to requirements.txt.
    # Include packages/aitbc-shared as well as packages/py/*.
    local pkg_dirs=()
    if [ -d "$AITBC_ROOT/packages/aitbc-shared" ]; then
        pkg_dirs+=("$AITBC_ROOT/packages/aitbc-shared")
    fi
    if [ -d "$AITBC_ROOT/packages/py" ]; then
        for pkg in "$AITBC_ROOT/packages/py"/*/; do
            [ -f "$pkg/pyproject.toml" ] || continue
            pkg_dirs+=("$pkg")
        done
    fi

    if [ "${#pkg_dirs[@]}" -gt 0 ]; then
        log "Installing repo-local packages..."
        for pkg in "${pkg_dirs[@]}"; do
            # shellcheck disable=SC2015
            pip install -e "$pkg" --quiet 2>/dev/null \
                && success "Installed $(basename "$pkg")" \
                || warning "Failed to install $(basename "$pkg") (continuing)"
        done
    fi
}

fallback_pip_install() {
    log "Installing from requirements.txt..."
    if [ -f "$AITBC_ROOT/requirements.txt" ]; then
        # shellcheck disable=SC2015
        pip install -r "$AITBC_ROOT/requirements.txt" --quiet 2>/dev/null \
            && success "Core requirements installed" \
            || warning "Failed to install some core requirements"
    fi
    if [ -f "$AITBC_ROOT/cli/requirements-cli.txt" ]; then
        pip install -r "$AITBC_ROOT/cli/requirements-cli.txt" --quiet 2>/dev/null \
            || warning "Failed to install some CLI requirements"
    fi
}

# ----------------------------------------------------------------------------
# Step 3: Relink systemd unit files
# ----------------------------------------------------------------------------
relink_systemd() {
    log "Step 3: Relinking systemd unit files..."
    if [ ! -x "$LINK_SYSTEMD_SCRIPT" ]; then
        error "link-systemd.sh not found or not executable: $LINK_SYSTEMD_SCRIPT"
        return 1
    fi

    "$LINK_SYSTEMD_SCRIPT" 2>&1 | sed 's/^/    /'
    link_exit=${PIPESTATUS[0]}
    if [[ $link_exit -eq 0 ]]; then
        success "Systemd unit files relinked (role-aware)"
    else
        warning "link-systemd.sh reported errors (exit $link_exit) — check output above"
    fi

    log "Running systemctl daemon-reload..."
    # shellcheck disable=SC2015
    systemctl daemon-reload && success "daemon-reload complete" \
        || warning "daemon-reload failed"
}

# ----------------------------------------------------------------------------
# Step 4: Enable services for this role
# ----------------------------------------------------------------------------
enable_services() {
    log "Step 4: Ensuring services are enabled for this role..."
    local role
    role=$(get_node_role)
    log "Node role: $role"

    # Get list of currently-installed aitbc unit files (after relink)
    local svc
    for svc in /etc/systemd/system/aitbc-*.service; do
        [ -f "$svc" ] || continue
        local name
        name=$(basename "$svc")
        if systemctl enable "$name" 2>/dev/null | grep -q "Created symlink\|already enabled" ; then
            : # quiet on success
        fi
    done
    # Enable timers too
    local timer
    for timer in /etc/systemd/system/aitbc-*.timer; do
        [ -f "$timer" ] || continue
        systemctl enable "$(basename "$timer")" 2>/dev/null || true
    done
    success "Service enablement reviewed"
}

# ----------------------------------------------------------------------------
# Step 4a: Ensure shared and per-service env files exist
# ----------------------------------------------------------------------------
ensure_env_files() {
    log "Step 4a: Ensuring AITBC environment files exist..."
    mkdir -p /etc/aitbc

    local unit base env_file
    for unit in /etc/systemd/system/aitbc-*.service /etc/systemd/system/aitbc-*.timer; do
        [ -e "$unit" ] || continue
        base=$(basename "$unit")
        base="${base%.service}"
        base="${base%.timer}"
        env_file="/etc/aitbc/${base}.env"
        if [ ! -f "$env_file" ]; then
            touch "$env_file"
            chmod 644 "$env_file"
            log "Created missing per-service env file: $env_file"
        fi
    done

    for common in "$NODE_ENV_FILE" "$BLOCKCHAIN_ENV_FILE"; do
        if [ ! -f "$common" ]; then
            touch "$common"
            chmod 644 "$common"
            log "Created missing shared env file: $common"
        fi
    done
    success "Environment files verified"
}

# ----------------------------------------------------------------------------
# Step 4b: Update /usr/local/bin/aitbc wrapper if it is stale
# ----------------------------------------------------------------------------
ensure_aitbc_wrapper() {
    log "Step 4b: Ensuring aitbc CLI wrapper is up to date..."
    local wrapper="/usr/local/bin/aitbc"
    local expected='#!/bin/sh
set -e
. /opt/aitbc/venv/bin/activate
exec aitbc "$@"'

    if [ -f "$wrapper" ] && diff -q <(printf '%s\n' "$expected") "$wrapper" >/dev/null 2>&1; then
        log "aitbc wrapper already up to date"
        return 0
    fi

    printf '%s\n' "$expected" > "$wrapper"
    chmod +x "$wrapper"
    success "Updated aitbc wrapper at $wrapper"
}

# ----------------------------------------------------------------------------
# Step 4c: Ensure consensus-safety env defaults
# ----------------------------------------------------------------------------
ensure_consensus_env_defaults() {
    if [ ! -f "$BLOCKCHAIN_ENV_FILE" ]; then
        return
    fi
    if ! grep -q "^BLOCK_SCOPED_PREREGISTERED_TRANSACTIONS=" "$BLOCKCHAIN_ENV_FILE"; then
        echo "BLOCK_SCOPED_PREREGISTERED_TRANSACTIONS=true" >> "$BLOCKCHAIN_ENV_FILE"
        log "Added BLOCK_SCOPED_PREREGISTERED_TRANSACTIONS=true to $BLOCKCHAIN_ENV_FILE"
    fi
    if ! grep -q "^SYNC_STATE_ROOT_VALIDATION_ENABLED=" "$BLOCKCHAIN_ENV_FILE"; then
        echo "SYNC_STATE_ROOT_VALIDATION_ENABLED=true" >> "$BLOCKCHAIN_ENV_FILE"
        log "Added SYNC_STATE_ROOT_VALIDATION_ENABLED=true to $BLOCKCHAIN_ENV_FILE"
    fi
}

# ----------------------------------------------------------------------------
# Step 4d: Ensure gossip/subscription transport defaults
# ----------------------------------------------------------------------------
ensure_gossip_defaults() {
    if [ ! -f "$BLOCKCHAIN_ENV_FILE" ]; then
        return
    fi

    if ! grep -q "^subscription_enabled=" "$BLOCKCHAIN_ENV_FILE"; then
        echo "subscription_enabled=true" >> "$BLOCKCHAIN_ENV_FILE"
        log "Added subscription_enabled=true to $BLOCKCHAIN_ENV_FILE"
    fi
    if ! grep -q "^subscription_transport=" "$BLOCKCHAIN_ENV_FILE"; then
        echo "subscription_transport=websocket" >> "$BLOCKCHAIN_ENV_FILE"
        log "Added subscription_transport=websocket to $BLOCKCHAIN_ENV_FILE"
    fi

    local blockchain_mode=""
    if [ -f "$BLOCKCHAIN_ENV_FILE" ]; then
        blockchain_mode=$(grep "^BLOCKCHAIN_MODE=" "$BLOCKCHAIN_ENV_FILE" | cut -d= -f2 | tr -d '[:space:]')
    fi
    blockchain_mode="${blockchain_mode:-follower}"

    if [ "$blockchain_mode" = "hub" ]; then
        if ! grep -q "^gossip_backend=" "$BLOCKCHAIN_ENV_FILE"; then
            echo "gossip_backend=redis" >> "$BLOCKCHAIN_ENV_FILE"
            log "Added gossip_backend=redis to $BLOCKCHAIN_ENV_FILE"
        fi
        if ! grep -q "^gossip_broadcast_url=" "$BLOCKCHAIN_ENV_FILE"; then
            echo "gossip_broadcast_url=redis://localhost:6379" >> "$BLOCKCHAIN_ENV_FILE"
            log "Added gossip_broadcast_url to $BLOCKCHAIN_ENV_FILE"
        fi
    else
        if ! grep -q "^gossip_backend=" "$BLOCKCHAIN_ENV_FILE"; then
            echo "gossip_backend=websocket" >> "$BLOCKCHAIN_ENV_FILE"
            log "Added gossip_backend=websocket to $BLOCKCHAIN_ENV_FILE"
        fi
        if ! grep -q "^gossip_websocket_url=" "$BLOCKCHAIN_ENV_FILE"; then
            # Derive from default_peer_rpc_url if present, else assume local.
            local hub_url
            hub_url=$(grep "^default_peer_rpc_url=" "$BLOCKCHAIN_ENV_FILE" | cut -d= -f2- | tr -d '[:space:]')
            if [ -n "$hub_url" ] && [ "$hub_url" != "http://127.0.0.1:8202" ]; then
                hub_url="$(printf '%s' "$hub_url" | sed 's|^https://|wss://|; s|^http://|ws://|')/rpc/gossip/ws"
            else
                hub_url="wss://hub.aitbc.bubuit.net/rpc/gossip/ws"
            fi
            echo "gossip_websocket_url=$hub_url" >> "$BLOCKCHAIN_ENV_FILE"
            log "Added gossip_websocket_url to $BLOCKCHAIN_ENV_FILE"
        fi
    fi
}

# ----------------------------------------------------------------------------
# Step 5: Run Alembic DB migrations for all services with alembic.ini
#
# The logic lives in run-migrations.sh so that deploy.sh, which installs a node from
# scratch, runs the same thing. It used to live here alone, which is why a first install
# started every service without ever migrating (V23-79). Exec'd rather than sourced: it
# sets `set -euo pipefail`, which this script refuses on purpose (see line 40).
# ----------------------------------------------------------------------------
run_migrations() {
    log "Step 5: Running Alembic DB migrations..."
    AITBC_ROOT="$AITBC_ROOT" VENV_DIR="$VENV_DIR" "$RUN_MIGRATIONS_SCRIPT"
}

# ----------------------------------------------------------------------------
# Step 6: Restart all aitbc services
# ----------------------------------------------------------------------------
restart_services() {
    log "Step 6: Restarting all aitbc services..."
    local services=()
    local svc

    # Gather currently-active aitbc services
    while read -r svc; do
        [ -n "$svc" ] && services+=("$svc")
    done < <(systemctl list-units --type=service --state=running --no-legend --no-pager 2>/dev/null | awk '$1 ~ /^aitbc-/{print $1}')

    if [ "${#services[@]}" -eq 0 ]; then
        warning "No aitbc services currently running — nothing to restart"
        return 0
    fi

    log "Restarting ${#services[@]} services: ${services[*]}"
    local failed=()
    for svc in "${services[@]}"; do
        if systemctl restart "$svc" 2>/dev/null; then
            log "  restarted: $svc"
        else
            warning "  failed to restart: $svc"
            failed+=("$svc")
        fi
    done

    # Give services a moment to come up
    log "Waiting 10s for services to settle..."
    sleep 10

    local active_count=0
    for svc in "${services[@]}"; do
        systemctl is-active --quiet "$svc" 2>/dev/null && ((active_count++))
    done
    log "Services active after restart: ${active_count}/${#services[@]}"

    if [ "${#failed[@]}" -gt 0 ]; then
        warning "Failed to restart: ${failed[*]}"
        warning "Inspect logs: journalctl -u <service> -n 50 --no-pager"
    fi
}

# ----------------------------------------------------------------------------
# Step 6: Health check
# ----------------------------------------------------------------------------
run_health_check() {
    log "Step 7: Running health check..."
    if [ ! -x "$HEALTH_CHECK_SCRIPT" ]; then
        warning "Health check script not found or not executable: $HEALTH_CHECK_SCRIPT"
        return 0
    fi
    if "$HEALTH_CHECK_SCRIPT"; then
        success "Health check passed"
    else
        warning "Health check reported issues — see output above"
    fi
}

# ----------------------------------------------------------------------------
# Step 8: Summary + manual follow-up reminders
# ----------------------------------------------------------------------------
print_summary() {
    local role
    role=$(get_node_role)
    echo ""
    echo "=== AITBC UPDATE COMPLETE ==="
    echo "  Node role:  $role"
    echo "  Repo:       $AITBC_ROOT  ($(git -C "$AITBC_ROOT" rev-parse --short HEAD 2>/dev/null))"
    echo "  Remote:     $GIT_REMOTE"
    echo "  Venv:       $VENV_DIR"
    echo ""
    if [ "${DO_RESTART}" = "true" ]; then
        echo "  Services restarted and health-checked."
    else
        echo "  Services NOT restarted (--no-restart). Apply manually if needed:"
        echo "    sudo systemctl restart aitbc-*"
    fi
    if [ "${DO_MIGRATE}" = "true" ]; then
        echo "  DB migrations run automatically (see Step 5 output above)."
    else
        echo "  DB migrations NOT run (--no-migrate). Apply manually if needed (see below)."
    fi
    echo ""
    echo "  Manual follow-ups to consider:"
    # Discovered, not hardcoded: this list read "blockchain-node, pool-hub, governance,
    # trading" long after coordinator-api, edge and gpu had gained an alembic.ini.
    echo "    - DB migrations (alembic) — services with alembic.ini:"
    local ini svc
    while IFS= read -r ini; do
        svc=$(basename "$(dirname "$ini")")
        [ "$svc" = "blockchain-node" ] && continue
        echo "        cd $AITBC_ROOT/apps/$svc && PYTHONPATH=src ../../venv/bin/alembic upgrade head"
    done < <(find "$AITBC_ROOT/apps" -maxdepth 3 -name "alembic.ini" 2>/dev/null | sort)
    echo "      blockchain-node is per-island — name the database, and stop the node first."
    echo "      Its default target is /var/lib/aitbc/data/chain.db, which no node uses:"
    local island_db
    for island_db in /var/lib/aitbc/data/*/chain.db; do
        [ -e "$island_db" ] || continue
        echo "        DATABASE_URL=sqlite:///$island_db \\"
        echo "          $AITBC_ROOT/venv/bin/alembic -c $AITBC_ROOT/apps/blockchain-node/alembic.ini upgrade head"
    done
    echo "    - Review changed config templates in examples/ vs /etc/aitbc/"
    echo "    - If nginx configs changed, update both container + host proxy:"
    echo "        Container: /opt/aitbc/examples/nginx/nginx-*.conf.example"
    echo "        Host proxy: /opt/aitbc/examples/nginx/nginx-*-proxy.conf.example"
    echo "        See: /opt/aitbc/examples/nginx/README.md"
    echo "    - Check logs for all running aitbc services:"
    echo "        journalctl -u 'aitbc-*' -n 50 --no-pager --since '5 min ago'"
    echo "      Or per-service, e.g.:"
    echo "        journalctl -u aitbc-blockchain-node -n 50 --no-pager"
    echo "        journalctl -u aitbc-trading -n 50 --no-pager"
    echo "        journalctl -u aitbc-governance -n 50 --no-pager"
    echo "        journalctl -u aitbc-pool-hub -n 50 --no-pager"
    echo ""
}

# ----------------------------------------------------------------------------
# Main
# ----------------------------------------------------------------------------
main() {
    parse_args "$@"
    echo "=== AITBC UPDATE STARTED ==="
    log "AITBC_ROOT=$AITBC_ROOT"

    check_root
    check_repo

    if [ "$DO_BACKUP" = "true" ]; then
        run_pre_update_backup
    else
        log "Skipping pre-update backup (--skip-backup)"
    fi

    if [ "$DO_PULL" = "true" ]; then
        do_git_pull || exit 1
        if [ "${NO_CHANGES:-false}" = "true" ] && [ "$DO_RESTART" = "false" ] && [ "$DO_MIGRATE" = "false" ]; then
            success "No changes, --no-restart and --no-migrate set — nothing to do"
            exit 0
        fi
    else
        log "Skipping git pull (--no-pull)"
        NO_CHANGES=false
    fi

    sync_venv
    relink_systemd
    enable_services
    ensure_env_files
    ensure_aitbc_wrapper
    ensure_consensus_env_defaults
    ensure_gossip_defaults

    if [ "$DO_MIGRATE" = "true" ]; then
        run_migrations || exit 1
    else
        log "Skipping DB migrations (--no-migrate)"
    fi

    if [ "$DO_RESTART" = "true" ]; then
        restart_services
        run_health_check
    else
        log "Skipping service restart and health check (--no-restart)"
    fi

    print_summary
    success "Update finished"

    agent_print_followup
}

main "$@"
