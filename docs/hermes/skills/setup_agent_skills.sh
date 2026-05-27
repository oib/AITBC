#!/bin/bash
# Setup script to symlink AITBC skills to agent skills directory with proper frontmatter

set -e

SOURCE_DIR="/opt/aitbc/docs/hermes/skills"
TARGET_DIR="/root/.hermes/skills/aitbc"

# Create target directory
echo "Creating agent skills directory: $TARGET_DIR"
mkdir -p "$TARGET_DIR"

# Function to add frontmatter to a skill file
add_frontmatter() {
    local file=$1
    local name=$2
    local description=$3
    local tags=$4
    
    # Check if file already has frontmatter
    if head -1 "$file" | grep -q "^---"; then
        echo "Skipping $file - already has frontmatter"
        return
    fi
    
    # Create temp file with frontmatter
    local temp_file=$(mktemp)
    cat > "$temp_file" << EOF
---
name: $name
description: "$description"
version: 1.0.0
author: AITBC
license: MIT
platforms: [linux]
metadata:
  hermes:
    tags: [$tags]
    category: aitbc
---

EOF
    
    # Append original content
    cat "$file" >> "$temp_file"
    
    # Replace original file
    mv "$temp_file" "$file"
    echo "Added frontmatter to $file"
}

# Define skills with their metadata
declare -A SKILLS=(
    ["aitbc-basic-operations.md"]="aitbc-basic-operations|Basic AITBC CLI operations, wallet management, and blockchain status checks|aitbc,cli,wallet,blockchain,operations"
    ["aitbc-marketplace.md"]="aitbc-marketplace|Marketplace operations, GPU provider registration, and trading|aitbc,marketplace,gpu,trading"
    ["aitbc-node-coordination.md"]="aitbc-node-coordination|Multi-node coordination, git synchronization, and blockchain sync|aitbc,coordination,multi-node,sync"
    ["aitbc-wallet-management.md"]="aitbc-wallet-management|Wallet creation, import/export, balance checks, and deletion|aitbc,wallet,management,keys"
    ["aitbc-ai-operations.md"]="aitbc-ai-operations|AI job submission, monitoring, resource allocation, and GPU testing|aitbc,ai,jobs,gpu,monitoring"
    ["aitbc-blockchain-troubleshooting.md"]="aitbc-blockchain-troubleshooting|Blockchain troubleshooting, sync issues, and P2P problems|aitbc,blockchain,troubleshooting,p2p,sync"
    ["aitbc-multi-node-operations.md"]="aitbc-multi-node-operations|Multi-node operations, git sync, service restart, and blockchain sync|aitbc,multi-node,operations,sync"
    ["aitbc-cli.md"]="aitbc-cli|CLI tool reference for training agents and workflow operations|aitbc,cli,reference,workflow"
    ["aitbc.md"]="aitbc|Comprehensive AITBC reference documentation|aitbc,reference,comprehensive"
)

# Process each skill file
for skill_file in "${!SKILLS[@]}"; do
    source_file="$SOURCE_DIR/$skill_file"
    
    if [ ! -f "$source_file" ]; then
        echo "Warning: $source_file not found, skipping"
        continue
    fi
    
    # Parse metadata
    IFS='|' read -r name description tags <<< "${SKILLS[$skill_file]}"
    
    # Add frontmatter to source file
    add_frontmatter "$source_file" "$name" "$description" "$tags"
    
    # Create symlink
    target_file="$TARGET_DIR/$skill_file"
    if [ -L "$target_file" ]; then
        echo "Removing existing symlink: $target_file"
        rm "$target_file"
    fi
    
    ln -s "$source_file" "$target_file"
    echo "Symlinked: $source_file -> $target_file"
done

echo ""
echo "Setup complete!"
echo "Skills installed to: $TARGET_DIR"
echo ""
echo "To reload agent skills, run:"
echo "  hermes reload-skills"
echo ""
echo "To verify installation, run:"
echo "  hermes skills list | grep aitbc"
