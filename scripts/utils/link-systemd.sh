#!/bin/bash

# AITBC Systemd Link Script
# Creates symbolic links from active systemd to repository systemd files
# Keeps active systemd always in sync with repository
# Role-aware: only links services appropriate for this node's role

# nounset and pipefail are on; errexit is deliberately not (V23-23 ratchet).
# This script links dozens of unit files and is written to continue past an individual
# failure, counting them in $error_count and reporting at the end -- one bad symlink must
# not abort the remaining services. That is why `set -e` was disabled here originally. The
# other two are what V23-23 was actually about (a mistyped name expanding to empty) and
# they are kept on.
set -euo pipefail
set +e

# Resolved from this script's own location rather than hardcoded to /opt/aitbc, which only
# existed on the node hosts. Since AITBC-136 CI checks the repository out into the runner
# workspace, and the hardcoded path made this fail with "Repository apps directory not
# found" before it could link anything.
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"

REPO_APPS_DIR="$REPO_ROOT/apps"
REPO_SCRIPTS_DIR="$REPO_ROOT/scripts"
ACTIVE_SYSTEMD_DIR="/etc/systemd/system"
REPO_CONFIG_DIR="$REPO_ROOT/scripts/config"
ACTIVE_TMPFILES_DIR="/etc/tmpfiles.d"

echo "=== AITBC SYSTEMD LINKING ==="
echo "Repository Apps: $REPO_APPS_DIR"
echo "Repository Scripts: $REPO_SCRIPTS_DIR"
echo "Active: $ACTIVE_SYSTEMD_DIR"
echo "Config: $REPO_CONFIG_DIR"
echo "Tmpfiles: $ACTIVE_TMPFILES_DIR"
echo

# Check if running as root
if [[ $EUID -ne 0 ]]; then
   echo "❌ This script must be run as root (use sudo)"
   echo "   sudo $0"
   exit 1
fi

# Check if repository directories exist
if [[ ! -d "$REPO_APPS_DIR" ]]; then
    echo "❌ Repository apps directory not found: $REPO_APPS_DIR"
    exit 1
fi

if [[ ! -d "$REPO_SCRIPTS_DIR" ]]; then
    echo "❌ Repository scripts directory not found: $REPO_SCRIPTS_DIR"
    exit 1
fi

# -----------------------------------------------------------------------------
# Role-aware service selection
# Determines which services to link based on node role from env config.
# Falls back to linking everything if role config is unavailable (initial setup).
# -----------------------------------------------------------------------------

get_node_role() {
    local blockchain_mode="" market_role="" hardware_profile=""
    if [ -f "/etc/aitbc/blockchain.env" ]; then
        source /etc/aitbc/blockchain.env 2>/dev/null
        blockchain_mode="${BLOCKCHAIN_MODE:-}"
        market_role="${MARKET_ROLE:-}"
        hardware_profile="${HARDWARE_PROFILE:-}"
    fi
    if [ -f "/etc/aitbc/node.env" ]; then
        source /etc/aitbc/node.env 2>/dev/null
        # node.env is node-specific and must override the public blockchain.env.
        blockchain_mode="${BLOCKCHAIN_MODE:-$blockchain_mode}"
        market_role="${MARKET_ROLE:-$market_role}"
        hardware_profile="${HARDWARE_PROFILE:-$hardware_profile}"
    fi

    # Output both axes so get_allowed_services can combine them
    echo "${blockchain_mode:-follower}:${market_role:-customer}:${hardware_profile:-nogpu}"
}

