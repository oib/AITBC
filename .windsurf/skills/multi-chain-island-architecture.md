---
description: Autonomous AI skill for configuring, managing, and troubleshooting multi-chain island architecture with gossip-based synchronization
title: Multi-Chain Island Architecture
version: 1.0
---

# Multi-Chain Island Architecture Skill

## Purpose
Autonomous AI skill for configuring, deploying, validating, and troubleshooting multi-chain island architecture where different blockchain nodes serve as hubs for specific chains while maintaining cross-chain synchronization via Redis gossip.

## Activation
Activate this skill when:
- Setting up multi-chain island architecture (hub/member nodes)
- Configuring gossip-based cross-chain synchronization
- Troubleshooting gossip sync issues between chains
- Verifying block production roles (hub vs member)
- Diagnosing Redis Pub/Sub subscription issues
- Validating chain-specific database isolation
- Testing multi-node gossip communication
- Fixing "Gap detected" or "Fork detected" errors in multi-chain setup

## Input Schema
```json
{
  "action_type": {
    "type": "string",
    "enum": ["configure", "validate", "troubleshoot", "test", "reconfigure"],
    "description": "Type of action to perform"
  },
  "nodes": {
    "type": "object",
    "properties": {
      "aitbc": {
        "type": "object",
        "properties": {
          "role": {"type": "string", "enum": ["hub", "member"]},
          "hub_chain": {"type": "string"},
          "member_chains": {"type": "array", "items": {"type": "string"}}
        }
      },
      "aitbc1": {
        "type": "object",
        "properties": {
          "role": {"type": "string", "enum": ["hub", "member"]},
          "hub_chain": {"type": "string"},
          "member_chains": {"type": "array", "items": {"type": "string"}}
        }
      },
      "gitea_runner": {
        "type": "object",
        "properties": {
          "role": {"type": "string", "enum": ["member"]},
          "member_chains": {"type": "array", "items": {"type": "string"}}
        }
      }
    }
  },
  "redis_config": {
    "type": "object",
    "properties": {
      "host": {"type": "string"},
      "port": {"type": "integer"}
    }
  },
  "issue_type": {
    "type": "string",
    "enum": ["gossip_sync_failure", "missing_broadcaster", "config_error", "subscription_issue", "gap_detected", "fork_detected", "unknown"],
    "description": "Type of issue to troubleshoot"
  },
  "diagnostic_data": {
    "type": "object",
    "properties": {
      "error_logs": {"type": "string"},
      "test_results": {"type": "object"},
      "metrics": {"type": "object"}
    }
  },
  "auto_recovery": {
    "type": "boolean",
    "default": true,
    "description": "Enable autonomous recovery actions"
  }
}
```

## Output Schema
```json
{
  "configuration_status": {
    "type": "string",
    "enum": ["configured", "partially_configured", "not_configured", "error"]
  },
  "validation_results": {
    "type": "object",
    "properties": {
      "broadcaster_installed": {"type": "boolean"},
      "gossip_backend_configured": {"type": "boolean"},
      "chain_roles_correct": {"type": "boolean"},
      "redis_subscriptions_active": {"type": "boolean"},
      "block_production_correct": {"type": "boolean"},
      "cross_chain_sync_working": {"type": "boolean"}
    }
  },
  "diagnosis": {
    "root_cause": {"type": "string"},
    "affected_components": {"type": "array", "items": {"type": "string"}},
    "confidence": {"type": "number", "minimum": 0, "maximum": 1}
  },
  "recovery_actions": {
    "type": "array",
    "items": {
      "type": "object",
      "properties": {
        "action": {"type": "string"},
        "command": {"type": "string"},
        "target_node": {"type": "string"},
        "status": {"type": "string", "enum": ["pending", "in_progress", "completed", "failed"]},
        "result": {"type": "string"}
      }
    }
  },
  "recovery_status": {
    "type": "string",
    "enum": ["successful", "partial", "failed", "manual_intervention_required"]
  },
  "recommendations": {
    "type": "array",
    "items": {"type": "string"}
  }
}
```

## Process

### 1. Configure Multi-Chain Island Architecture

