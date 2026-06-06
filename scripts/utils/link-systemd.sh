#!/bin/bash

# AITBC Systemd Link Script
# Creates symbolic links from active systemd to repository systemd files
# Keeps active systemd always in sync with repository

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

echo "🔍 Creating symbolic links for AITBC systemd files..."

# Remove existing aitbc-* files and stale drop-in directories
echo "🧹 Removing existing systemd files..."
find "$ACTIVE_SYSTEMD_DIR" -name "aitbc-*" -type f -delete 2>/dev/null || true
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
            if cp "$file" "$target" 2>/dev/null; then
                echo "    ✅ Successfully deployed: $filename"
            else
                echo "    ❌ Failed to deploy: $filename"
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

# Ensure script exits successfully
if [[ $linked_files -gt 0 ]]; then
    echo "✅ Script completed successfully with $linked_files files linked"
    exit 0
else
    echo "⚠️  No files were linked, but script completed"
    exit 0
fi