# Get allowed service basenames (without .service/.timer suffix) for a role.
# Also includes infrastructure services that should always be linked.
# Combines BLOCKCHAIN_MODE and MARKET_ROLE as independent axes:
#   BLOCKCHAIN_MODE: hub | follower
#   MARKET_ROLE:     customer | shop
#   HARDWARE:        gpu | nogpu
get_allowed_services() {
    local role_spec="${1:-all}"

    # Infrastructure services — always linked regardless of role
    local infra_services=(
        aitbc-load-secrets
        aitbc-recovery
    )

    # Base services — always enabled on every node
    local base_services=(
        aitbc-blockchain-node
        aitbc-blockchain-rpc
        aitbc-wallet
        aitbc-recovery
        aitbc-monitoring
        aitbc-backup
        aitbc-trading
        aitbc-governance
        aitbc-chain-isolation-monitor
        aitbc-memory-monitor
    )

    # Hub-specific services (blockchain producer)
    local hub_services=(
        aitbc-blockchain-p2p
        aitbc-coordinator-api
        aitbc-api-gateway
        aitbc-exchange
        aitbc-market
        aitbc-bridge-monitor
        aitbc-blockchain-event-bridge
        aitbc-agent-coordinator
        aitbc-blockchain-explorer
    )

    # Follower-specific services (blockchain sync, in addition to base)
    local follower_services=(
        aitbc-blockchain-explorer
    )

    # Shop-specific services (GPU provider, regardless of blockchain mode)
    local shop_services=(
        aitbc-gpu
        aitbc-miner
        aitbc-coordinator-api
        aitbc-edge
        # aitbc-pool-hub is not a shop-side service — add it via
        # EXTRA_SERVICES on hosts that should run one.
        aitbc-market
        aitbc-hermes-agent
        aitbc-whisper
        aitbc-ffmpeg
    )

    if [ "$role_spec" = "all" ]; then
        echo "all"
        return
    fi

    # Parse role_spec: blockchain_mode:market_role:hardware_profile
    local blockchain_mode="${role_spec%%:*}"
    local rest="${role_spec#*:}"
    local market_role="${rest%%:*}"
    local hardware_profile="${rest##*:}"

    # Start with infra + base
    local services=()
    for s in "${infra_services[@]}" "${base_services[@]}"; do
        services+=("$s")
    done

    # Axis 1: BLOCKCHAIN_MODE
    if [ "$blockchain_mode" = "hub" ]; then
        for s in "${hub_services[@]}"; do services+=("$s"); done
    else
        for s in "${follower_services[@]}"; do services+=("$s"); done
    fi

    # Axis 2: MARKET_ROLE (independent of blockchain mode)
    if [ "$market_role" = "shop" ]; then
        for s in "${shop_services[@]}"; do services+=("$s"); done
    fi

    # Print unique services
    printf '%s\n' "${services[@]}" | sort -u
}

# Determine node role (blockchain_mode:market_role:hardware_profile)
NODE_ROLE=$(get_node_role)
echo "🎯 Node role: $NODE_ROLE"

# Get allowed services list (combines both axes)
ALLOWED_SERVICES=$(get_allowed_services "$NODE_ROLE")

# Check if we should filter (role-aware) or link everything
if [ "$ALLOWED_SERVICES" = "all" ]; then
    echo "ℹ️  No role config found — linking all services (initial setup mode)"
    ROLE_FILTER=false
else
    echo "📋 Role-based service filtering enabled"
    ROLE_FILTER=true
fi

# Check if a service basename is in the allowed list
is_service_allowed() {
    local basename="$1"
    # aitbc-cache-monitor is not a role service: it belongs on hosts that run a
    # local redis-server (its optional EnvironmentFile /etc/aitbc/redis.env
    # supplies REDISCLI_AUTH). Gate on Redis presence so a relink does not
    # silently remove it and non-Redis hosts never get a failing timer.
    if [ "$basename" = "aitbc-cache-monitor" ]; then
        # systemctl cat avoids the list-unit-files|grep -q pipe: under pipefail,
        # grep -q's early exit SIGPIPEs systemctl and the pipeline reports 141.
        systemctl cat redis-server.service >/dev/null 2>&1
        return
    fi
    if [ "$basename" = "aitbc-island-ipfs" ]; then
        # Island IPFS is island infrastructure, not a blockchain-mode or
        # market-role service: it runs on whichever nodes form the island,
        # whatever their hub/follower axis says.
        # Gate on the env file the unit itself consumes, mirroring the
        # cache-monitor/redis rule above, so a relink does not delete it.
        [ -f /etc/aitbc/aitbc-island-ipfs.env ]
        return
    fi
    # Per-node escape hatch for units the three role axes cannot express (e.g.
    # a demoted hub that still serves the market). /etc/aitbc/node.env may
    # declare:   EXTRA_SERVICES="aitbc-market aitbc-island-ipfs"
    if [[ -z "${EXTRA_SERVICES+x}" && -f /etc/aitbc/node.env ]]; then
        EXTRA_SERVICES=$(grep -E '^EXTRA_SERVICES=' /etc/aitbc/node.env | tail -1 | cut -d= -f2- | tr -d '"')
    fi
    for extra in ${EXTRA_SERVICES:-}; do
        if [ "$basename" = "$extra" ]; then
            return 0
        fi
    done
    if [ "$ROLE_FILTER" = "false" ]; then
        return 0  # Allow all
    fi
    echo "$ALLOWED_SERVICES" | grep -qxF "$basename"
}

