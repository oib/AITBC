---
name: aitbc-multi-node-operations
description: Multi-node operations including git synchronization, service restart across nodes, blockchain state sync, and coordinated actions across the AITBC multi-node deployment
category: operations
---

# AITBC Multi-Node Operations Skill

## Trigger Conditions
Activate when user requests multi-node operations: git synchronization, service restart across nodes, blockchain state sync, or coordinated actions across the AITBC multi-node deployment.

## Purpose
Synchronize git changes, coordinate blockchain state, and manage multi-node operations across genesis (localhost), follower (aitbc1), and gitea-runner nodes.

## Prerequisites
- SSH access configured between all nodes with key-based authentication
- Git remote configured: `origin` (Gitea) and `github` (GitHub)
- All nodes have AITBC repository at `/opt/aitbc`
- Systemd services operational on all nodes

## Operations

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
# If git pull fails on remote node
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

### Check Blockchain Sync Across Nodes
```bash
# Check block heights on all nodes
for node in localhost aitbc1 gitea-runner; do
  echo "=== $node ==="
  if [ "$node" = "localhost" ]; then
    ./aitbc-cli chain
  else
    ssh "$node" 'cd /opt/aitbc && ./aitbc-cli chain'
  fi
done
```

### Check Service Status on All Nodes
```bash
# Check blockchain services on all nodes
for node in localhost aitbc1 gitea-runner; do
  echo "=== $node ==="
  if [ "$node" = "localhost" ]; then
    systemctl status aitbc-blockchain-node.service --no-pager
  else
    ssh "$node" "systemctl status aitbc-blockchain-node.service --no-pager"
  fi
done
```

### Coordinated Service Restart
```bash
# Restart blockchain services on all nodes
systemctl restart aitbc-blockchain-node.service
ssh aitbc1 'systemctl restart aitbc-blockchain-node.service'
ssh gitea-runner 'systemctl restart aitbc-blockchain-node.service'

# Verify services are running
systemctl status aitbc-blockchain-node.service
ssh aitbc1 'systemctl status aitbc-blockchain-node.service'
ssh gitea-runner 'systemctl status aitbc-blockchain-node.service'
```

## Common Pitfalls

1. **Git Conflicts on Remote Nodes:** Use `--force` flag with caution, prefer manual resolution
2. **Service Start Order:** Ensure services restart in correct order (P2P before blockchain-node)
3. **SSH Connectivity Issues:** Verify SSH keys are configured at `/root/.ssh/` for passwordless access
4. **Sync Partial Failure:** Identify which node failed and retry individually
5. **Blockchain Height Mismatch:** Wait for sync to complete after service restart
6. **Port Mismatches:** Coordinator API is on port 8011 (not 8000)

## Verification Checklist
- [ ] Git status consistent across all nodes
- [ ] Git HEAD matches across all nodes
- [ ] Services running on all nodes
- [ ] Blockchain heights match across nodes
- [ ] P2P connections established (port 7070)
- [ ] RPC endpoints responding (port 8006)

## Node Architecture
- **Genesis Node** (localhost): `/opt/aitbc` - Primary development node
- **Follower Node** (aitbc1): `/opt/aitbc` - Secondary blockchain node
- **Gitea-Runner Node** (gitea-runner): `/opt/aitbc` - CI/CD runner node (also hosts aitbc2 blockchain)

## Git Remote Strategy
- **Primary Remote:** `origin` (GitHub at `https://github.com/oib/AITBC.git`) - Public repository for all operations
- **Development Remote:** `gitea` (Gitea at `http://gitea.bubuit.net:3000/oib/aitbc.git`) - Internal development only

## Best Practices
1. Always verify git status on all nodes before major changes
2. Push to Gitea first, then pull on remote nodes
3. Use `--force-with-lease` instead of `--force` when needed
4. Restart affected services after code sync
5. Verify service health after sync and restart
6. Check blockchain sync after service restarts

## CLI Tool Preference
- **Primary CLI:** `/opt/aitbc/aitbc-cli` is the single CLI entry point
- **SSH Access:** Use `ssh aitbc1` for follower node, `ssh gitea-runner` for CI/CD node
