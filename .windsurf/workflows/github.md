---
description: Git operations workflow with Gitea for daily usage and GitHub for milestone pushes
title: AITBC Git Operations Workflow (Gitea + GitHub)
version: 4.0
auto_execution_mode: 3
---

# AITBC Git Operations Workflow (Gitea + GitHub)

This workflow handles git operations for the AITBC project with a dual-remote strategy:
- **Gitea**: Used for daily git operations (commits, pushes, pulls, CI/CD)
- **GitHub**: Used only for milestone pushes (public releases, major milestones)

This ensures genesis, follower, and gitea-runner nodes maintain consistent git status after git operations.

## Git Remote Strategy

### Primary Remote: Gitea
- Used for all daily development work
- CI/CD pipelines run from Gitea
- All branches and commits live here
- Remote name: `origin`

### Secondary Remote: GitHub
- Used only for milestone pushes (releases, major milestones)
- Public-facing repository
- Synced from Gitea at specific milestones
- Remote name: `github`

## Prerequisites

### Required Setup
- Gitea repository configured as primary remote (`origin`)
- GitHub repository configured as secondary remote (`github`)
- GitHub access token available (for milestone pushes only)
- Git user configured
- Working directory: `/opt/aitbc`

### Environment Setup
```bash
cd /opt/aitbc
git status
git remote -v
# Expected output:
# origin    git@gitea.bubuit.net:oib/aitbc.git (fetch)
# origin    git@gitea.bubuit.net:oib/aitbc.git (push)
# github   https://github.com/oib/AITBC.git (fetch)
# github   https://github.com/oib/AITBC.git (push)
```

## Daily Git Operations Workflow (Gitea)

### 1. Check Current Status
```bash
# Check git status
git status

# Check remote configuration
git remote -v

# Check current branch
git branch

# Check for uncommitted changes
git diff --stat
```

### 2. Stage Changes
```bash
# Stage all changes
git add .

# Stage specific files
git add docs/ cli/ scripts/

# Stage specific directory
git add .windsurf/

# Check staged changes
git status --short
```

### 3. Commit Changes
```bash
# Commit with descriptive message
git commit -m "feat: update CLI documentation and workflows

- Updated CLI enhancement workflow to reflect current structure
- Added comprehensive GitHub operations workflow
- Updated documentation paths and service endpoints
- Enhanced CLI command documentation"

# Commit with specific changes
git commit -m "fix: resolve service endpoint issues

- Updated coordinator API port from 18000 to 8000
- Fixed blockchain RPC endpoint configuration
- Updated CLI commands to use correct service ports"

# Quick commit for minor changes
git commit -m "docs: update README with latest changes"
```

### 4. Push to Gitea (Daily Operations)
```bash
# Push to main branch on Gitea
git push origin main

# Push to specific branch on Gitea
git push origin develop

# Push with upstream tracking (first time)
git push -u origin main

# Force push (use with caution)
git push --force-with-lease origin main

# Push all branches to Gitea
git push --all origin
```

### 5. Multi-Node Git Status Check
```bash
# Check git status on all three nodes
echo "=== Genesis Node Git Status ==="
cd /opt/aitbc
git status
git log --oneline -3

echo ""
echo "=== Follower Node Git Status ==="
ssh aitbc1 'cd /opt/aitbc && git status'
ssh aitbc1 'cd /opt/aitbc && git log --oneline -3'

echo ""
echo "=== Gitea-Runner Node Git Status ==="
ssh gitea-runner 'cd /opt/aitbc && git status'
ssh gitea-runner 'cd /opt/aitbc && git log --oneline -3'

echo ""
echo "=== Comparison Check ==="
# Get latest commit hashes
GENESIS_HASH=$(git rev-parse HEAD)
FOLLOWER_HASH=$(ssh aitbc1 'cd /opt/aitbc && git rev-parse HEAD')
RUNNER_HASH=$(ssh gitea-runner 'cd /opt/aitbc && git rev-parse HEAD')

echo "Genesis latest: $GENESIS_HASH"
echo "Follower latest: $FOLLOWER_HASH"
echo "Gitea-Runner latest: $RUNNER_HASH"

if [ "$GENESIS_HASH" = "$FOLLOWER_HASH" ] && [ "$GENESIS_HASH" = "$RUNNER_HASH" ]; then
    echo "✅ All three nodes are in sync"
else
    echo "⚠️ Nodes are out of sync"
    echo "Genesis ahead by: $(git rev-list --count $FOLLOWER_HASH..HEAD 2>/dev/null || echo "N/A") commits"
    echo "Follower ahead by: $(ssh aitbc1 'cd /opt/aitbc && git rev-list --count $GENESIS_HASH..HEAD 2>/dev/null || echo "N/A"') commits"
    echo "Runner ahead by: $(ssh gitea-runner 'cd /opt/aitbc && git rev-list --count $GENESIS_HASH..HEAD 2>/dev/null || echo "N/A"') commits"
fi
```