echo "🔍 Creating symbolic links for AITBC systemd files..."

# Remove existing aitbc-* files and stale drop-in directories
echo "🧹 Removing existing systemd files..."
find "$ACTIVE_SYSTEMD_DIR" -maxdepth 1 -name "aitbc-*" \( -type f -o -type l \) -delete 2>/dev/null || true
find "$ACTIVE_SYSTEMD_DIR" -maxdepth 1 -name "aitbc-*.d" -type l -exec rm -rf {} + 2>/dev/null || true

# Create symbolic links
echo "🔗 Creating symbolic links..."
linked_files=0
error_count=0
# Unit names that were actually linked, which drives the enable pass below.
LINKED_UNITS=()

# Find all systemd service files in apps directory
echo "📁 Scanning apps directory..."
for file in "$REPO_APPS_DIR"/*/aitbc-*.service "$REPO_APPS_DIR"/*/aitbc-*.timer; do
    if [[ -f "$file" ]]; then
        filename=$(basename "$file")
        target="$ACTIVE_SYSTEMD_DIR/$filename"
        source="$file"

        # Role-aware filtering: skip services not in this node's role
        svc_base="${filename%.service}"
        svc_base="${svc_base%.timer}"
        if ! is_service_allowed "$svc_base"; then
            echo "  ⏭️  Skipping (not in $NODE_ROLE role): $filename"
            continue
        fi

        echo "  🔗 Linking: $filename -> $source"

        # Create symbolic link
        if ln -sf "$source" "$target" 2>/dev/null; then
            echo "    ✅ Successfully linked: $filename"
            LINKED_UNITS+=("$filename")
        else
            echo "    ❌ Failed to link: $filename"
            ((error_count++))
        fi

        # Handle .d directories
        if [[ -d "${file}.d" ]]; then
            target_dir="${target}.d"
            source_dir="${file}.d"

            echo "    📁 Linking directory: ${filename}.d -> ${source_dir}"

            # Remove existing directory
            rm -rf "$target_dir" 2>/dev/null || true

            # Create symbolic link for directory
            if ln -sf "$source_dir" "$target_dir" 2>/dev/null; then
                echo "    ✅ Successfully linked directory: ${filename}.d"
            else
                echo "    ❌ Failed to link directory: ${filename}.d"
                ((error_count++))
            fi
        fi

        ((linked_files++))
    fi
done

# Find all systemd service files in scripts directory.
# `*/aitbc-*` already covers utils/ and monitoring/; naming them again made the
# loop process those nine files twice, inflating $linked_files and running the
# enable pass on each of them a second time.
echo "📁 Scanning scripts directory..."
for file in "$REPO_SCRIPTS_DIR"/*/aitbc-*.service "$REPO_SCRIPTS_DIR"/*/aitbc-*.timer; do
    if [[ -f "$file" ]]; then
        filename=$(basename "$file")
        target="$ACTIVE_SYSTEMD_DIR/$filename"
        source="$file"

        # Role-aware filtering: skip services not in this node's role
        svc_base="${filename%.service}"
        svc_base="${svc_base%.timer}"
        if ! is_service_allowed "$svc_base"; then
            echo "  ⏭️  Skipping (not in $NODE_ROLE role): $filename"
            continue
        fi

        echo "  🔗 Linking: $filename -> $source"

        # Create symbolic link
        if ln -sf "$source" "$target" 2>/dev/null; then
            echo "    ✅ Successfully linked: $filename"
            LINKED_UNITS+=("$filename")
        else
            echo "    ❌ Failed to link: $filename"
            ((error_count++))
        fi

        # Handle .d directories
        if [[ -d "${file}.d" ]]; then
            target_dir="${target}.d"
            source_dir="${file}.d"

            echo "    📁 Linking directory: ${filename}.d -> ${source_dir}"

            # Remove existing directory
            rm -rf "$target_dir" 2>/dev/null || true

            # Create symbolic link for directory
            if ln -sf "$source_dir" "$target_dir" 2>/dev/null; then
                echo "    ✅ Successfully linked directory: ${filename}.d"
            else
                echo "    ❌ Failed to link directory: ${filename}.d"
                ((error_count++))
            fi
        fi

        ((linked_files++))
    fi
