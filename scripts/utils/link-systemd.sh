#!/bin/bash

# AITBC Systemd Link Script
# Creates symbolic links from active systemd to repository systemd files
# Keeps active systemd always in sync with repository
# Role-aware: only links services appropriate for this node's role

# set -e  # Disabled to allow script to continue even if some operations fail

REPO_APPS_DIR="/opt/aitbc/apps"
REPO_SCRIPTS_DIR="/opt/aitbc/scripts"
ACTIVE_SYSTEMD_DIR="/etc/systemd/system"
REPO_CONFIG_DIR="/opt/aitbc/scripts/config"
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
        blockchain_mode="$BLOCKCHAIN_MODE"
        market_role="$MARKET_ROLE"
        hardware_profile="$HARDWARE_PROFILE"
    fi
    if [ -f "/etc/aitbc/node.env" ]; then
        source /etc/aitbc/node.env 2>/dev/null
        blockchain_mode="${blockchain_mode:-$BLOCKCHAIN_MODE}"
        market_role="${market_role:-$MARKET_ROLE}"
        hardware_profile="${hardware_profile:-$HARDWARE_PROFILE}"
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
    )

    # Hub-specific services (blockchain producer)
    local hub_services=(
        aitbc-blockchain-p2p
        aitbc-coordinator-api
        aitbc-api-gateway
        aitbc-governance
        aitbc-exchange
        aitbc-marketplace
        aitbc-bridge-monitor
        aitbc-blockchain-event-bridge
        aitbc-agent-management
        aitbc-agent-coordinator
        aitbc-blockchain-explorer
    )

    # Follower-specific services (blockchain sync, in addition to base)
    local follower_services=(
        aitbc-blockchain-sync
        aitbc-blockchain-explorer
    )

    # Shop-specific services (GPU provider, regardless of blockchain mode)
    local shop_services=(
        aitbc-gpu
        aitbc-miner
        aitbc-coordinator-api
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
    if [ "$ROLE_FILTER" = "false" ]; then
        return 0  # Allow all
    fi
    echo "$ALLOWED_SERVICES" | grep -qxF "$basename"
}

echo "🔍 Creating symbolic links for AITBC systemd files..."

# Remove existing aitbc-* files and stale drop-in directories
echo "🧹 Removing existing systemd files..."
find "$ACTIVE_SYSTEMD_DIR" -maxdepth 1 -name "aitbc-*" \( -type f -o -type l \) -delete 2>/dev/null || true
find "$ACTIVE_SYSTEMD_DIR" -maxdepth 1 -name "aitbc-*.d" -exec rm -rf {} + 2>/dev/null || true

# Create symbolic links
echo "🔗 Creating symbolic links..."
linked_files=0
error_count=0

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

# Find all systemd service files in scripts directory
echo "📁 Scanning scripts directory..."
for file in "$REPO_SCRIPTS_DIR"/*/aitbc-*.service "$REPO_SCRIPTS_DIR"/*/aitbc-*.timer "$REPO_SCRIPTS_DIR"/utils/aitbc-*.service "$REPO_SCRIPTS_DIR"/monitoring/aitbc-*.service; do
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

# Exit code reflects both link and tmpfiles deployment errors
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
