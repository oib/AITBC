#!/bin/bash

# AITBC Systemd Sync Script
# Syncs repository systemd files to active systemd configuration
# Eliminates gap between repo and running services

set -e

REPO_SYSTEMD_DIR="/opt/aitbc/systemd"
ACTIVE_SYSTEMD_DIR="/etc/systemd/system"

echo "=== AITBC SYSTEMD SYNC ==="
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

echo "🔍 Scanning for AITBC systemd files..."

# Create backup of current active systemd files
BACKUP_DIR="/opt/aitbc/systemd-backup-$(date +%Y%m%d-%H%M%S)"
echo "📦 Creating backup: $BACKUP_DIR"
mkdir -p "$BACKUP_DIR"
find "$ACTIVE_SYSTEMD_DIR" -name "aitbc-*" -type f -exec cp {} "$BACKUP_DIR/" \;

# Sync repository files to active systemd
echo "🔄 Syncing systemd files..."

# Copy all aitbc-* files from repo to active systemd
for file in "$REPO_SYSTEMD_DIR"/aitbc-*; do
    if [[ -f "$file" ]]; then
        filename=$(basename "$file")
        target="$ACTIVE_SYSTEMD_DIR/$filename"
        
        echo "  📄 Syncing: $filename"
        
        # Copy file with proper permissions
        cp "$file" "$target"
        chmod 644 "$target"
        
        # Handle .d directories
        if [[ -d "${file}.d" ]]; then
            target_dir="${target}.d"
            echo "    📁 Syncing directory: ${filename}.d"
            mkdir -p "$target_dir"
            cp -r "${file}.d"/* "$target_dir/"
            chmod 644 "$target_dir"/*
        fi
    fi
done

echo
echo "🔄 Reloading systemd daemon..."
systemctl daemon-reload

echo
echo "✅ Systemd sync completed!"
echo
echo "📊 Sync Summary:"
echo "  Repository files: $(find "$REPO_SYSTEMD_DIR" -name 'aitbc-*' -type f | wc -l)"
echo "  Active files: $(find "$ACTIVE_SYSTEMD_DIR" -name 'aitbc-*' -type f | wc -l)"
echo "  Backup location: $BACKUP_DIR"
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
echo "⚠️  If you need to restore backup:"
echo "  sudo cp $BACKUP_DIR/* /etc/systemd/system/"
echo "  sudo systemctl daemon-reload"
