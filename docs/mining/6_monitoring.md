# Monitoring & Alerts

Monitor your miner performance and set up alerts.

## Real-time Monitoring

### Dashboard

```bash
aitbc monitor dashboard
```

Shows:

- GPU utilization
- Memory usage
- Temperature
- Active jobs

### CLI Stats

```bash
# Mining loop status
aitbc mining status

# Coordinator-side job statistics
aitbc ai stats

# Local GPU inventory
aitbc gpu list-gpus
```

### Metrics

```bash
# Query recent platform metrics
aitbc monitor metrics --period 1h
aitbc monitor metrics --period 24h --export /tmp/metrics.json
```

## Alert Configuration

### Set Alerts

```bash
# Miner offline alert
aitbc monitor alerts add --name miner-offline --type miner_offline --threshold 90

# Failed job alert
aitbc monitor alerts add --name job-failures --type job_failed --threshold 3

# Low balance alert
aitbc monitor alerts add --name low-balance --type low_balance --threshold 10
```

### Alert Types

| Type | Description |
|------|-------------|
| coordinator_down | Coordinator unreachable |
| miner_offline | Miner stopped responding |
| job_failed | Job failure rate |
| low_balance | Wallet balance below threshold |

### Manage Alerts

```bash
# List configured alerts
aitbc monitor alerts list

# Remove an alert
aitbc monitor alerts remove --name miner-offline

# Send a test alert
aitbc monitor alerts test --name miner-offline
```

GPU temperature/memory thresholds are enforced by the NVIDIA driver and
`nvidia-smi`; platform alerts cover service and job health.

## Log Management

### View Logs

Miner logs are journald logs for the `aitbc-miner` service:

```bash
# Recent logs
journalctl -u aitbc-miner -n 100

# Follow live
journalctl -u aitbc-miner -f

# Filter by priority (errors)
journalctl -u aitbc-miner -p err
```

### Log Rotation

Log rotation is handled by journald (`SystemMaxUse` in
`/etc/systemd/journald.conf`).

## Health Checks

```bash
# Service health
systemctl status aitbc-miner

# Mining status via the node RPC
aitbc mining status

# Coordinator reachability and service health
aitbc system check
```

Shows:

- Service state (active/failed)
- GPU health via `nvidia-smi`
- Network connectivity

## Next
