#!/bin/bash

# AITBC Systemd Link Script
# Creates symbolic links from active systemd to repository systemd files
# Keeps active systemd always in sync with repository

set -e

REPO_SYSTEMD_DIR="/opt/aitbc/systemd"
ACTIVE_SYSTEMD_DIR="/etc/systemd/system"

echo "=== AITBC SYSTEMD LINKING ==="
echo "Repository: $REPO_SYSTEMD_DIR"
echo "Active: $ACTIVE_SYSTEMD_DIR"
echo

# Check if running as root
if [[ $EUID -ne 0 ]]; then
   echo "❌ This script must be run as root (use sudo)"
   echo "   sudo $0"
   exit 1
fi

# Check if repository systemd directory exists
if [[ ! -d "$REPO_SYSTEMD_DIR" ]]; then
    echo "❌ Repository systemd directory not found: $REPO_SYSTEMD_DIR"
    exit 1
fi

echo "🔍 Creating symbolic links for AITBC systemd files..."

# Create backup of current active systemd files
BACKUP_DIR="/opt/aitbc/systemd-backup-$(date +%Y%m%d-%H%M%S)"
echo "📦 Creating backup: $BACKUP_DIR"
mkdir -p "$BACKUP_DIR"
find "$ACTIVE_SYSTEMD_DIR" -name "aitbc-*" -type f -exec cp {} "$BACKUP_DIR/" \; 2>/dev/null || true

# Remove existing aitbc-* files (but not directories)
echo "🧹 Removing existing systemd files..."
find "$ACTIVE_SYSTEMD_DIR" -name "aitbc-*" -type f -delete 2>/dev/null || true

# Create symbolic links
echo "🔗 Creating symbolic links..."
linked_files=0
for file in "$REPO_SYSTEMD_DIR"/aitbc-*; do
    if [[ -f "$file" ]]; then
        filename=$(basename "$file")
        target="$ACTIVE_SYSTEMD_DIR/$filename"
        source="$REPO_SYSTEMD_DIR/$filename"
        
        echo "  🔗 Linking: $filename -> $source"
        
        # Create symbolic link
        ln -sf "$source" "$target"
        
        # Handle .d directories
        if [[ -d "${file}.d" ]]; then
            target_dir="${target}.d"
            source_dir="${file}.d"
            
            echo "    📁 Linking directory: ${filename}.d -> ${source_dir}"
            
            # Remove existing directory
            rm -rf "$target_dir" 2>/dev/null || true
            
            # Create symbolic link for directory
            ln -sf "$source_dir" "$target_dir"
        fi
        
        ((linked_files++))
    fi
done

echo
echo "🔄 Reloading systemd daemon..."
systemctl daemon-reload

echo
echo "✅ Systemd linking completed!"
echo
echo "📊 Link Summary:"
echo "  Linked files: $linked_files"
echo "  Repository: $REPO_SYSTEMD_DIR"
echo "  Active: $ACTIVE_SYSTEMD_DIR"
echo "  Backup location: $BACKUP_DIR"
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
echo
echo "⚠️  If you need to restore backup:"
echo "  sudo cp $BACKUP_DIR/* /etc/systemd/system/"
echo "  sudo systemctl daemon-reload"