### 6. Sync Follower and Gitea-Runner Nodes (if needed)
```bash
# Sync follower node with genesis
if [ "$GENESIS_HASH" != "$FOLLOWER_HASH" ]; then
    echo "=== Syncing Follower Node ==="
    
    # Option 1: Push from genesis to follower
    ssh aitbc1 'cd /opt/aitbc && git fetch origin'
    ssh aitbc1 'cd /opt/aitbc && git pull origin main'
    
    # Option 2: Copy changes directly (if remote sync fails)
    rsync -av --exclude='.git' /opt/aitbc/ aitbc1:/opt/aitbc/
    ssh aitbc1 'cd /opt/aitbc && git add . && git commit -m "sync from genesis node" || true'
    
    echo "✅ Follower node synced"
fi

# Sync gitea-runner node with genesis
if [ "$GENESIS_HASH" != "$RUNNER_HASH" ]; then
    echo "=== Syncing Gitea-Runner Node ==="
    
    # Option 1: Push from genesis to gitea-runner
    ssh gitea-runner 'cd /opt/aitbc && git fetch origin'
    ssh gitea-runner 'cd /opt/aitbc && git pull origin main'
    
    # Option 2: Copy changes directly (if remote sync fails)
    rsync -av --exclude='.git' /opt/aitbc/ gitea-runner:/opt/aitbc/
    ssh gitea-runner 'cd /opt/aitbc && git add . && git commit -m "sync from genesis node" || true'
    
    echo "✅ Gitea-Runner node synced"
fi
```

### 7. Verify Push
```bash
# Check if push was successful
git status

# Check remote status
git log --oneline -5 origin/main

# Verify on Gitea (web interface)
# Open: https://gitea.bubuit.net/oib/aitbc

# Verify all three nodes are updated
echo "=== Final Status Check ==="
echo "Genesis: $(git rev-parse --short HEAD)"
echo "Follower: $(ssh aitbc1 'cd /opt/aitbc && git rev-parse --short HEAD')"
echo "Gitea-Runner: $(ssh gitea-runner 'cd /opt/aitbc && git rev-parse --short HEAD')"
```

### 8. Push to GitHub (Milestone Only)
```bash
# Only push to GitHub for milestones (releases, major features)
# First verify local changes are pushed to Gitea
LOCAL_HASH=$(git rev-parse HEAD)
ORIGIN_HASH=$(git rev-parse origin/main)

if [ "$LOCAL_HASH" != "$ORIGIN_HASH" ]; then
    echo "❌ Local changes not pushed to Gitea"
    echo "Local: $LOCAL_HASH"
    echo "Origin: $ORIGIN_HASH"
    echo "Push to Gitea first: git push origin main"
    exit 1
fi

echo "✅ Local changes already pushed to Gitea"

# Verify all three nodes are in sync before GitHub push
GENESIS_HASH=$(git rev-parse HEAD)
FOLLOWER_HASH=$(ssh aitbc1 'cd /opt/aitbc && git rev-parse HEAD')
RUNNER_HASH=$(ssh gitea-runner 'cd /opt/aitbc && git rev-parse HEAD')

if [ "$GENESIS_HASH" = "$FOLLOWER_HASH" ] && [ "$GENESIS_HASH" = "$RUNNER_HASH" ]; then
    echo "✅ All nodes in sync, proceeding with GitHub push"
    
    # Push to GitHub (milestone only)
    git push github main
    
    echo "✅ GitHub push complete"
    echo "Verify on GitHub: https://github.com/oib/AITBC"
else
    echo "❌ Nodes out of sync, aborting GitHub push"
    echo "Sync all nodes first before pushing to GitHub"
    exit 1
fi
```

