#!/bin/bash
# Shared CI clone helper for Gitea runner workflows
# Usage: source scripts/ci/clone-repo.sh <workspace-name>
#   Sets REPO_DIR to the cloned repo path

set -euo pipefail

WORKSPACE_NAME="${1:-default}"
WORKSPACE_BASE="/var/lib/aitbc-workspaces"
WORKSPACE_DIR="$WORKSPACE_BASE/$WORKSPACE_NAME"
REPO_URL="http://gitea.bubuit.net:3000/oib/aitbc.git"

echo "=== Setting up workspace: $WORKSPACE_NAME ==="

rm -rf "$WORKSPACE_DIR"
mkdir -p "$WORKSPACE_DIR"
cd "$WORKSPACE_DIR"

git clone --depth 1 "$REPO_URL" repo
cd repo

export REPO_DIR="$WORKSPACE_DIR/repo"
echo "✅ Repository cloned to $REPO_DIR"
