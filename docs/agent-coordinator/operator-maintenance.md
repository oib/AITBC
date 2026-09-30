# Agent Coordinator - Maintenance

**Last Updated**: 2026-06-30
**Version**: 1.0

## Regular Maintenance Tasks

### Daily

- Monitor service health
- Check task distribution stats
- Review error logs

### Weekly

- Backup Redis data
- Review agent registrations
- Clean up stale agents

### Monthly

- Review performance metrics
- Update software dependencies
- Audit security configurations

## Agent Cleanup

### Remove Inactive Agents

```bash
# No `agents:active`/`agent:*` Redis layout exists — agents are marked
# via the status endpoint (there is no delete endpoint):
curl -X PUT http://localhost:8107/v1/agents/stale-agent-id/status   -H 'content-type: application/json' -d '{"status": "inactive"}'
```

### Bulk Cleanup Script

```bash
#!/bin/bash
# cleanup_stale_agents.sh — mark stale agents inactive via the API.
# (No agent keys are stored in Redis; direct redis-cli surgery does not
# apply to this service.)
curl -s -X POST http://localhost:8107/v1/agents/discover   -H 'content-type: application/json' -d '{}' | jq -r '.agents[]? | select(.status=="stale") | .agent_id' | while read -r agent_id; do
    curl -s -X PUT "http://localhost:8107/v1/agents/$agent_id/status"       -H 'content-type: application/json' -d '{"status": "inactive"}'
    echo "Marked stale agent inactive: $agent_id"
  done
```

## Service Restart

### Graceful Restart

```bash
systemctl reload aitbc-agent-coordinator.service
```

### Force Restart

```bash
systemctl restart aitbc-agent-coordinator.service
```

### Rolling Restart (Multiple Instances)

```bash
for i in {1..3}; do
  systemctl restart aitbc-agent-coordinator.service (no template unit exists — single instance only)
  sleep 10
done
```

## Related Topics

- [Deployment](./operator-deployment.md) - Installation and service configuration
- [Backup and Recovery](./operator-backup.md) - Redis backup and service configuration backup
- [Monitoring](./operator-monitoring.md) - Health checks and agent monitoring

> Auth note: `/v1/agents/{id}/status` requires an authorized principal (agent-scoped credential or admin) — see `API.md`/`docs/security/agent-signed-envelopes.md` for the credential format.
