---
description: Autonomous AI skill for monitoring journalctl and logfiles across all AITBC nodes
title: AITBC Log Monitor
version: 1.0
---

# AITBC Log Monitor Skill

## Purpose
Autonomous AI skill for real-time monitoring of journalctl logs and AITBC logfiles across all nodes (aitbc, aitbc1, gitea-runner). Provides error detection, alerting, and cross-node log correlation for aitbc-* systemd services and application logs.

## Activation
Activate this skill when:
- Real-time log monitoring is needed across all AITBC nodes
- Error detection and alerting is required for aitbc-* services
- Cross-node log correlation is needed for troubleshooting
- Service health monitoring is required
- Log analysis for debugging or investigation is needed

## Input Schema
```json
{
  "monitoring_mode": {
    "type": "string",
    "enum": ["realtime", "historical", "error_only", "full"],
    "description": "Monitoring mode for logs"
  },
  "services": {
    "type": "array",
    "items": {"type": "string"},
    "description": "Specific aitbc-* services to monitor (empty = all services)"
  },
  "nodes": {
    "type": "array",
    "items": {"type": "string", "enum": ["aitbc", "aitbc1", "gitea-runner", "all"]},
    "description": "Nodes to monitor (default: all)"
  },
  "log_paths": {
    "type": "array",
    "items": {"type": "string"},
    "description": "Additional log paths to monitor in /var/log/aitbc/"
  },
  "error_keywords": {
    "type": "array",
    "items": {"type": "string"},
    "description": "Keywords to trigger error alerts (default: ERROR, CRITICAL, FAILED, exception)"
  },
  "alert_threshold": {
    "type": "integer",
    "default": 5,
    "description": "Number of errors before triggering alert"
  },
  "duration": {
    "type": "integer",
    "description": "Monitoring duration in seconds (null = indefinite)"
  }
}
```

## Output Schema
```json
{
  "monitoring_status": {
    "type": "string",
    "enum": ["active", "completed", "stopped", "error"]
  },
  "nodes_monitored": {
    "type": "array",
    "items": {"type": "string"}
  },
  "services_monitored": {
    "type": "array",
    "items": {"type": "string"}
  },
  "error_summary": {
    "type": "object",
    "properties": {
      "total_errors": {"type": "integer"},
      "by_service": {"type": "object"},
      "by_node": {"type": "object"},
      "recent_errors": {"type": "array"}
    }
  },
  "alerts_triggered": {
    "type": "array",
    "items": {
      "type": "object",
      "properties": {
        "timestamp": {"type": "string"},
        "node": {"type": "string"},
        "service": {"type": "string"},
        "message": {"type": "string"},
        "severity": {"type": "string"}
      }
    }
  },
  "log_samples": {
    "type": "object",
    "description": "Sample log entries from each service"
  },
  "recommendations": {
    "type": "array",
    "items": {"type": "string"}
  }
}
```

## Process

### 1. Discover aitbc-* Services
```bash
# Get list of all aitbc-* services on each node
echo "=== aitbc services ==="
systemctl list-units --all | grep "aitbc-"

echo "=== aitbc1 services ==="
ssh aitbc1 'systemctl list-units --all | grep "aitbc-"'

echo "=== gitea-runner services ==="
ssh gitea-runner 'systemctl list-units --all | grep "aitbc-"'
```

### 2. Start Journalctl Monitoring (Real-time)
```bash
# Monitor all aitbc-* services on each node in parallel
journalctl -f -u "aitbc-*" --no-pager > /tmp/aitbc-journalctl.log 2>&1 &
JOURNALCTL_PID=$!

ssh aitbc1 'journalctl -f -u "aitbc-*" --no-pager' > /tmp/aitbc1-journalctl.log 2>&1 &
AITBC1_PID=$!

ssh gitea-runner 'journalctl -f -u "aitbc-*" --no-pager' > /tmp/gitea-runner-journalctl.log 2>&1 &
GITEA_RUNNER_PID=$!
```

