#!/bin/bash
# Multi-Node Git Sync Script for AITBC
# Syncs git changes from genesis node to follower and gitea-runner nodes

set -e

REPO_DIR="/opt/aitbc"
GITEA_REMOTE="origin"
FOLLOWER_NODE="aitbc1"
RUNNER_NODE="gitea-runner"

echo "=== AITBC Multi-Node Git Sync ==="
echo "Starting sync from genesis node..."
echo ""

# Check genesis node status
echo "=== Genesis Node Status ==="
cd $REPO_DIR
git status --short
GENESIS_HASH=$(git rev-parse HEAD)
echo "Genesis HEAD: $GENESIS_HASH"
echo ""

# Check if there are uncommitted changes
if ! git diff-index --quiet HEAD --; then
    echo "⚠️  Uncommitted changes detected on genesis node"
    echo "Please commit changes before syncing:"
    echo "  git add ."
    echo "  git commit -m 'description'"
    exit 1
fi

# Check if genesis is ahead of origin
if [ "$(git rev-parse HEAD)" != "$(git rev-parse $GITEA_REMOTE/main)" ]; then
    echo "⚠️  Genesis node is ahead of $GITEA_REMOTE"
    echo "Pushing to $GITEA_REMOTE first..."
    git push $GITEA_REMOTE main
    echo "✅ Pushed to $GITEA_REMOTE"
else
    echo "✅ Genesis node is up to date with $GITEA_REMOTE"
fi
echo ""

# Sync follower node
echo "=== Syncing Follower Node ($FOLLOWER_NODE) ==="
FOLLOWER_HASH=$(ssh $FOLLOWER_NODE "cd $REPO_DIR && git rev-parse HEAD" 2>/dev/null || echo "none")
echo "Follower HEAD: $FOLLOWER_HASH"

if [ "$GENESIS_HASH" != "$FOLLOWER_HASH" ]; then
    echo "Syncing follower node..."
    ssh $FOLLOWER_NODE "cd $REPO_DIR && git fetch $GITEA_REMOTE && git reset --hard $GITEA_REMOTE/main"
    NEW_FOLLOWER_HASH=$(ssh $FOLLOWER_NODE "cd $REPO_DIR && git rev-parse HEAD")
    echo "✅ Follower node synced: $NEW_FOLLOWER_HASH"
else
    echo "✅ Follower node already in sync"
fi
echo ""

# Sync gitea-runner node
echo "=== Syncing Gitea-Runner Node ($RUNNER_NODE) ==="
RUNNER_HASH=$(ssh $RUNNER_NODE "cd $REPO_DIR && git rev-parse HEAD" 2>/dev/null || echo "none")
echo "Gitea-Runner HEAD: $RUNNER_HASH"

if [ "$GENESIS_HASH" != "$RUNNER_HASH" ]; then
    echo "Syncing gitea-runner node..."
    ssh $RUNNER_NODE "cd $REPO_DIR && git fetch $GITEA_REMOTE && git reset --hard $GITEA_REMOTE/main"
    NEW_RUNNER_HASH=$(ssh $RUNNER_NODE "cd $REPO_DIR && git rev-parse HEAD")
    echo "✅ Gitea-Runner node synced: $NEW_RUNNER_HASH"
else
    echo "✅ Gitea-Runner node already in sync"
fi
echo ""

# Final verification
echo "=== Final Verification ==="
FINAL_GENESIS=$(git rev-parse --short HEAD)
FINAL_FOLLOWER=$(ssh $FOLLOWER_NODE "cd $REPO_DIR && git rev-parse --short HEAD")
FINAL_RUNNER=$(ssh $RUNNER_NODE "cd $REPO_DIR && git rev-parse --short HEAD")

echo "Genesis: $FINAL_GENESIS"
echo "Follower: $FINAL_FOLLOWER"
echo "Gitea-Runner: $FINAL_RUNNER"

if [ "$FINAL_GENESIS" = "$FINAL_FOLLOWER" ] && [ "$FINAL_GENESIS" = "$FINAL_RUNNER" ]; then
    echo "✅ All three nodes are in sync"
    exit 0
else
    echo "❌ Nodes are out of sync"
    exit 1
fi
