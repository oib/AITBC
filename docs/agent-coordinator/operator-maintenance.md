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
redis-cli
> SREM agents:active "stale-agent-id"
> DEL agent:stale-agent-id
```

### Bulk Cleanup Script

```bash
#!/bin/bash
# cleanup_stale_agents.sh
redis-cli --scan --pattern "agent:*" | while read key; do
  status=$(redis-cli HGET "$key" status)
  if [ "$status" = "stale" ]; then
    agent_id=$(echo "$key" | cut -d: -f2)
    redis-cli SREM agents:active "$agent_id"
    redis-cli DEL "$key"
    echo "Removed stale agent: $agent_id"
  fi
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
  systemctl restart aitbc-agent-coordinator@$i.service
  sleep 10
done
```

## Related Topics

- [Deployment](./operator-deployment.md) - Installation and service configuration
- [Backup and Recovery](./operator-backup.md) - Redis backup and service configuration backup
- [Monitoring](./operator-monitoring.md) - Health checks and agent monitoring
