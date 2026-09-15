# Agent Coordinator - Troubleshooting

**Last Updated**: 2026-06-30
**Version**: 1.0

## Common Issues and Solutions

### Service Won't Start

**Symptoms:**

```
Failed to start aitbc-agent-coordinator.service
```

**Solutions:**

1. Check Redis is running:

```bash
systemctl status redis
```

1. Check Redis connection:

```bash
redis-cli ping
```

1. Check service logs:

```bash
journalctl -u aitbc-agent-coordinator.service -n 50
```

1. Verify PYTHONPATH:

```bash
echo $PYTHONPATH
# Should include: /opt/aitbc/apps/agent-coordinator/src
```

### No Agents Discovered

**Symptoms:**

```bash
aitbc agent discover agents
Found 0 agents
```

**Solutions:**

1. Check if agents are registered:

```bash
redis-cli SMEMBERS agents:active
```

1. Register an agent:

```bash
aitbc agent create --name test-agent --type worker
aitbc agent register --agent-id test-agent
```

1. Check agent status:

```bash
aitbc agent status --agent-id test-agent
```

### Tasks Not Distributing

**Symptoms:**

- Tasks submitted but not assigned
- `tasks_distributed` count not increasing

**Solutions:**

1. Check for active agents:

```bash
aitbc agent discover agents
```

1. Check task distributor status:

```bash
curl http://localhost:8107/v1/tasks/status
```

1. Verify agent capabilities match task requirements
2. Check load balancer strategy
3. Review service logs for errors

### Agent Marked as Stale

**Symptoms:**

- Agent status changes from active to stale
- Agent not receiving new tasks

**Solutions:**

1. Update agent status:

```bash
aitbc agent register --agent-id my-agent  # re-register to refresh coordinator state
```

1. Check heartbeat mechanism (if implemented)
2. Verify agent is still running
3. Check network connectivity

### Redis Connection Errors

**Symptoms:**

```
Error connecting to Redis
```

**Solutions:**

1. Check Redis service:

```bash
systemctl status redis
```

1. Restart Redis:

```bash
systemctl restart redis
```

1. Check Redis configuration:

```bash
redis-cli INFO server
```

1. Verify Redis URL in environment:

```bash
echo $AITBC_REDIS_URL
```

## Troubleshooting Checklist

When issues occur, check in this order:

1. **Service status**
   - [ ] Service running?
   - [ ] Health check passing?
   - [ ] Logs showing errors?

2. **Redis status**
   - [ ] Redis running?
   - [ ] Connection successful?
   - [ ] Memory usage normal?

3. **Agent status**
   - [ ] Agents registered?
   - [ ] Agents active?
   - [ ] Agent capabilities valid?

4. **Task status**
   - [ ] Tasks submitting?
   - [ ] Tasks distributing?
   - [ ] Tasks completing?

5. **Network**
   - [ ] Connectivity to Redis?
   - [ ] Connectivity to agents?
   - [ ] Firewall rules correct?

6. **Configuration**
   - [ ] Environment variables set?
   - [ ] PYTHONPATH correct?
   - [ ] Port available?

## Related Topics

- [Deployment](./operator-deployment.md) - Installation and service configuration
- [Monitoring](./operator-monitoring.md) - Health checks and agent monitoring
- [Performance Tuning](./operator-performance.md) - Load balancing and resource limits
