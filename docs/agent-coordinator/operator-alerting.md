# Agent Coordinator - Alerting

**Last Updated**: 2026-06-30
**Version**: 1.0

## Recommended Alerts

### Service Alerts

- Service down (health check fails)
- High error rate (> 5%)
- High response time (> 5s)

### Agent Alerts

- No active agents
- Agent registration failures
- Agent stale count increasing

### Task Alerts

- Task queue backlog (> 100 tasks)
- Task failure rate (> 10%)
- Distribution time increasing

### Redis Alerts

- Redis connection failures
- Redis memory usage > 80%
- Redis latency > 100ms

## Monitoring Tools

### Prometheus Metrics

Future implementation:
- Export metrics at `/metrics` endpoint
- Use Grafana for visualization

### Log Aggregation

- Send logs to ELK stack
- Use Loki for log storage
- Configure alerting based on log patterns

## Related Topics

- [Monitoring](./operator-monitoring.md) - Health checks and agent monitoring
- [Performance Tuning](./operator-performance.md) - Load balancing and resource limits
- [Troubleshooting](./operator-troubleshooting.md) - Common issues and solutions