#### Set aitbc as Hub of ait-mainnet, Member of ait-testnet
```bash
# Configure aitbc environment
cat > /etc/aitbc/.env << EOF
block_production_chains=ait-mainnet
supported_chains=ait-mainnet,ait-testnet
gossip_backend=broadcast
gossip_broadcast_url=redis://10.1.223.93:6379
EOF

# Restart blockchain node
systemctl restart aitbc-blockchain-node
```

#### Set aitbc1 as Hub of ait-testnet, Member of ait-mainnet
```bash
# Configure aitbc1 environment
ssh aitbc1 'cat > /etc/aitbc/.env << EOF
block_production_chains=ait-testnet
supported_chains=ait-mainnet,ait-testnet
gossip_backend=broadcast
gossip_broadcast_url=redis://10.1.223.93:6379
default_peer_rpc_url=http://10.1.223.93:8006
EOF'

# Restart blockchain node
ssh aitbc1 'systemctl restart aitbc-blockchain-node'
```

#### Set gitea-runner as Member of both chains
```bash
# Configure gitea-runner environment
ssh gitea-runner 'cat > /etc/aitbc/.env << EOF
block_production_chains=
supported_chains=ait-mainnet,ait-testnet
gossip_backend=broadcast
gossip_broadcast_url=redis://10.1.223.93:6379
default_peer_rpc_url=http://10.1.223.93:8006
EOF'

# Restart blockchain node
ssh gitea-runner 'systemctl restart aitbc-blockchain-node'
```

### 2. Validate Configuration

#### Check Broadcaster Module Installation
```bash
# Check on all nodes
python3 -c "from broadcaster import Broadcast; print('OK')"
ssh aitbc1 'python3 -c "from broadcaster import Broadcast; print('OK')"'
ssh gitea-runner 'python3 -c "from broadcaster import Broadcast; print('OK')"'

# If missing, install:
pip install broadcaster>=0.3.1
ssh aitbc1 'pip install broadcaster>=0.3.1'
ssh gitea-runner 'pip install broadcaster>=0.3.1'
```

#### Verify Gossip Backend Configuration
```bash
# Check gossip_backend setting
grep gossip_backend /etc/aitbc/.env
ssh aitbc1 'grep gossip_backend /etc/aitbc/.env'
ssh gitea-runner 'grep gossip_backend /etc/aitbc/.env'

# Expected: gossip_backend=broadcast on all nodes
```

#### Verify Redis Subscriptions
```bash
# Check subscriber count for each chain topic
redis-cli -h 10.1.223.93 -p 6379 PUBSUB NUMSUB blocks.ait-mainnet
redis-cli -h 10.1.223.93 -p 6379 PUBSUB NUMSUB blocks.ait-testnet

# Expected: 3 subscribers for each topic (aitbc, aitbc1, gitea-runner)
```

#### Verify Block Production Roles
```bash
# Check aitbc is producing only ait-mainnet blocks
journalctl -u aitbc-blockchain-node --since "5 minutes ago" --no-pager | grep "\[BROADCAST\].*ait-mainnet" | wc -l
journalctl -u aitbc-blockchain-node --since "5 minutes ago" --no-pager | grep "\[BROADCAST\].*ait-testnet" | wc -l

# Expected: ait-mainnet > 0, ait-testnet = 0

# Check aitbc1 is producing only ait-testnet blocks
ssh aitbc1 'journalctl -u aitbc-blockchain-node --since "5 minutes ago" --no-pager | grep "\[BROADCAST\].*ait-testnet" | wc -l'
ssh aitbc1 'journalctl -u aitbc-blockchain-node --since "5 minutes ago" --no-pager | grep "\[BROADCAST\].*ait-mainnet" | wc -l'

# Expected: ait-testnet > 0, ait-mainnet = 0

# Check gitea-runner is producing no blocks
ssh gitea-runner 'journalctl -u aitbc-blockchain-node --since "5 minutes ago" --no-pager | grep "\[BROADCAST\]" | wc -l'

# Expected: 0
```

