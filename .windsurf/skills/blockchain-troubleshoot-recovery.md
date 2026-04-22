---
description: Autonomous AI skill for blockchain troubleshooting and recovery across multi-node AITBC setup
title: Blockchain Troubleshoot & Recovery
version: 1.1
---

# Blockchain Troubleshoot & Recovery Skill

## Purpose
Autonomous AI skill for diagnosing and resolving blockchain communication issues between aitbc (genesis) and aitbc1 (follower) nodes running on port 8006 across different physical machines.

## Activation
Activate this skill when:
- Blockchain communication tests fail
- Nodes become unreachable
- Block synchronization lags (>10 blocks)
- Transaction propagation times exceed thresholds
- Git synchronization fails
- Network latency issues detected
- Service health checks fail
- P2P handshake rejections (duplicate node IDs)
- Nodes with identical p2p_node_id or proposer_id

## Input Schema
```json
{
  "issue_type": {
    "type": "string",
    "enum": ["connectivity", "sync_lag", "transaction_timeout", "service_failure", "git_sync_failure", "network_latency", "p2p_identity_conflict", "unknown"],
    "description": "Type of blockchain communication issue"
  },
  "affected_nodes": {
    "type": "array",
    "items": {"type": "string", "enum": ["aitbc", "aitbc1", "both"]},
    "description": "Nodes affected by the issue"
  },
  "severity": {
    "type": "string",
    "enum": ["low", "medium", "high", "critical"],
    "description": "Severity level of the issue"
  },
  "diagnostic_data": {
    "type": "object",
    "properties": {
      "error_logs": {"type": "string"},
      "test_results": {"type": "object"},
      "metrics": {"type": "object"}
    },
    "description": "Diagnostic data from failed tests"
  },
  "auto_recovery": {
    "type": "boolean",
    "default": true,
    "description": "Enable autonomous recovery actions"
  },
  "recovery_timeout": {
    "type": "integer",
    "default": 300,
    "description": "Maximum time (seconds) for recovery attempts"
  }
}
```

## Output Schema
```json
{
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
  "post_recovery_validation": {
    "tests_passed": {"type": "integer"},
    "tests_failed": {"type": "integer"},
    "metrics_restored": {"type": "boolean"}
  },
  "recommendations": {
    "type": "array",
    "items": {"type": "string"}
  },
  "escalation_required": {
    "type": "boolean"
  }
}
```

## Process

### 1. Diagnose Issue
```bash
# Collect diagnostic information
tail -100 /var/log/aitbc/blockchain-communication-test.log > /tmp/diagnostic_logs.txt
tail -50 /var/log/aitbc/blockchain-test-errors.txt >> /tmp/diagnostic_logs.txt

# Check service status
systemctl status aitbc-blockchain-rpc --no-pager >> /tmp/diagnostic_logs.txt
ssh aitbc1 'systemctl status aitbc-blockchain-rpc --no-pager' >> /tmp/diagnostic_logs.txt

# Check network connectivity
ping -c 5 10.1.223.40 >> /tmp/diagnostic_logs.txt
ping -c 5 <aitbc1-ip> >> /tmp/diagnostic_logs.txt

# Check port accessibility
netstat -tlnp | grep 8006 >> /tmp/diagnostic_logs.txt

# Check blockchain status
NODE_URL=http://10.1.223.40:8006 ./aitbc-cli blockchain info --verbose >> /tmp/diagnostic_logs.txt
NODE_URL=http://<aitbc1-ip>:8006 ./aitbc-cli blockchain info --verbose >> /tmp/diagnostic_logs.txt
```

### 2. Analyze Root Cause
Based on diagnostic data, identify:
- Network connectivity issues (firewall, routing)
- Service failures (crashes, hangs)
- Synchronization problems (git, blockchain)
- Resource exhaustion (CPU, memory, disk)
- Configuration errors

### 3. Execute Recovery Actions