done

echo
echo "📊 Linking Summary:"
echo "  Files processed: $linked_files"
echo "  Errors encountered: $error_count"

if [[ $error_count -gt 0 ]]; then
    echo "⚠️  Some links failed, but continuing..."
else
    echo "✅ All links created successfully"
fi

echo
echo "🔄 Reloading systemd daemon..."
if systemctl daemon-reload 2>/dev/null; then
    echo "    ✅ Systemd daemon reloaded successfully"
else
    echo "    ⚠️  Systemd daemon reload failed, but continuing..."
fi

echo
echo "⚙️  Enabling allowed units for boot..."
# `ln -sf` alone leaves units in `linked` state — they start manually but are
# not part of the boot transaction, so a reboot silently drops them.
#
# This is driven off the units actually linked above, not off $ALLOWED_SERVICES:
# is_service_allowed() is deliberately wider than the role list (EXTRA_SERVICES
# from node.env, plus the aitbc-island-ipfs and aitbc-cache-monitor gates), so
# keying on the role list left exactly those units linked but never enabled --
# on a demoted hub that is most of what the node actually runs.
if [[ "$ROLE_FILTER" == "false" ]]; then
    # Initial-setup mode links every unit in the repo. Enabling them all would
    # put services this host may not be meant to run into the boot transaction,
    # so leave the decision to a declared role.
    echo "    ℹ️  No role config — nothing enabled; declare a role and re-run"