## Quick Git Commands

### Multi-Node Standard Workflow (Gitea)
```bash
# Complete multi-node workflow - check, stage, commit, push to Gitea, sync all nodes
cd /opt/aitbc

# 1. Check all three nodes status
echo "=== Checking All Nodes ==="
git status
ssh aitbc1 'cd /opt/aitbc && git status'
ssh gitea-runner 'cd /opt/aitbc && git status'

# 2. Stage and commit
git add .
git commit -m "feat: add new feature implementation"

# 3. Push to Gitea (daily operations)
git push origin main

# 4. Sync follower node
ssh aitbc1 'cd /opt/aitbc && git pull origin main'

# 5. Sync gitea-runner node
ssh gitea-runner 'cd /opt/aitbc && git pull origin main'

# 6. Verify all three nodes
echo "=== Verification ==="
git rev-parse --short HEAD
ssh aitbc1 'cd /opt/aitbc && git rev-parse --short HEAD'
ssh gitea-runner 'cd /opt/aitbc && git rev-parse --short HEAD'
```

### Quick Multi-Node Push (Gitea)
```bash
# Quick push for minor changes with node sync
cd /opt/aitbc
git add . && git commit -m "docs: update documentation" && git push origin main
ssh aitbc1 'cd /opt/aitbc && git pull origin main'
ssh gitea-runner 'cd /opt/aitbc && git pull origin main'
```

### Multi-Node Sync Check
```bash
# Quick sync status check
cd /opt/aitbc
GENESIS_HASH=$(git rev-parse HEAD)
FOLLOWER_HASH=$(ssh aitbc1 'cd /opt/aitbc && git rev-parse HEAD')
RUNNER_HASH=$(ssh gitea-runner 'cd /opt/aitbc && git rev-parse HEAD')
if [ "$GENESIS_HASH" = "$FOLLOWER_HASH" ] && [ "$GENESIS_HASH" = "$RUNNER_HASH" ]; then
    echo "✅ All three nodes in sync"
else
    echo "⚠️ Nodes out of sync - sync needed"
fi
```

### Standard Workflow (Gitea)
```bash
# Complete workflow - stage, commit, push to Gitea
cd /opt/aitbc
git add .
git commit -m "feat: add new feature implementation"
git push origin main
```

### Quick Push (Gitea)
```bash
# Quick push for minor changes to Gitea
git add . && git commit -m "docs: update documentation" && git push origin main
```

### Specific File Push
```bash
# Push specific changes
git add docs/README.md
git commit -m "docs: update main README"
git push origin main
```

## GitHub Milestone Pushes

### When to Push to GitHub
- Major releases (v1.0.0, v2.0.0, etc.)
- Public-facing milestones
- Significant feature releases
- Quarterly releases

### Milestone Push Workflow
```bash
# 1. Ensure Gitea is up to date
cd /opt/aitbc
git status
git pull origin main

# 2. Verify commit hash matches between all three nodes
GENESIS_HASH=$(git rev-parse HEAD)
FOLLOWER_HASH=$(ssh aitbc1 'cd /opt/aitbc && git rev-parse HEAD')
RUNNER_HASH=$(ssh gitea-runner 'cd /opt/aitbc && git rev-parse HEAD')
if [ "$GENESIS_HASH" = "$FOLLOWER_HASH" ] && [ "$GENESIS_HASH" = "$RUNNER_HASH" ]; then
    echo "✅ All nodes in sync, proceeding with GitHub push"
else
    echo "❌ Nodes out of sync, aborting GitHub push"
    exit 1
fi

# 3. Push to GitHub (milestone only)
git push github main

# 4. Verify on GitHub
# Open: https://github.com/oib/AITBC
```

### GitHub Remote Setup
```bash
# Add GitHub remote (if not already configured)
git remote add github https://github.com/oib/AITBC.git

# Set up GitHub with token from secure file
GITHUB_TOKEN=$(cat /root/github_token)
git remote set-url github https://${GITHUB_TOKEN}@github.com/oib/AITBC.git

# Verify GitHub remote
git remote -v | grep github
```

