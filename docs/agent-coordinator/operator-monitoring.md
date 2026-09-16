# Agent Coordinator - Monitoring

**Last Updated**: 2026-06-30
**Version**: 1.0

## Health Checks

### Service Health

```bash
curl http://localhost:8107/health
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
curl http://localhost:8107/v1/tasks/status
```

### CLI Health Check

```bash
aitbc ai stats
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

### List Local Agents

```bash
aitbc agent list
```

### List Coordinator-Registered Agents

```bash
aitbc agent discover agents
```

### Filter Agents by Type or Capability

```bash
aitbc agent discover agents --agent-type provider --min-health 0.5
```

### Check Specific Agent

```bash
aitbc agent status --agent-id my-agent
```

### Monitor Distribution Stats

> **Note:** `aitbc ai distribution-stats` calls `GET /v1/agent/stats/distribution`
> on the coordinator-api, a route that does not exist — the command currently
> returns 404. Agent distribution data is available via the agent-coordinator
> list endpoint (`GET /api/v1/agent/agents`) or `aitbc agent list`.

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