elif [[ ${#LINKED_UNITS[@]} -eq 0 ]]; then
    echo "    ℹ️  Nothing was linked — nothing to enable"
else
    enable_unit() {
        if systemctl enable "$1" >/dev/null 2>&1; then
            echo "    ✅ Enabled: $1"
        else
            echo "    ⚠️  Could not enable: $1"
            ((error_count++))
        fi
    }

    # Basenames that got a timer: for those, the timer is the activation unit.
    timer_bases=" "
    for unit in "${LINKED_UNITS[@]}"; do
        if [[ "$unit" == *.timer ]]; then
            timer_bases="${timer_bases}${unit%.timer} "
        fi
    done

    # Timers first — enabling one is what puts the pair in the boot transaction.
    for unit in "${LINKED_UNITS[@]}"; do
        if [[ "$unit" == *.timer ]]; then
            enable_unit "$unit"
        fi
    done

    for unit in "${LINKED_UNITS[@]}"; do
        [[ "$unit" == *.service ]] || continue
        # A timer-activated oneshot must not also be wanted by multi-user.target:
        # that adds a run at every boot on top of the schedule.
        if [[ "$timer_bases" == *" ${unit%.service} "* ]]; then
            echo "    ⏭️  Timer-activated, not enabled separately: $unit"
            continue
        fi
        # No [Install] means systemctl enable cannot work. Expected for units
        # something else pulls in as a dependency; report rather than fail.
        if ! grep -q '^\[Install\]' "$ACTIVE_SYSTEMD_DIR/$unit"; then
            echo "    ⏭️  No [Install] section, not enabled: $unit"
            continue
        fi
        enable_unit "$unit"
    done
fi

echo
echo "🧹 Removing stale boot dependencies..."
# The sweep near the top only clears $ACTIVE_SYSTEMD_DIR itself. A unit that was
# once enabled also left a symlink under <target>.wants/, and that entry names the
# unit rather than the file -- systemd resolves the name against the unit search
# path. Once the unit is no longer linked (a role change, or a service that predates
# role filtering) the dependency survives in the target and resolves to nothing, so
# every boot carries a Wants= on a unit that cannot load.
#
# Removal is keyed on systemd's own view, never on guesswork: an entry goes only
# if the unit reports LoadState=not-found, or if it is a service some timer
# already triggers. A unit shipped elsewhere in the search path therefore stays
# untouched. This runs after the enable pass above, which legitimately creates
# .wants/ entries of its own.
stale_wants=0
if systemctl --version >/dev/null 2>&1; then
    for wants_link in "$ACTIVE_SYSTEMD_DIR"/*.wants/aitbc-*; do
        [[ -L "$wants_link" ]] || continue
        wants_unit=$(basename "$wants_link")
        reason=""
        if [[ "$(systemctl show -p LoadState --value "$wants_unit" 2>/dev/null)" == "not-found" ]]; then
            reason="unresolvable"
        elif [[ "$wants_unit" == *.service ]] &&
             [[ -n "$(systemctl show -p TriggeredBy --value "$wants_unit" 2>/dev/null)" ]]; then
            # Mirrors the enable pass above: for a timer-activated service the timer
            # is the unit that belongs in the boot transaction, so a boot entry here
            # adds a run at every boot on top of the schedule.
            reason="timer-activated"
        fi
        [[ -n "$reason" ]] || continue
        if rm -f "$wants_link" 2>/dev/null; then
            echo "    🗑️  Removed $reason: $(basename "$(dirname "$wants_link")")/$wants_unit"
            stale_wants=$((stale_wants + 1))
        else
            echo "    ⚠️  Could not remove: $wants_link"
            ((error_count++))
        fi
    done
    if [[ $stale_wants -gt 0 ]]; then
        systemctl daemon-reload 2>/dev/null || true
        echo "    ✅ Cleared $stale_wants stale boot dependencies"
    else
        echo "    ✅ None found"
    fi
else
    echo "    ⏭️  systemctl unavailable, skipped"
fi

echo
echo "📁 Deploying tmpfiles.d configurations..."
if [[ -d "$REPO_CONFIG_DIR" ]]; then
    for file in "$REPO_CONFIG_DIR"/*.conf; do
        if [[ -f "$file" ]]; then
            filename=$(basename "$file")
            target="$ACTIVE_TMPFILES_DIR/$filename"
            echo "  📋 Deploying: $filename -> $target"
            if deploy_err=$(cp "$file" "$target" 2>&1); then
                echo "    ✅ Successfully deployed: $filename"
            else
                echo "    ❌ Failed to deploy: $filename: $deploy_err"
                ((error_count++))
            fi
        fi
    done
else
    echo "  ℹ️  Config directory not found: $REPO_CONFIG_DIR (skipping tmpfiles.d deployment)"
fi

echo
echo "✅ Systemd linking completed!"
echo
echo "📊 Linking Summary:"
echo "  Linked files: $linked_files"
echo "  Repository Apps: $REPO_APPS_DIR"
echo "  Repository Scripts: $REPO_SCRIPTS_DIR"
echo "  Active: $ACTIVE_SYSTEMD_DIR"
echo
echo "🎯 Benefits:"
echo "  ✅ Active systemd files always match repository"
echo "  ✅ No gap between repo and running services"
echo "  ✅ Changes in repo immediately reflected"
echo "  ✅ Automatic sync on every repository update"
echo
echo "🔧 To restart services:"
echo "  sudo systemctl restart aitbc-blockchain-node"
echo "  sudo systemctl restart aitbc-coordinator-api"
echo "  # ... or restart all AITBC services:"
echo "  sudo systemctl restart aitbc-*"
echo
echo "🔍 To check status:"
echo "  sudo systemctl status aitbc-*"
echo
echo "🔍 To verify links:"
echo "  ls -la /etc/systemd/system/aitbc-*"
echo "  readlink /etc/systemd/system/aitbc-blockchain-node.service"

# Exit code reflects link, enable and tmpfiles deployment errors
if [[ $error_count -gt 0 ]]; then
    echo "⚠️  Script completed with $error_count error(s) and $linked_files file(s) linked"
    exit 1
elif [[ $linked_files -gt 0 ]]; then
    echo "✅ Script completed successfully with $linked_files files linked"
    exit 0
else
    echo "⚠️  No files were linked, but script completed"
    exit 0
fi
