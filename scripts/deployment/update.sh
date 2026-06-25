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
#   6. Restart all aitbc services
#   7. Run health check
#   8. Print summary + DB migration reminder
#
# Usage:
#   sudo /opt/aitbc/scripts/deployment/update.sh
#   sudo /opt/aitbc/scripts/deployment/update.sh --no-pull    # skip git pull
#   sudo /opt/aitbc/scripts/deployment/update.sh --no-restart # skip service restart
#   sudo /opt/aitbc/scripts/deployment/update.sh --skip-backup # skip pre-update backup
#   sudo /opt/aitbc/scripts/deployment/update.sh --remote URL # override git remote
#
# Prerequisites:
#   - Node already set up via setup.sh
#   - /etc/aitbc/node.env and/or /etc/aitbc/blockchain.env present
#
# Git remote:
#   Defaults to https://github.com/oib/AITBC.git (public repo).
#   Override with --remote <url> or AITBC_GIT_REMOTE env var.
# ============================================================================

set -u  # error on unset vars; do NOT use -e (we want to continue past soft failures)

AITBC_ROOT="${AITBC_ROOT:-/opt/aitbc}"
VENV_DIR="$AITBC_ROOT/venv"
NODE_ENV_FILE="/etc/aitbc/node.env"
BLOCKCHAIN_ENV_FILE="/etc/aitbc/blockchain.env"
HEALTH_CHECK_SCRIPT="$AITBC_ROOT/scripts/monitoring/health_check.sh"
LINK_SYSTEMD_SCRIPT="$AITBC_ROOT/scripts/utils/link-systemd.sh"
INSTALL_PROFILES_SCRIPT="$AITBC_ROOT/scripts/deployment/install-profiles.sh"

# Public Git remote — pull from GitHub by default.
# Override with --remote flag or AITBC_GIT_REMOTE env var.
GIT_REMOTE="${AITBC_GIT_REMOTE:-https://github.com/oib/AITBC.git}"

# Flags
DO_PULL=true
DO_RESTART=true
DO_BACKUP=true

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m'

log()     { echo -e "${BLUE}[$(date +'%H:%M:%S')]${NC} $*"; }
success() { echo -e "${GREEN}[$(date +'%H:%M:%S')] ✓${NC} $*"; }
warning() { echo -e "${YELLOW}[$(date +'%H:%M:%S')] ⚠${NC} $*" >&2; }
error()   { echo -e "${RED}[$(date +'%H:%M:%S')] ✗${NC} $*" >&2; }

# ----------------------------------------------------------------------------
# Parse arguments
# ----------------------------------------------------------------------------
parse_args() {
    while [ $# -gt 0 ]; do
        case "$1" in
            --no-pull)    DO_PULL=false; shift ;;
            --no-restart) DO_RESTART=false; shift ;;
            --skip-backup) DO_BACKUP=false; shift ;;
            --remote)     GIT_REMOTE="$2"; shift 2 ;;
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
    echo "${blockchain_mode:-follower}:${market_role:-customer}:${hardware_profile:-nogpu}"
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
        error "Check the URL or override with --remote <url> or AITBC_GIT_REMOTE env var"
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
        ( cd "$AITBC_ROOT/cli" && pip install -e . --quiet 2>/dev/null ) \
            && success "CLI reinstalled" \
            || warning "CLI reinstall failed (continuing)"
    fi
}

fallback_pip_install() {
    log "Installing from requirements.txt..."
    if [ -f "$AITBC_ROOT/requirements.txt" ]; then
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
    for svc in $(ls /etc/systemd/system/aitbc-*.service 2>/dev/null); do
        local name
        name=$(basename "$svc")
        if systemctl enable "$name" 2>/dev/null | grep -q "Created symlink\|already enabled" ; then
            : # quiet on success
        fi
    done
    # Enable timers too
    for timer in $(ls /etc/systemd/system/aitbc-*.timer 2>/dev/null); do
        systemctl enable "$(basename "$timer")" 2>/dev/null || true
    done
    success "Service enablement reviewed"
}

# ----------------------------------------------------------------------------
# Step 5: Restart all aitbc services
# ----------------------------------------------------------------------------
restart_services() {
    log "Step 5: Restarting all aitbc services..."
    local services=()
    local svc

    # Gather currently-active aitbc services
    while read -r svc; do
        [ -n "$svc" ] && services+=("$svc")
    done < <(systemctl list-units --type=service --state=running --no-legend 2>/dev/null | awk '/^aitbc-/{print $1}')

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
    log "Step 6: Running health check..."
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
# Step 7: Summary + DB migration reminder
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
    echo ""
    echo "  Manual follow-ups to consider:"
    echo "    - DB migrations (alembic) if schema changed:"
    echo "        cd $AITBC_ROOT/apps/blockchain-node && alembic upgrade head"
    echo "    - Review changed config templates in examples/ vs /etc/aitbc/"
    echo "    - If nginx configs changed, update both container + host proxy:"
    echo "        Container: /opt/aitbc/examples/nginx/nginx-*.conf.example"
    echo "        Host proxy: /opt/aitbc/examples/nginx/nginx-*-proxy.conf.example"
    echo "        See: /opt/aitbc/examples/nginx/README.md"
    echo "    - Check logs: journalctl -u aitbc-blockchain-node -n 50 --no-pager"
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
        if [ "${NO_CHANGES:-false}" = "true" ] && [ "$DO_RESTART" = "false" ]; then
            success "No changes and --no-restart set — nothing to do"
            exit 0
        fi
    else
        log "Skipping git pull (--no-pull)"
        NO_CHANGES=false
    fi

    sync_venv
    relink_systemd
    enable_services

    if [ "$DO_RESTART" = "true" ]; then
        restart_services
        run_health_check
    else
        log "Skipping service restart and health check (--no-restart)"
    fi

    print_summary
    success "Update finished"
}

main "$@"
