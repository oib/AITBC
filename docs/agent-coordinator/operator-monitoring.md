# Agent Coordinator - Monitoring

**Last Updated**: 2026-06-30
**Version**: 1.0

## Health Checks

### Service Health

```bash
curl http://localhost:9001/health
```

**Expected response:**
```json
{
  "status": "healthy",
  "version": "1.0.0",
  "timestamp": "2026-05-07T16:00:00.000000+00:00"
}
```

### Task Distribution Stats

```bash
curl http://localhost:9001/tasks/status
```

### CLI Health Check

```bash
aitbc-cli ai status
```

## Service Status

### Check Systemd Service

```bash
systemctl status aitbc-agent-coordinator.service
```

### View Service Logs

```bash
journalctl -u aitbc-agent-coordinator.service -f
```

### View Recent Logs

```bash
journalctl -u aitbc-agent-coordinator.service -n 100
```

## Agent Monitoring

### List All Agents

```bash
aitbc-cli agent sdk list
```

### List Active Agents Only

```bash
aitbc-cli agent sdk list --status active
```

### Check Specific Agent

```bash
aitbc-cli agent sdk status --agent-id my-agent
```

### Monitor Distribution Stats

```bash
aitbc-cli ai distribution-stats
```

## Redis Monitoring

### Check Redis Connection

```bash
redis-cli ping
```

### View All Registered Agents

```bash
redis-cli
> KEYS agent:*
```

### View Active Agents

```bash
redis-cli
> SMEMBERS agents:active
```

### View Agent Details

```bash
redis-cli
> HGETALL agent:my-agent
```

### Monitor Redis Memory

```bash
redis-cli INFO memory
```

## Related Topics

- [Deployment](./operator-deployment.md) - Installation and service configuration
- [Registration](./operator-registration.md) - Agent registration procedures
- [Troubleshooting](./operator-troubleshooting.md) - Common issues and solutions