#### Verify Cross-Chain Sync
```bash
# Check aitbc is receiving ait-testnet blocks
journalctl -u aitbc-blockchain-node --since "5 minutes ago" --no-pager | grep "Received block.*ait-testnet" | wc -l

# Expected: > 0

# Check aitbc1 is receiving ait-mainnet blocks
ssh aitbc1 'journalctl -u aitbc-blockchain-node --since "5 minutes ago" --no-pager | grep "Received block.*ait-mainnet" | wc -l'

# Expected: > 0

# Check gitea-runner is receiving both chains
ssh gitea-runner 'journalctl -u aitbc-blockchain-node --since "5 minutes ago" --no-pager | grep "Received block.*ait-mainnet" | wc -l'
ssh gitea-runner 'journalctl -u aitbc-blockchain-node --since "5 minutes ago" --no-pager | grep "Received block.*ait-testnet" | wc -l'

# Expected: both > 0
```

### 3. Troubleshoot Common Issues

#### Missing Broadcaster Module
```bash
# Symptom: Node not receiving gossip messages
# Root Cause: broadcaster module not installed, fallback to in-memory backend

# Check if broadcaster is installed
python3 -c "from broadcaster import Broadcast; print('OK')" || echo "NOT INSTALLED"

# Install broadcaster
source venv/bin/activate
pip install broadcaster>=0.3.1

# Restart service
systemctl restart aitbc-blockchain-node
```

#### Redis Subscription Not Working
```bash
# Symptom: Redis shows correct subscriber count but node not receiving messages
# Root Cause: Broadcast backend not connected or subscription failed

# Check Redis client connections
redis-cli -h 10.1.223.93 -p 6379 CLIENT LIST

# Restart service to re-establish connections
systemctl restart aitbc-blockchain-node
ssh aitbc1 'systemctl restart aitbc-blockchain-node'
ssh gitea-runner 'systemctl restart aitbc-blockchain-node'
```

#### Gap Detected Errors
```bash
# Symptom: "Gap detected" errors in logs
# Root Cause: Corrupted or stale database from previous sync attempts

# Clear affected chain database
systemctl stop aitbc-blockchain-node
rm -rf /var/lib/aitbc/data/[chain-name]
systemctl start aitbc-blockchain-node

# Example for aitbc1 ait-mainnet:
ssh aitbc1 'systemctl stop aitbc-blockchain-node && rm -rf /var/lib/aitbc/data/ait-mainnet && systemctl start aitbc-blockchain-node'
```

#### Fork Detected Warnings
```bash
# Symptom: "Fork detected" warnings in logs
# Root Cause: Cross-chain broadcasting bug (fixed in recent code)

# Ensure latest code is deployed
cd /opt/aitbc
git pull origin main
systemctl restart aitbc-blockchain-node
ssh aitbc1 'cd /opt/aitbc && git pull origin main && systemctl restart aitbc-blockchain-node'
```

### 4. Run Validation Test
```bash
# Run dedicated multi-chain island test script
bash scripts/workflow/46_multi_chain_island_test.sh

# Expected output: All tests PASSED
```

### 5. Clear Stale Databases (if needed)
```bash
# Clear aitbc1's ait-mainnet database (member role)
ssh aitbc1 'systemctl stop aitbc-blockchain-node && rm -rf /var/lib/aitbc/data/ait-mainnet && systemctl start aitbc-blockchain-node'

# Clear gitea-runner's ait-testnet database (member role)
ssh gitea-runner 'systemctl stop aitbc-blockchain-node && rm -rf /var/lib/aitbc/data/ait-testnet && systemctl start aitbc-blockchain-node'
```

## Constraints
- Maximum reconfiguration attempts: 3 per node
- Cannot modify hub chains without clearing databases first
- Must preserve blockchain data for hub chains
- Cannot restart services during peak hours (9AM-5PM) without confirmation
- Must verify Redis connectivity before gossip configuration
- Cannot change gossip_backend without broadcaster module installed
- Must log all configuration changes
- Escalate if configuration fails after 3 attempts