#### P2P Identity Conflict Recovery
```bash
# Check current node IDs on all nodes
echo "=== aitbc node IDs ==="
grep -E "^(proposer_id|p2p_node_id)=" /etc/aitbc/.env /etc/aitbc/node.env

echo "=== aitbc1 node IDs ==="
ssh aitbc1 'grep -E "^(proposer_id|p2p_node_id)=" /etc/aitbc/.env /etc/aitbc/node.env'

echo "=== gitea-runner node IDs ==="
ssh gitea-runner 'grep -E "^(proposer_id|p2p_node_id)=" /etc/aitbc/.env /etc/aitbc/node.env'

# Run unique ID generation on affected nodes
python3 /opt/aitbc/scripts/utils/generate_unique_node_ids.py
ssh aitbc1 'python3 /opt/aitbc/scripts/utils/generate_unique_node_ids.py'
ssh gitea-runner 'python3 /opt/aitbc/scripts/utils/generate_unique_node_ids.py'

# Restart P2P services on all nodes
systemctl restart aitbc-blockchain-p2p
ssh aitbc1 'systemctl restart aitbc-blockchain-p2p'
ssh gitea-runner 'systemctl restart aitbc-blockchain-p2p'

# Verify P2P connectivity
journalctl -u aitbc-blockchain-p2p -n 30 --no-pager
ssh aitbc1 'journalctl -u aitbc-blockchain-p2p -n 30 --no-pager'
ssh gitea-runner 'journalctl -u aitbc-blockchain-p2p -n 30 --no-pager'
```

#### Connectivity Recovery
```bash
# Restart network services
systemctl restart aitbc-blockchain-p2p
ssh aitbc1 'systemctl restart aitbc-blockchain-p2p'

# Check and fix firewall rules
iptables -L -n | grep 8006
if [ $? -ne 0 ]; then
    iptables -A INPUT -p tcp --dport 8006 -j ACCEPT
    iptables -A OUTPUT -p tcp --sport 8006 -j ACCEPT
fi

# Test connectivity
curl -f -s http://10.1.223.40:8006/health
curl -f -s http://<aitbc1-ip>:8006/health
```

#### Service Recovery
```bash
# Restart blockchain services
systemctl restart aitbc-blockchain-rpc
ssh aitbc1 'systemctl restart aitbc-blockchain-rpc'

# Restart coordinator if needed
systemctl restart aitbc-coordinator
ssh aitbc1 'systemctl restart aitbc-coordinator'

# Check service logs
journalctl -u aitbc-blockchain-rpc -n 50 --no-pager
```

#### Synchronization Recovery
```bash
# Force blockchain sync
./aitbc-cli cluster sync --all --yes

# Git sync recovery
cd /opt/aitbc
git fetch origin main
git reset --hard origin/main
ssh aitbc1 'cd /opt/aitbc && git fetch origin main && git reset --hard origin/main'

# Verify sync
git log --oneline -5
ssh aitbc1 'cd /opt/aitbc && git log --oneline -5'
```

#### Resource Recovery
```bash
# Clear system caches
sync && echo 3 > /proc/sys/vm/drop_caches

# Restart if resource exhausted
systemctl restart aitbc-*
ssh aitbc1 'systemctl restart aitbc-*'
```

### 4. Validate Recovery
```bash
# Run full communication test
./scripts/blockchain-communication-test.sh --full --debug

# Verify all services are healthy
curl http://10.1.223.40:8006/health
curl http://<aitbc1-ip>:8006/health
curl http://10.1.223.40:8001/health
curl http://10.1.223.40:8000/health

# Check blockchain sync
NODE_URL=http://10.1.223.40:8006 ./aitbc-cli blockchain height
NODE_URL=http://<aitbc1-ip>:8006 ./aitbc-cli blockchain height
```

### 5. Report and Escalate
- Document recovery actions taken
- Provide metrics before/after recovery
- Recommend preventive measures
- Escalate if recovery fails or manual intervention needed

## Constraints
- Maximum recovery attempts: 3 per issue type
- Recovery timeout: 300 seconds per action
- Cannot restart services during peak hours (9AM-5PM local time) without confirmation
- Must preserve blockchain data integrity
- Cannot modify wallet keys or cryptographic material
- Must log all recovery actions
- Escalate to human if recovery fails after 3 attempts

## Environment Assumptions
- Genesis node IP: 10.1.223.40
- Follower node IP: <aitbc1-ip> (replace with actual IP)
- Both nodes use port 8006 for blockchain RPC
- SSH access to aitbc1 configured and working
- AITBC CLI accessible at /opt/aitbc/aitbc-cli
- Git repository: http://gitea.bubuit.net:3000/oib/aitbc.git
- Log directory: /var/log/aitbc/
- Test script: /opt/aitbc/scripts/blockchain-communication-test.sh
- Systemd services: aitbc-blockchain-rpc, aitbc-coordinator, aitbc-blockchain-p2p