### Gitea Remote Setup
```bash
# Gitea is configured as primary remote (origin)
# Uses HTTP authentication with token stored in ~/.git-credentials

# Add Gitea remote (if not already configured)
git remote add origin http://gitea.bubuit.net:3000/oib/aitbc.git

# Configure token authentication via ~/.git-credentials
# Format: http://<username>:<token>@gitea.bubuit.net:3000
# Note: Replace <GITEA_TOKEN> with actual Gitea access token
# Note: Replace <GITHUB_TOKEN> with actual GitHub personal access token
cat > ~/.git-credentials << 'EOF'
http://aitbc:<GITEA_TOKEN>@gitea.bubuit.net:3000
https://oib:<GITHUB_TOKEN>@github.com
EOF

# Enable credential helper
git config --global credential.helper store

# Verify Gitea remote
git remote -v | grep origin
```

### Git Setup Configuration

**Current Git Remote Configuration:**
```
origin    http://gitea.bubuit.net:3000/oib/aitbc.git (fetch)
origin    http://gitea.bubuit.net:3000/oib/aitbc.git (push)
github   https://<GITHUB_TOKEN>@github.com/oib/AITBC.git (fetch)
github   https://<GITHUB_TOKEN>@github.com/oib/AITBC.git (push)
```

**Authentication Method:**
- **Gitea**: HTTP authentication with token stored in `~/.git-credentials`
- **GitHub**: HTTPS authentication with token embedded in remote URL

**Credential Storage:**
- `~/.git-credentials` file contains authentication tokens
- Git credential helper configured to use this file
- Tokens are stored in URL format: `http://<username>:<token>@<host>:<port>`

**Security Notes:**
- Gitea token: Stored in `~/.git-credentials` for HTTP authentication
- GitHub token: Stored in `/root/github_token` file for milestone pushes
- Ensure credential files have appropriate permissions (chmod 600)
- Never commit actual tokens to version control

## Advanced GitHub Operations

### Branch Management
```bash
# Create new branch
git checkout -b feature/new-feature

# Switch branches
git checkout develop

# Merge branches
git checkout main
git merge feature/new-feature

# Delete branch
git branch -d feature/new-feature
```

### Remote Management
```bash
# Add GitHub remote (secondary, for milestones only)
git remote add github https://github.com/oib/AITBC.git

# Set up GitHub with token from secure file
GITHUB_TOKEN=$(cat /root/github_token)
git remote set-url github https://${GITHUB_TOKEN}@github.com/oib/AITBC.git

# Push to GitHub specifically (milestone only)
git push github main

# Push to both remotes (not recommended - use milestone workflow instead)
git push origin main && git push github main

# View all remotes
git remote -v
```

### Sync Operations
```bash
# Pull latest changes from Gitea
git pull origin main

# Sync with Gitea
git fetch origin
git rebase origin/main

# Push to Gitea after sync
git push origin main
```

## Troubleshooting

### Multi-Node Sync Issues
```bash
# Check if nodes are in sync
cd /opt/aitbc
GENESIS_HASH=$(git rev-parse HEAD)
FOLLOWER_HASH=$(ssh aitbc1 'cd /opt/aitbc && git rev-parse HEAD')
RUNNER_HASH=$(ssh gitea-runner 'cd /opt/aitbc && git rev-parse HEAD')

if [ "$GENESIS_HASH" != "$FOLLOWER_HASH" ] || [ "$GENESIS_HASH" != "$RUNNER_HASH" ]; then
    echo "⚠️ Nodes out of sync - fixing..."
    
    # Check connectivity to follower
    ssh aitbc1 'echo "Follower node reachable"' || {
        echo "❌ Cannot reach follower node"
        exit 1
    }
    
    # Check connectivity to gitea-runner
    ssh gitea-runner 'echo "Gitea-Runner node reachable"' || {
        echo "❌ Cannot reach gitea-runner node"
        exit 1
    }
    
    # Sync follower node
    if [ "$GENESIS_HASH" != "$FOLLOWER_HASH" ]; then
        ssh aitbc1 'cd /opt/aitbc && git fetch origin'
        ssh aitbc1 'cd /opt/aitbc && git pull origin main'
    fi
    
    # Sync gitea-runner node
    if [ "$GENESIS_HASH" != "$RUNNER_HASH" ]; then
        ssh gitea-runner 'cd /opt/aitbc && git fetch origin'
        ssh gitea-runner 'cd /opt/aitbc && git pull origin main'
    fi
    
    # Verify sync
    NEW_FOLLOWER_HASH=$(ssh aitbc1 'cd /opt/aitbc && git rev-parse HEAD')
    NEW_RUNNER_HASH=$(ssh gitea-runner 'cd /opt/aitbc && git rev-parse HEAD')
    if [ "$GENESIS_HASH" = "$NEW_FOLLOWER_HASH" ] && [ "$GENESIS_HASH" = "$NEW_RUNNER_HASH" ]; then
        echo "✅ All nodes synced successfully"
    else
        echo "❌ Sync failed - manual intervention required"
    fi
fi
```

