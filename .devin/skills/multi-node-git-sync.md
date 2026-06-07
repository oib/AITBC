# Multi-Node Git Sync Skill

This skill provides expertise in synchronizing git changes across AITBC multi-node deployment (genesis, follower, gitea-runner).

## Node Architecture

- **Genesis Node** (localhost): `/opt/aitbc` - Primary development node
- **Follower Node** (aitbc1): `/opt/aitbc` - Secondary blockchain node
- **Gitea-Runner Node** (gitea-runner): `/opt/aitbc` - CI/CD runner node

## Git Remote Strategy

- **Primary Remote**: `origin` (Gitea) - Daily development operations
- **Secondary Remote**: `github` - Milestone releases only

## Common Operations

### Check Multi-Node Git Status
```bash
# Check all three nodes
cd /opt/aitbc
echo "=== Genesis ===" && git status --short && git rev-parse --short HEAD
echo "=== Follower ===" && ssh aitbc1 'cd /opt/aitbc && git status --short && git rev-parse --short HEAD'
echo "=== Gitea-Runner ===" && ssh gitea-runner 'cd /opt/aitbc && git status --short && git rev-parse --short HEAD'
```

### Sync All Nodes from Genesis
```bash
# 1. Commit and push from genesis
cd /opt/aitbc
git add . && git commit -m "feat: description" && git push origin main

# 2. Pull on follower
ssh aitbc1 'cd /opt/aitbc && git pull origin main'

# 3. Pull on gitea-runner
ssh gitea-runner 'cd /opt/aitbc && git pull origin main'

# 4. Verify sync
# (use check status command above)
```

### Handle Sync Conflicts
```bash
# If git pull fails on remote node:
ssh aitbc1 'cd /opt/aitbc && git checkout --force . && git clean -fd && git pull origin main'
ssh gitea-runner 'cd /opt/aitbc && git checkout --force . && git clean -fd && git pull origin main'
```

### Service Restart After Sync
```bash
# Restart services that need code updates
ssh aitbc1 'systemctl restart aitbc-agent-coordinator.service'
ssh aitbc1 'systemctl restart aitbc-blockchain-node.service'
ssh gitea-runner 'systemctl restart aitbc-blockchain-node.service'
```

## Best Practices

1. Always verify git status on all nodes before major changes
2. Push to Gitea first, then pull on remote nodes
3. Use `--force-with-lease` instead of `--force` when needed
4. Restart affected services after code sync
5. Verify service health after sync and restart