### 3. Monitor Application Logfiles
```bash
# Monitor /var/log/aitbc/ logfiles on each node
tail -f /var/log/aitbc/*.log > /tmp/aitbc-applogs.log 2>&1 &
APPLOGS_PID=$!

ssh aitbc1 'tail -f /var/log/aitbc/*.log' > /tmp/aitbc1-applogs.log 2>&1 &
AITBC1_APPLOGS_PID=$!

ssh gitea-runner 'tail -f /var/log/aitbc/*.log' > /tmp/gitea-runner-applogs.log 2>&1 &
GITEA_RUNNER_APPLOGS_PID=$!
```

### 4. Error Detection and Alerting
```bash
# Monitor logs for error keywords
tail -f /tmp/aitbc-journalctl.log | grep -E --line-buffered "(ERROR|CRITICAL|FAILED|exception)" | while read line; do
    echo "[ALERT] aitbc: $line"
    # Increment error counter
    # Trigger alert if threshold exceeded
done &

tail -f /tmp/aitbc1-journalctl.log | grep -E --line-buffered "(ERROR|CRITICAL|FAILED|exception)" | while read line; do
    echo "[ALERT] aitbc1: $line"
done &

tail -f /tmp/gitea-runner-journalctl.log | grep -E --line-buffered "(ERROR|CRITICAL|FAILED|exception)" | while read line; do
    echo "[ALERT] gitea-runner: $line"
done &
```

### 5. Cross-Node Log Correlation
```bash
# Correlate events across nodes by timestamp
# Example: detect if a service fails on all nodes simultaneously
# Check for common error patterns across nodes
# Identify propagation of errors from one node to another
```

### 6. Historical Log Analysis (if requested)
```bash
# Analyze recent logs for patterns
journalctl -u "aitbc-*" --since "1 hour ago" --no-pager | grep -E "(ERROR|CRITICAL|FAILED)"
ssh aitbc1 'journalctl -u "aitbc-*" --since "1 hour ago" --no-pager' | grep -E "(ERROR|CRITICAL|FAILED)"
ssh gitea-runner 'journalctl -u "aitbc-*" --since "1 hour ago" --no-pager' | grep -E "(ERROR|CRITICAL|FAILED)"
```

### 7. Stop Monitoring
```bash
# Kill background processes when monitoring duration expires
kill $JOURNALCTL_PID $AITBC1_PID $GITEA_RUNNER_PID
kill $APPLOGS_PID $AITBC1_APPLOGS_PID $GITEA_RUNNER_APPLOGS_PID
```

## Common aitbc-* Services

### Primary Services
- aitbc-blockchain-node.service - Main blockchain node
- aitbc-blockchain-p2p.service - P2P network service
- aitbc-blockchain-rpc.service - RPC API service
- aitbc-agent-daemon.service - Agent listener daemon
- aitbc-agent-coordinator.service - Agent coordinator
- aitbc-agent-registry.service - Agent registry

### Secondary Services
- aitbc-marketplace.service - Marketplace service
- aitbc-gpu-miner.service - GPU mining service
- aitbc-monitor.service - System monitoring

## Logfile Locations

### Application Logs
- /var/log/aitbc/blockchain-communication-test.log
- /var/log/aitbc/blockchain-test-errors.log
- /var/log/aitbc/training*.log
- /var/log/aitbc/service_monitoring.log
- /var/log/aitbc/service_alerts.log

### Service-Specific Logs
- /var/log/aitbc/blockchain-node/
- /var/log/aitbc/agent-coordinator/
- /var/log/aitbc/agent-registry/
- /var/log/aitbc/gpu-marketplace/

## Error Patterns to Monitor

### Critical Errors
- "FileNotFoundError" - Missing configuration or data files
- "Permission denied" - File permission issues
- "Connection refused" - Network connectivity issues
- "state root mismatch" - Blockchain state corruption
- "provided invalid or self node_id" - P2P identity conflicts

### Warning Patterns
- "Large sync gap" - Blockchain sync issues
- "Contract endpoints not available" - Service unavailability
- "Memory limit exceeded" - Resource exhaustion

## Constraints
- Maximum monitoring duration: 24 hours unless renewed
- Cannot monitor more than 50 concurrent log streams
- Alert threshold cannot be lower than 3 to avoid false positives
- Must preserve log integrity - cannot modify original logs
- Monitoring should not impact system performance significantly
- SSH connections must be established and working for remote nodes

