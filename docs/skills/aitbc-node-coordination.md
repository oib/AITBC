---
name: aitbc-node-coordination
description: Cross-node operations including synchronization, coordination, messaging, and multi-node status checks between genesis and follower nodes
category: operations
---

# AITBC Node Coordination Skill

## Trigger Conditions
Activate when user requests cross-node operations: synchronization, coordination, messaging, or multi-node status checks.

## Purpose
Coordinate cross-node operations, synchronize blockchain state, and manage inter-node messaging between genesis and follower nodes.

## Prerequisites
- SSH access configured between genesis (aitbc) and follower (aitbc1) with key-based authentication
- Blockchain nodes operational on both nodes via systemd services
- P2P mesh network active on port 7070 with peer configuration
- Unique node IDs configured (proposer_id and p2p_node_id in `/etc/aitbc/.env` and `/etc/aitbc/node.env`)
- Git synchronization configured between nodes at `/opt/aitbc/.git`

## Operations

### Check Multi-Node Status
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

### Check Blockchain Sync Status
```bash
# Check blockchain height on all nodes
./aitbc-cli chain
ssh aitbc1 'cd /opt/aitbc && ./aitbc-cli chain'
ssh gitea-runner 'cd /opt/aitbc && ./aitbc-cli chain'
```

### Check Node Health
```bash
# Check service status on all nodes
systemctl status aitbc-blockchain-node.service
ssh aitbc1 'systemctl status aitbc-blockchain-node.service'
ssh gitea-runner 'systemctl status aitbc-blockchain-node.service'
```

## Common Pitfalls

1. **SSH Connectivity Issues:** Verify SSH keys are configured at `/root/.ssh/` for passwordless access
2. **Git Conflicts:** Use `--force` flag with caution, prefer manual resolution
3. **P2P Handshake Rejection:** Check for duplicate p2p_node_id, run `/opt/aitbc/scripts/utils/generate_unique_node_ids.py`
4. **Service Restart Failures:** Check systemd logs: `journalctl -u aitbc-blockchain-node.service -n 50`
5. **Sync Partial Failure:** Identify which sync type failed (blockchain, mempool, configuration, git)

## Verification Checklist
- [ ] SSH connectivity to all nodes verified
- [ ] Git status consistent across all nodes
- [ ] Blockchain heights match across nodes
- [ ] P2P mesh network operational (port 7070)
- [ ] Services running on all nodes
- [ ] Node IDs unique (no duplicate p2p_node_id)

## Node Architecture
- **Genesis Node** (localhost): `/opt/aitbc` - Primary development node
- **Follower Node** (aitbc1): `/opt/aitbc` - Secondary blockchain node
- **Gitea-Runner Node** (gitea-runner): `/opt/aitbc` - CI/CD runner node (also hosts aitbc2 blockchain)

## Git Remote Strategy
- **Primary Remote:** `origin` (Gitea) - Daily development operations
- **Secondary Remote:** `github` - Milestone releases only

## CLI Tool Preference
- **Primary CLI:** `/opt/aitbc/aitbc-cli` is the single CLI entry point
- **SSH Access:** Use `ssh aitbc1` for follower node, `ssh gitea-runner` for CI/CD node