## Error Handling

### Recovery Action Failure
- Log specific failure reason
- Attempt alternative recovery method
- Increment failure counter
- Escalate after 3 failures

### Service Restart Failure
- Check service logs for errors
- Verify configuration files
- Check system resources
- Escalate if service cannot be restarted

### Network Unreachable
- Check physical network connectivity
- Verify firewall rules
- Check routing tables
- Escalate if network issue persists

### Data Integrity Concerns
- Stop all recovery actions
- Preserve current state
- Escalate immediately for manual review
- Do not attempt automated recovery

### Timeout Exceeded
- Stop current recovery action
- Log timeout event
- Attempt next recovery method
- Escalate if all methods timeout

## Example Usage Prompts

### Basic Troubleshooting
"Blockchain communication test failed on aitbc1 node. Diagnose and recover."

### Specific Issue Type
"Block synchronization lag detected (>15 blocks). Perform autonomous recovery."

### Service Failure
"aitbc-blockchain-rpc service crashed on genesis node. Restart and validate."

### Network Issue
"Cannot reach aitbc1 node on port 8006. Troubleshoot network connectivity."

### Full Recovery
"Complete blockchain communication test failed with multiple issues. Perform full autonomous recovery."

### Escalation Scenario
"Recovery actions failed after 3 attempts. Prepare escalation report with diagnostic data."

## Expected Output Example
```json
{
  "diagnosis": {
    "root_cause": "Network firewall blocking port 8006 on follower node",
    "affected_components": ["network", "firewall", "aitbc1"],
    "confidence": 0.95
  },
  "recovery_actions": [
    {
      "action": "Check firewall rules",
      "command": "iptables -L -n | grep 8006",
      "target_node": "aitbc1",
      "status": "completed",
      "result": "Port 8006 not in allowed rules"
    },
    {
      "action": "Add firewall rule",
      "command": "iptables -A INPUT -p tcp --dport 8006 -j ACCEPT",
      "target_node": "aitbc1",
      "status": "completed",
      "result": "Rule added successfully"
    },
    {
      "action": "Test connectivity",
      "command": "curl -f -s http://<aitbc1-ip>:8006/health",
      "target_node": "aitbc1",
      "status": "completed",
      "result": "Node reachable"
    }
  ],
  "recovery_status": "successful",
  "post_recovery_validation": {
    "tests_passed": 5,
    "tests_failed": 0,
    "metrics_restored": true
  },
  "recommendations": [
    "Add persistent firewall rules to /etc/iptables/rules.v4",
    "Monitor firewall changes for future prevention",
    "Consider implementing network monitoring alerts"
  ],
  "escalation_required": false
}
```

## Model Routing
- **Fast Model**: Use for simple, routine recoveries (service restarts, basic connectivity)
- **Reasoning Model**: Use for complex diagnostics, root cause analysis, multi-step recovery
- **Reasoning Model**: Use when recovery fails and escalation planning is needed

## Performance Notes
- **Diagnosis Time**: 10-30 seconds depending on issue complexity
- **Recovery Time**: 30-120 seconds per recovery action
- **Validation Time**: 60-180 seconds for full test suite
- **Memory Usage**: <500MB during recovery operations
- **Network Impact**: Minimal during diagnostics, moderate during git sync
- **Concurrency**: Can handle single issue recovery; multiple issues should be queued
- **Optimization**: Cache diagnostic data to avoid repeated collection
- **Rate Limiting**: Limit service restarts to prevent thrashing
- **Logging**: All actions logged with timestamps for audit trail

## Related Skills
- [aitbc-node-coordinator](/aitbc-node-coordinator.md) - For cross-node coordination during recovery
- [openclaw-error-handler](/openclaw-error-handler.md) - For error handling and escalation
- [openclaw-coordination-orchestrator](/openclaw-coordination-orchestrator.md) - For multi-node recovery coordination

## Related Workflows
- [Blockchain Communication Test](/workflows/blockchain-communication-test.md) - Testing workflow that triggers this skill
- [Multi-Node Operations](/workflows/multi-node-blockchain-operations.md) - General node operations
