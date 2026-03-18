# Node Monitoring
Monitor your blockchain node performance and health.

## Dashboard

```bash
aitbc-chain dashboard
```

Shows:
- Block height
- Peers connected
- Mempool size
- CPU/Memory/GPU usage
- Network traffic

## Prometheus Metrics

```bash
# Enable metrics
aitbc-chain metrics --port 9090
```

Available metrics:
- `aitbc_block_height` - Current block height
- `aitbc_peers_count` - Number of connected peers
- `aitbc_mempool_size` - Transactions in mempool
- `aitbc_block_production_time` - Block production time
- `aitbc_cpu_usage` - CPU utilization
- `aitbc_memory_usage` - Memory utilization

## Alert Configuration

### Set Alerts

```bash
# Low peers alert
aitbc-chain alert --metric peers --threshold 3 --action notify

# High mempool alert
aitbc-chain alert --metric mempool --threshold 5000 --action notify

# Sync delay alert
aitbc-chain alert --metric sync_delay --threshold 100 --action notify
```

### Alert Actions

| Action | Description |
|--------|-------------|
| notify | Send notification |
| restart | Restart node |
| pause | Pause block production |

## Log Monitoring

```bash
# Real-time logs
aitbc-chain logs --tail

# Search logs
aitbc-chain logs --grep "error" --since "1h"

# Export logs
aitbc-chain logs --export /var/log/aitbc-chain/
```

## Health Checks

```bash
# Run health check
aitbc-chain health

# Detailed report
aitbc-chain health --detailed
```

Checks:
- Disk space
- Memory
- P2P connectivity
- RPC availability
- Database sync

## Next

- [Quick Start](./1_quick-start.md) — Get started
- [Configuration](./2_configuration.md) - Configure your node
- [Operations](./3_operations.md) — Day-to-day ops