### Push Failures
```bash
# Check if remote exists
git remote get-url origin

# Check authentication
git config --get remote.origin.url

# Fix authentication issues for Gitea
# (Gitea uses SSH key authentication by default)
git remote set-url origin git@gitea.bubuit.net:oib/aitbc.git

# Fix authentication issues for GitHub (milestone only)
GITHUB_TOKEN=$(cat /root/github_token)
git remote set-url github https://${GITHUB_TOKEN}@github.com/oib/AITBC.git

# Force push if needed (use with caution)
git push --force-with-lease origin main
```

### Merge Conflicts
```bash
# Check for conflicts
git status

# Resolve conflicts manually
# Edit conflicted files, then:
git add .
git commit -m "resolve merge conflicts"

# Abort merge if needed
git merge --abort
```

### Remote Issues
```bash
# Check remote connectivity
git ls-remote origin

# Re-add Gitea remote if needed
git remote remove origin
git remote add origin git@gitea.bubuit.net:oib/aitbc.git

# Re-add GitHub remote if needed (milestone only)
git remote remove github
git remote add github https://github.com/oib/AITBC.git

# Test push to Gitea
git push origin main --dry-run
```

## GitHub Integration (Milestone Only)

### GitHub CLI (if available)
```bash
# Create pull request (GitHub only - not typically used for AITBC)
gh pr create --title "Update CLI documentation" --body "Comprehensive CLI documentation updates"

# View repository
gh repo view

# List issues
gh issue list

# Create release (milestone only)
gh release create v1.0.0 --title "Version 1.0.0" --notes "Initial release"
```

### Web Interface
```bash
# Open Gitea repository in browser (daily use)
xdg-open https://gitea.bubuit.net/oib/aitbc

# Open GitHub repository in browser (milestone only)
xdg-open https://github.com/oib/AITBC

# Open specific commit on Gitea
xdg-open https://gitea.bubuit.net/oib/aitbc/commit/$(git rev-parse HEAD)

# Open specific commit on GitHub
xdg-open https://github.com/oib/AITBC/commit/$(git rev-parse HEAD)
```

## Best Practices

### Commit Messages
- Use conventional commit format: `type: description`
- Keep messages under 72 characters
- Use imperative mood: "add feature" not "added feature"
- Include body for complex changes

### Branch Strategy
- Use `main` for production-ready code
- Use `develop` for integration
- Use feature branches for new work
- Keep branches short-lived

### Push Frequency
- Push small, frequent commits to Gitea (daily operations)
- Ensure tests pass before pushing to Gitea
- Include documentation with code changes
- Push to GitHub only for milestones (releases, major features)
- Tag releases appropriately on GitHub

## Recent Updates (v4.0)

### Three-Node Verification
- **Gitea-Runner Added**: Extended multi-node verification to include gitea-runner node
- **All-Node Sync Check**: Updated all verification steps to check genesis, aitbc1, and gitea-runner nodes
- **GitHub Push Verification**: Added three-node sync verification before GitHub milestone pushes
- **Sync Operations**: Updated sync procedures to include gitea-runner node

### Updated Workflow Sections
- **Multi-Node Git Status Check**: Now checks all three nodes (genesis, aitbc1, gitea-runner)
- **Sync Follower and Gitea-Runner Nodes**: Added gitea-runner sync to section 6
- **Verify Push**: Updated to verify all three nodes are updated
- **Push to GitHub (Milestone Only)**: New section 8 for GitHub push with three-node verification

