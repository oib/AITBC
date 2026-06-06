# Monitoring & Alerts
Monitor your miner performance and set up alerts.

## Real-time Monitoring

### Dashboard

```bash
aitbc miner dashboard
```

Shows:
- GPU utilization
- Memory usage
- Temperature
- Active jobs
- Earnings rate

### CLI Stats

```bash
aitbc miner stats
```

### Prometheus Metrics

```bash
# Enable metrics endpoint
aitbc miner metrics --port 9090
```

Available at: http://localhost:9090/metrics

## Alert Configuration

### Set Alerts

```bash
# GPU temperature alert
aitbc miner alert --metric temp --threshold 85 --action notify

# Memory usage alert
aitbc miner alert --metric memory --threshold 90 --action throttle

# Job failure alert
aitbc miner alert --metric failures --threshold 3 --action pause
```

### Alert Types

| Type | Description |
|------|-------------|
| temp | GPU temperature |
| memory | GPU memory usage |
| utilization | GPU utilization |
| jobs | Job success/failure rate |
| earnings | Earnings below threshold |

### Alert Actions

| Action | Description |
|--------|-------------|
| notify | Send notification |
| throttle | Reduce job acceptance |
| pause | Stop accepting jobs |
| restart | Restart miner |

## Log Management

### View Logs

```bash
# Recent logs
aitbc miner logs --tail 100

# Filter by level
aitbc miner logs --level error

# Filter by job
aitbc miner logs --job-id <JOB_ID>
```

### Log Rotation

```bash
# Configure log rotation
aitbc miner logs --rotate --max-size 100MB --keep 5
```

## Health Checks

```bash
# Run health check
aitbc miner health

# Detailed health report
aitbc miner health --detailed
```

Shows:
- GPU health
- Driver status
- Network connectivity
- Storage availability

## Next

- [Quick Start](./1_quick-start.md) — Get started
- [GPU Setup](./5_gpu-setup.md) — GPU configuration
- [Job Management](./3_job-management.md) — Job management
