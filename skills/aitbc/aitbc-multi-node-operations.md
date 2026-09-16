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
Synchronize git changes, coordinate blockchain state, and manage multi-node operations across the hub/proposer (`hub`), followers (`node0`/`node1`/`node2`), and the demoted follower `hub1`.

## Node Architecture

| Node | Hostname | Role | Access |
|------|----------|------|--------|
| Hub / Proposer | `hub` (hub.aitbc, 10.177.61.28) | Block production, coordinator, marketplace | `ssh hub` |
| Follower | `node0` (10.1.223.93) | Customer GPU node | `ssh node0` |
| Follower / PBFT | `node1` (10.1.223.40) | Validator | `ssh node1` |
| Follower / shop | `node2` (10.1.223.136) | Shop node, commits/pushes to gitea | `ssh node2` |
| Demoted follower | `hub1` (192.168.100.10) | Old hub, pull-only replica | `ssh hub1` |

Legacy names `aitbc`, `aitbc1`..`aitbc3`, `node3`, and `hub2.aitbc.bubuit.net` are retired — `aitbc3` in older docs means today's `node2`.

## Port Reference (Same on All Nodes)

For authoritative port configuration, see [Service Ports Reference](../../docs/reference/SERVICE_PORTS.md).

**Quick Reference:**
| Service | Port | Notes |
|---------|------|-------|
| Blockchain RPC | 8202 | Main blockchain API |
| Coordinator API | 8203 | Agent registry |
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
ssh node1 'echo "SSH to node1 working"'
ssh node2 'echo "SSH to node2 working"'

# Check git remotes
cd /opt/aitbc && git remote -v

# Check service status on all nodes
systemctl list-units --state=running | grep aitbc
ssh node1 'systemctl list-units --state=running | grep aitbc'
ssh node2 'systemctl list-units --state=running | grep aitbc'

# Verify CLI accessible
aitbc version
```

## Operations

### Check Multi-Node Git Status
```bash
# Check all three nodes
cd /opt/aitbc
echo "=== Main (aitbc) ===" && git status --short && git rev-parse --short HEAD
echo "=== Follower (node1) ===" && ssh node1 'cd /opt/aitbc && git status --short && git rev-parse --short HEAD'
echo "=== node2 ===" && ssh node2 'cd /opt/aitbc && git status --short && git rev-parse --short HEAD'
```

### Sync All Nodes from Main
```bash
# 1. Commit and push from main node
cd /opt/aitbc
git add . && git commit -m "feat: description" && git push origin main

# 2. Pull on follower
ssh node1 'cd /opt/aitbc && git pull origin main'

# 3. Pull on node2
ssh node2 'cd /opt/aitbc && git pull origin main'

# 4. Verify sync
# (use check status command above)
```

### Handle Sync Conflicts
```bash
# If git pull fails on remote node
ssh node1 'cd /opt/aitbc && git checkout --force . && git clean -fd && git pull origin main'
ssh node2 'cd /opt/aitbc && git checkout --force . && git clean -fd && git pull origin main'
```

### Service Restart After Sync
```bash
# Restart services that need code updates — run each where it lives:
# coordinator-api runs on hub; blockchain-node runs on every node
ssh hub 'sudo systemctl restart aitbc-coordinator-api.service'
ssh node1 'sudo systemctl restart aitbc-blockchain-node.service'
ssh node2 'sudo systemctl restart aitbc-blockchain-node.service'
```

`localhost` below means whichever node you run the commands on (typically
`node2` or `hub` — the commit/push nodes).

### Check Blockchain Sync Across Nodes
```bash
# Check block heights on all nodes
for node in localhost node1 node2; do
  echo "=== $node ==="
  if [ "$node" = "localhost" ]; then
    aitbc blockchain height
  else
    ssh "$node" 'aitbc blockchain height'
  fi
done
```

### Check Service Status on All Nodes
```bash
# Check blockchain services on all nodes
for node in localhost node1 node2; do
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
ssh node1 'sudo systemctl restart aitbc-blockchain-node.service'
ssh node2 'sudo systemctl restart aitbc-blockchain-node.service'

# Verify services are running
systemctl status aitbc-blockchain-node.service
ssh node1 'systemctl status aitbc-blockchain-node.service'
ssh node2 'systemctl status aitbc-blockchain-node.service'
```

## Common Pitfalls

1. **Git Conflicts on Remote Nodes:** Use `--force` flag with caution, prefer manual resolution
2. **Service Start Order:** Ensure services restart in correct order (P2P before blockchain-node)
3. **SSH Connectivity Issues:** Verify SSH keys are configured at `/root/.ssh/` for passwordless access
4. **Sync Partial Failure:** Identify which node failed and retry individually
5. **Blockchain Height Mismatch:** Wait for sync to complete after service restart
6. **Port Mismatches:** Coordinator API is on port 8203 (not 9001)

## Verification Checklist
- [ ] Git status consistent across all nodes
- [ ] Git HEAD matches across all nodes
- [ ] Services running on all nodes
- [ ] Blockchain heights match across nodes
- [ ] P2P connections established (port 7070)
- [ ] RPC endpoints responding (port 8202)

## Git Remote Strategy
- **Primary Remote:** `origin` (primary dev repo) - Daily development operations
- **Secondary Remote:** `github` (GitHub at `https://github.com/oib/AITBC.git`) - Milestone releases only

## Best Practices
1. Always verify git status on all nodes before major changes
2. Push to gitea `origin` first, then pull on remote nodes (the `github` remote is fetch-only on live nodes; the mirror is pushed from the IDE `/opt/aitbc`)
3. Use `--force-with-lease` instead of `--force` when needed
4. Restart affected services after code sync
5. Verify service health after sync and restart
6. Check blockchain sync after service restarts

## CLI Entry Point

**Canonical CLI:** `aitbc` (`/usr/local/bin/aitbc`, a shell wrapper exec'ing `python -m aitbc_cli.core.main` inside `/opt/aitbc/venv`)

This is the single CLI entry point for all AITBC operations.

**Usage Examples:**
```bash
# All CLI operations
aitbc blockchain height
aitbc network status
aitbc wallet balance --name genesis
```

---

**Generated by:** OWL (aitbc main node)
**Date:** 2026-05-20
**Location:** `/opt/aitbc/skills/aitbc-multi-node-operations.md`