### Updated Quick Commands
- **Multi-Node Standard Workflow**: Updated to include gitea-runner status check and sync
- **Quick Multi-Node Push**: Added gitea-runner sync to quick push command
- **Multi-Node Sync Check**: Updated to check all three nodes for sync status

### Updated Milestone Workflow
- **Three-Node Verification**: GitHub milestone push now verifies all three nodes are in sync
- **Sync Check**: Added gitea-runner hash comparison before GitHub push
- **Error Handling**: Aborts GitHub push if any node is out of sync

### Updated Troubleshooting
- **Multi-Node Sync Issues**: Updated to handle gitea-runner sync issues
- **Connectivity Checks**: Added gitea-runner connectivity verification
- **Sync Validation**: Updated to verify all three nodes after sync operations

## Recent Updates (v3.0)

### Dual-Remote Strategy
- **Gitea as Primary**: Gitea used for all daily git operations (commits, pushes, pulls, CI/CD)
- **GitHub as Secondary**: GitHub used only for milestone pushes (releases, major milestones)
- **Remote Strategy**: Clear separation between Gitea (origin) and GitHub (github) remotes
- **Milestone Workflow**: Dedicated workflow for GitHub milestone pushes with node sync verification

### Updated Workflow Sections
- **Daily Git Operations**: Renamed from "GitHub Operations" to reflect Gitea usage
- **Push to Gitea**: Clarified daily operations push to Gitea (origin)
- **GitHub Milestone Pushes**: New section for milestone-specific GitHub operations
- **Remote Management**: Updated to show both Gitea and GitHub remotes

### Updated Quick Commands
- **Gitea-First Workflow**: All quick commands updated to use Gitea for daily operations
- **Multi-Node Sync**: Maintained across both Gitea and GitHub operations
- **Verification**: Updated to verify on Gitea for daily operations

### Updated Integration
- **Gitea Web Interface**: Added Gitea repository URL for daily use
- **GitHub Integration**: Clarified as milestone-only operations
- **Authentication**: Updated to reflect Gitea SSH key authentication and GitHub token authentication

### Updated Best Practices
- **Push Frequency**: Updated to reflect Gitea for daily use and GitHub for milestones
- **Remote Strategy**: Clear guidance on when to use each remote

## Previous Updates (v2.1)

### Enhanced Multi-Node Workflow
- **Multi-Node Git Status**: Check git status on both genesis and follower nodes
- **Automatic Sync**: Sync follower node with genesis after GitHub push
- **Comparison Check**: Verify both nodes have the same commit hash
- **Sync Verification**: Confirm successful synchronization across nodes

### Multi-Node Operations
- **Status Comparison**: Compare git status between nodes
- **Hash Verification**: Check commit hashes for consistency
- **Automatic Sync**: Pull changes on follower node after genesis push
- **Error Handling**: Detect and fix sync issues automatically

### Enhanced Troubleshooting
- **Multi-Node Sync Issues**: Detect and resolve node synchronization problems
- **Connectivity Checks**: Verify SSH connectivity to follower node
- **Sync Validation**: Confirm successful node synchronization
- **Manual Recovery**: Alternative sync methods if automatic sync fails

### Quick Commands
- **Multi-Node Workflow**: Complete workflow with node synchronization
- **Quick Sync Check**: Fast verification of node status
- **Automatic Sync**: One-command synchronization across nodes

## Previous Updates (v2.0)

### Enhanced Workflow
- **Comprehensive Operations**: Added complete GitHub workflow
- **Push Integration**: Specific git push to GitHub commands
- **Remote Management**: GitHub remote configuration
- **Troubleshooting**: Common issues and solutions

### Current Integration
- **GitHub Token**: Integration with GitHub access token
- **Multi-Remote**: Support for both Gitea and GitHub
- **Branch Management**: Complete branch operations
- **CI/CD Ready**: Integration with automated workflows

### Advanced Features
- **GitHub CLI**: Integration with GitHub CLI tools
- **Web Interface**: Browser integration
- **Best Practices**: Documentation standards
- **Error Handling**: Comprehensive troubleshooting