## Environment Assumptions
- SSH access to aitbc1 and gitea-runner configured
- Log directory: /var/log/aitbc/
- Systemd services: aitbc-* pattern
- Journalctl available on all nodes
- Sufficient disk space for log buffering
- Network connectivity between nodes for cross-node correlation

## Error Handling

### SSH Connection Failure
- Log connection error
- Mark node as unavailable
- Continue monitoring other nodes
- Alert user about connectivity issue

### Service Not Found
- Skip missing services gracefully
- Log service not found warning
- Continue monitoring available services

### Log File Access Denied
- Log permission error
- Check file permissions
- Alert user if critical logs inaccessible

### Buffer Overflow
- Monitor log buffer size
- Rotate buffers if needed
- Alert if disk space insufficient

## Example Usage Prompts

### Basic Monitoring
"Monitor all aitbc-* services on all nodes in real-time mode."

### Error-Only Monitoring
"Monitor for errors only across aitbc and aitbc1 nodes."

### Specific Services
"Monitor aitbc-blockchain-node and aitbc-agent-daemon services on all nodes."

### Historical Analysis
"Analyze the last 2 hours of logs for errors across all nodes."

### Duration-Limited Monitoring
"Monitor all services for 30 minutes and report error summary."

### Custom Error Keywords
"Monitor for 'state root mismatch' and 'P2P handshake' errors across all nodes."

## Expected Output Example
```json
{
  "monitoring_status": "completed",
  "nodes_monitored": ["aitbc", "aitbc1", "gitea-runner"],
  "services_monitored": ["aitbc-blockchain-node.service", "aitbc-blockchain-p2p.service", "aitbc-agent-daemon.service"],
  "error_summary": {
    "total_errors": 12,
    "by_service": {
      "aitbc-blockchain-node.service": 5,
      "aitbc-agent-daemon.service": 7
    },
    "by_node": {
      "aitbc": 3,
      "aitbc1": 9,
      "gitea-runner": 0
    },
    "recent_errors": [
      {
        "timestamp": "2026-04-22T14:10:15",
        "node": "aitbc1",
        "service": "aitbc-agent-daemon.service",
        "message": "FileNotFoundError: /var/lib/aitbc/keystore/.agent_daemon_password",
        "severity": "CRITICAL"
      }
    ]
  },
  "alerts_triggered": [
    {
      "timestamp": "2026-04-22T14:10:15",
      "node": "aitbc1",
      "service": "aitbc-agent-daemon.service",
      "message": "Agent daemon service failed due to missing keystore file",
      "severity": "CRITICAL"
    }
  ],
  "log_samples": {
    "aitbc-blockchain-node.service": "Latest 10 log entries...",
    "aitbc-agent-daemon.service": "Latest 10 log entries..."
  },
  "recommendations": [
    "Check keystore directory on aitbc1",
    "Verify agent daemon service configuration",
    "Monitor for additional file permission errors"
  ]
}
```

## Model Routing
- **Fast Model**: Use for basic monitoring and error detection
- **Reasoning Model**: Use for complex log correlation, root cause analysis, cross-node pattern detection

## Performance Notes
- **Memory Usage**: ~100-200MB for log buffering
- **Network Impact**: Minimal for journalctl, moderate for log file tailing
- **CPU Usage**: Low for grep-based filtering, moderate for complex correlation
- **Disk Usage**: Temporary log buffers (~50-100MB per node)
- **Latency**: Near real-time for journalctl (~1-2s delay)

## Related Skills
- [blockchain-troubleshoot-recovery](/blockchain-troubleshoot-recovery.md) - For troubleshooting based on log findings
- [gitea-runner-log-debugger](/gitea-runner-log-debugger.md) - For CI-specific log debugging
- [aitbc-node-coordinator](/aitbc-node-coordinator.md) - For cross-node coordination during issues

## Related Workflows
- [AITBC System Architecture Audit](/workflows/aitbc-system-architecture-audit.md) - System-wide audit including log analysis
