---
description: Comprehensive GitHub operations including git push to GitHub
title: AITBC GitHub Operations Workflow
version: 2.0
auto_execution_mode: 3
---

# AITBC GitHub Operations Workflow

This workflow handles all GitHub operations including staging, committing, and pushing changes to GitHub repository.

## Prerequisites

### Required Setup
- GitHub repository configured as remote
- GitHub access token available
- Git user configured
- Working directory: `/opt/aitbc`

### Environment Setup
```bash
cd /opt/aitbc
git status
git remote -v
```

## GitHub Operations Workflow

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

### 4. Push to GitHub
```bash
# Push to main branch
git push origin main

# Push to specific branch
git push origin develop

# Push with upstream tracking (first time)
git push -u origin main

# Force push (use with caution)
git push --force-with-lease origin main

# Push all branches
git push --all origin
```

### 5. Verify Push
```bash
# Check if push was successful
git status

# Check remote status
git log --oneline -5 origin/main

# Verify on GitHub (if GitHub CLI is available)
gh repo view --web
```

## Quick GitHub Commands

### Standard Workflow
```bash
# Complete workflow - stage, commit, push
cd /opt/aitbc
git add .
git commit -m "feat: add new feature implementation"
git push origin main
```

### Quick Push
```bash
# Quick push for minor changes
git add . && git commit -m "docs: update documentation" && git push origin main
```

### Specific File Push
```bash
# Push specific changes
git add docs/README.md
git commit -m "docs: update main README"
git push origin main
```

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
# Add GitHub remote
git remote add github https://github.com/oib/AITBC.git

# Set up GitHub with token
git remote set-url github https://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@github.com/oib/AITBC.git

# Push to GitHub specifically
git push github main

# Push to both remotes
git push origin main && git push github main
```

### Sync Operations
```bash
# Pull latest changes from GitHub
git pull origin main

# Sync with GitHub
git fetch origin
git rebase origin/main

# Push to GitHub after sync
git push origin main
```

## Troubleshooting

### Push Failures
```bash
# Check if remote exists
git remote get-url origin

# Check authentication
git config --get remote.origin.url

# Fix authentication issues
git remote set-url origin https://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@github.com/oib/AITBC.git

# Force push if needed
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

# Re-add remote if needed
git remote remove origin
git remote add origin https://github.com/oib/AITBC.git

# Test push
git push origin main --dry-run
```

## GitHub Integration

### GitHub CLI (if available)
```bash
# Create pull request
gh pr create --title "Update CLI documentation" --body "Comprehensive CLI documentation updates"

# View repository
gh repo view

# List issues
gh issue list

# Create release
gh release create v1.0.0 --title "Version 1.0.0" --notes "Initial release"
```

### Web Interface
```bash
# Open repository in browser
xdg-open https://github.com/oib/AITBC

# Open specific commit
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
- Push small, frequent commits
- Ensure tests pass before pushing
- Include documentation with code changes
- Tag releases appropriately

## Recent Updates (v2.0)

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