---
name: aitbc-multi-node-operations
description: Multi-node operations including git synchronization, service restart across nodes, blockchain state sync, and coordinated actions across the AITBC multi-node deployment
category: operations
---

# AITBC Multi-Node Operations Skill

**Status:** 🟡 **Procedure Validated** - Procedures accurate if dependencies and services are present

## Trigger Conditions
Activate when user requests multi-node operations: git synchronization, service restart across nodes, blockchain state sync, or coordinated actions across the AITBC multi-node deployment.

## Purpose
Synchronize git changes, coordinate blockchain state, and manage multi-node operations across genesis (aitbc/main node), follower (aitbc1), and gitea-runner nodes.

## Node Architecture

| Node | Hostname | Role | Access |
|------|----------|------|--------|
| Main Node | aitbc (localhost) | Primary development + blockchain | Direct |
| Follower Node | aitbc1 | Secondary blockchain node | `ssh aitbc1` |
| CI/CD Node | gitea-runner | CI/CD runner (also hosts aitbc2 blockchain) | `ssh gitea-runner` |

## Port Reference (Same on All Nodes)

For authoritative port configuration, see [Service Ports Reference](../../docs/reference/SERVICE_PORTS.md).

**Quick Reference:**
| Service | Port | Notes |
|---------|------|-------|
| Blockchain RPC | 8006 | Main blockchain API |
| Coordinator API | 8011 | Agent registry |
| Marketplace | 8102 | Marketplace operations |
| P2P Network | 7070 | Blockchain peer-to-peer |

## Prerequisites
- SSH access configured between all nodes with key-based authentication
- Git remote configured: `origin` and `github`
- All nodes have AITBC repository at `/opt/aitbc`
- Systemd services operational on all nodes

## Prerequisites Check
Before proceeding, verify:
```bash
# Check SSH connectivity to all nodes
ssh aitbc1 'echo "SSH to aitbc1 working"'
ssh gitea-runner 'echo "SSH to gitea-runner working"'

# Check git remotes
cd /opt/aitbc && git remote -v

# Check service status on all nodes
systemctl list-units --state=running | grep aitbc
ssh aitbc1 'systemctl list-units --state=running | grep aitbc'
ssh gitea-runner 'systemctl list-units --state=running | grep aitbc'

# Verify CLI accessible
/opt/aitbc/aitbc-cli --version
```

## Operations

### Check Multi-Node Git Status
```bash
# Check all three nodes
cd /opt/aitbc
echo "=== Main (aitbc) ===" && git status --short && git rev-parse --short HEAD
echo "=== Follower (aitbc1) ===" && ssh aitbc1 'cd /opt/aitbc && git status --short && git rev-parse --short HEAD'
echo "=== Gitea-Runner ===" && ssh gitea-runner 'cd /opt/aitbc && git status --short && git rev-parse --short HEAD'
```

### Sync All Nodes from Main
```bash
# 1. Commit and push from main node
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
sudo systemctl restart aitbc-coordinator-api.service
ssh aitbc1 'sudo systemctl restart aitbc-coordinator-api.service'
ssh gitea-runner 'sudo systemctl restart aitbc-blockchain-node.service'
```

### Check Blockchain Sync Across Nodes
```bash
# Check block heights on all nodes
for node in localhost aitbc1 gitea-runner; do
  echo "=== $node ==="
  if [ "$node" = "localhost" ]; then
    cd /opt/aitbc && ./aitbc-cli chain
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
sudo systemctl restart aitbc-blockchain-node.service
ssh aitbc1 'sudo systemctl restart aitbc-blockchain-node.service'
ssh gitea-runner 'sudo systemctl restart aitbc-blockchain-node.service'

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
6. **Port Mismatches:** Coordinator API is on port 8011 (not 9001)

## Verification Checklist
- [ ] Git status consistent across all nodes
- [ ] Git HEAD matches across all nodes
- [ ] Services running on all nodes
- [ ] Blockchain heights match across nodes
- [ ] P2P connections established (port 7070)
- [ ] RPC endpoints responding (port 8006)

## Git Remote Strategy
- **Primary Remote:** `origin` (primary dev repo) - Daily development operations
- **Secondary Remote:** `github` (GitHub at `https://github.com/oib/AITBC.git`) - Milestone releases only

## Best Practices
1. Always verify git status on all nodes before major changes
2. Push to GitHub first, then pull on remote nodes
3. Use `--force-with-lease` instead of `--force` when needed
4. Restart affected services after code sync
5. Verify service health after sync and restart
6. Check blockchain sync after service restarts

## CLI Entry Point

**Canonical CLI:** `/opt/aitbc/aitbc-cli` (wrapper script)

This is the single CLI entry point for all AITBC operations. The wrapper script loads `cli/unified_cli.py` automatically.

**Usage Examples:**
```bash
# All CLI operations (use wrapper)
/opt/aitbc/aitbc-cli chain
/opt/aitbc/aitbc-cli network
/opt/aitbc/aitbc-cli balance --name genesis
```

---

**Generated by:** OWL (aitbc main node)
**Date:** 2026-05-20
**Location:** `/opt/aitbc/skills/aitbc-multi-node-operations.md`
