# Agent Coordinator - Performance Tuning

**Last Updated**: 2026-06-30
**Version**: 1.0

## Load Balancing Strategies

**Current default:** `LEAST_CONNECTIONS`

### Available Strategies

- `LEAST_CONNECTIONS` - Fewest active connections
- `ROUND_ROBIN` - Circular distribution
- `WEIGHTED_ROUND_ROBIN` - Performance-based
- `RESOURCE_BASED` - CPU/memory metrics
- `GEOGRAPHIC` - Location-based
- `RANDOM` - Random selection (testing)

### Changing Strategy

Requires code modification in `lifespan.py`.

## Priority Queue Configuration

### Priority Levels

1. urgent
2. critical
3. high
4. normal
5. low

### Queue Sizing

Configured in `TaskDistributor` class.

### Monitoring Queue Sizes

```bash
curl http://localhost:9001/tasks/status | jq .stats.queue_sizes
```

## Resource Limits

### Redis Memory Limits

```bash
redis-cli CONFIG SET maxmemory 1gb
redis-cli CONFIG SET maxmemory-policy allkeys-lru
```

### Service Memory Limits

Configure in systemd service file:
```
MemoryLimit=2G
MemorySwap=2G
```

### Connection Limits

Configure in uvicorn startup:
```
--limit-concurrency 100
```

## Related Topics

- [Deployment](./operator-deployment.md) - Installation and service configuration
- [Monitoring](./operator-monitoring.md) - Health checks and agent monitoring
- [Troubleshooting](./operator-troubleshooting.md) - Common issues and solutions