## Environment Assumptions
- aitbc IP: 10.1.223.93 (hub of ait-mainnet, member of ait-testnet)
- aitbc1 IP: 10.1.223.93 (hub of ait-testnet, member of ait-mainnet)
- gitea-runner IP: 10.1.223.93 (member of both chains)
- Redis server: redis://10.1.223.93:6379
- SSH access to all nodes configured and working
- Blockchain RPC port: 8006
- Log directory: /var/log/aitbc/
- Database directory: /var/lib/aitbc/data/
- Environment file: /etc/aitbc/.env
- Test script: /opt/aitbc/scripts/workflow/46_multi_chain_island_test.sh

## Error Handling

### Broadcaster Module Missing
- Log missing module on affected nodes
- Install broadcaster>=0.3.1
- Restart affected services
- Verify installation

### Redis Connection Failed
- Check Redis server status
- Verify network connectivity
- Check firewall rules
- Escalate if Redis unreachable

### Configuration Validation Failed
- Log specific validation error
- Attempt to correct configuration
- Restart affected service
- Re-validate after correction

### Gap Detection Errors Persist
- Clear affected chain database
- Restart service
- Monitor for new errors
- Escalate if errors continue

### Service Restart Failed
- Check service logs for errors
- Verify configuration files
- Check system resources
- Escalate if service cannot be restarted

### Database Clear Failed
- Stop service before clearing
- Verify directory permissions
- Clear entire directory (rm -rf)
- Restart service after clearing

## Example Usage Prompts

### Initial Configuration
"Configure multi-chain island architecture with aitbc as hub of ait-mainnet, aitbc1 as hub of ait-testnet, and gitea-runner as member of both chains."

### Validation
"Validate the multi-chain island architecture configuration and report status."

### Troubleshoot Gossip Sync
"aitbc is not receiving ait-testnet blocks via gossip. Diagnose and fix the issue."

### Fix Missing Broadcaster
"Install missing broadcaster module on aitbc and restart blockchain service."

### Clear Stale Database
"Clear aitbc1's ait-mainnet database to fix gap detection errors."

### Full Validation Test
"Run the multi-chain island architecture validation test and report results."

## Expected Output Example
```json
{
  "configuration_status": "configured",
  "validation_results": {
    "broadcaster_installed": true,
    "gossip_backend_configured": true,
    "chain_roles_correct": true,
    "redis_subscriptions_active": true,
    "block_production_correct": true,
    "cross_chain_sync_working": true
  },
  "diagnosis": {
    "root_cause": "None - configuration is correct",
    "affected_components": [],
    "confidence": 1.0
  },
  "recovery_actions": [],
  "recovery_status": "successful",
  "recommendations": [
    "Monitor gossip sync regularly",
    "Run validation test daily",
    "Check Redis subscriber counts weekly"
  ]
}
```

## Model Routing
- **Fast Model**: Use for simple configuration checks and status queries
- **Reasoning Model**: Use for complex diagnostics, root cause analysis, multi-step recovery
- **Reasoning Model**: Use when troubleshooting requires cross-node coordination

## Performance Notes
- **Configuration Time**: 30-60 seconds per node
- **Validation Time**: 60-120 seconds for full validation
- **Troubleshooting Time**: 60-300 seconds depending on issue
- **Database Clear Time**: 10-30 seconds per database
- **Memory Usage**: <500MB during operations
- **Network Impact**: Minimal during validation, moderate during database clear
- **Concurrency**: Can configure nodes in parallel
- **Logging**: All actions logged with timestamps for audit trail

## Related Skills
- [blockchain-troubleshoot-recovery](/blockchain-troubleshoot-recovery.md) - For general blockchain troubleshooting
- [aitbc-system-architect](/aitbc-system-architect.md) - For system-level architecture decisions
- [log-monitor](/log-monitor.md) - For monitoring blockchain node logs

## Related Workflows
- [Multi-Chain Island Architecture Test](/workflows/46_multi_chain_island_test.sh) - Validation test script
- [Multi-Chain Island Architecture Scenario](/docs/scenarios/46_multi_chain_island_architecture.md) - Documentation
- [Multi-Chain Island Architecture CI](/.gitea/workflows/multi-chain-island-architecture.yml) - CI/CD workflow
