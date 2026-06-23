---
name: aitbc-node-coordination
description: Cross-node operations including synchronization, coordination, messaging, and multi-node status checks between genesis and follower nodes
category: operations
---

# AITBC Node Coordination Skill

**Status:** 🟡 **Procedure Validated** - Procedures accurate if dependencies and services are present

## Trigger Conditions
Activate when user requests cross-node operations: synchronization, coordination, messaging, or multi-node status checks.

## Purpose
Coordinate cross-node operations, synchronize blockchain state, and manage inter-node messaging between genesis (aitbc) and follower (aitbc1) nodes.

**Note:** For git sync and service restart across all nodes, see aitbc-multi-node-operations.md. This skill focuses on runtime coordination.

## Node Architecture

| Node | Hostname | Role |
|------|----------|------|
| Main Node | aitbc (localhost) | Primary development + blockchain |
| Follower Node | aitbc1 | Secondary blockchain node |
| CI/CD Node | gitea-runner | CI/CD runner |

## Prerequisites
- SSH access configured between nodes with key-based authentication
- Blockchain nodes operational on both nodes via systemd services
- P2P mesh network active on port 7070 with peer configuration
- Unique node IDs configured (proposer_id and p2p_node_id in `/etc/aitbc/.env`)

## Prerequisites Check
Before proceeding, verify:
```bash
# Check SSH connectivity
ssh aitbc1 'echo "SSH to aitbc1 working"'
ssh gitea-runner 'echo "SSH to gitea-runner working"'

# Check service status on all nodes
systemctl list-units --state=running | grep aitbc
ssh aitbc1 'systemctl list-units --state=running | grep aitbc'

# Check Python dependencies
source /opt/aitbc/venv/bin/activate && pip list | grep -E "fastapi|click|uvicorn"

# Verify CLI accessible
/opt/aitbc/aitbc-cli --version

# Check P2P network
ss -tlnp | grep 7070
```

## Port Reference

For authoritative port configuration, see [Service Ports Reference](../../docs/reference/SERVICE_PORTS.md).

**Quick Reference:**
| Service | Port | Notes |
|---------|------|-------|
| Blockchain RPC | 8006 | Main blockchain API + messaging |
| Coordinator API | 8011 | Agent registry |
| Marketplace | 8102 | Marketplace operations |
| P2P Network | 7070 | Blockchain peer-to-peer |

## Operations

### Check Node Health
```bash
# Check service status on all nodes
systemctl status aitbc-blockchain-node.service
ssh aitbc1 'systemctl status aitbc-blockchain-node.service'

# Check RPC health
curl -s http://localhost:8006/health
curl -s http://aitbc1:8006/health

# Check coordinator health
curl -s http://localhost:8011/health
curl -s http://aitbc1:8011/health
```

### Check Blockchain Sync Status
```bash
# Check blockchain height on all nodes
cd /opt/aitbc && ./aitbc-cli chain
ssh aitbc1 'cd /opt/aitbc && ./aitbc-cli chain'
```

### Cross-Node Messaging
```bash
# Topics are shared across nodes via blockchain
curl -s http://localhost:8006/topics
curl -s http://aitbc1:8006/topics  # Same topics

# Post message from either node
curl -s -X POST http://localhost:8006/topics/{id}/messages \
  -H "Content-Type: application/json" \
  -d '{"content":"message from main node"}'

curl -s -X POST http://aitbc1:8006/topics/{id}/messages \
  -H "Content-Type: application/json" \
  -d '{"content":"message from follower node"}'
```

### Cross-Node Agent Discovery
```bash
# Register agent on coordinator
curl -s -X POST http://localhost:8011/agents/register \
  -H "Content-Type: application/json" \
  -d '{"agent_id":"agent-main","agent_type":"worker","endpoint":"http://localhost:9997","capabilities":["marketplace","messaging"]}'

# List agents (same on all nodes via shared state)
curl -s http://localhost:8011/agents
```

### Check P2P Connectivity
```bash
# Check P2P port
ss -tlnp | grep 7070
ssh aitbc1 'ss -tlnp | grep 7070'

# Check network peers
cd /opt/aitbc && ./aitbc-cli network
ssh aitbc1 'cd /opt/aitbc && ./aitbc-cli network'
```

## Common Pitfalls

1. **SSH Connectivity Issues:** Verify SSH keys are configured at `/root/.ssh/` for passwordless access
2. **P2P Handshake Rejection:** Check for duplicate p2p_node_id, run `/opt/aitbc/scripts/utils/generate_unique_node_ids.py`
3. **Service Restart Failures:** Check systemd logs: `journalctl -u aitbc-blockchain-node.service -n 50`
4. **Port Confusion:** Coordinator API is on port 8011 (not 9001)
5. **Using IP Instead of Hostname:** Use `aitbc1` not raw IP addresses

## Verification Checklist
- [ ] SSH connectivity to all nodes verified
- [ ] Blockchain heights match across nodes
- [ ] P2P mesh network operational (port 7070)
- [ ] RPC endpoints responding (port 8006)
- [ ] Coordinator responding (port 8011)
- [ ] Services running on all nodes
- [ ] Node IDs unique (no duplicate p2p_node_id)

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
**Location:** `/opt/aitbc/skills/aitbc-node-coordination.md`
