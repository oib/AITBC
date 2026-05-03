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

## Coordinator API Metrics

The coordinator API now exposes a JSON metrics endpoint for dashboard consumption in addition to the Prometheus `/metrics` endpoint.

### Live JSON Metrics

```bash
curl http://localhost:8000/v1/metrics
```

Includes:
- API request and error counters
- Average API response time
- Cache hit/miss and hit-rate data
- Lightweight process memory and CPU snapshot
- Alert threshold evaluation state
- Alert delivery result metadata

### Dashboard Flow

The web dashboard at `/opt/aitbc/website/dashboards/metrics.html` consumes:
- `GET /v1/metrics` for live JSON metrics
- `GET /v1/health` for API health-state checks
- `GET /metrics` for Prometheus-compatible scraping

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

## Coordinator Metrics Verification

### Verify JSON Metrics Endpoint

```bash
# Check live JSON metrics for dashboard consumption
curl http://localhost:8000/v1/metrics | jq
```

Expected fields:
- `api_requests` - Total API request count
- `api_errors` - Total API error count
- `error_rate_percent` - Calculated error rate percentage
- `avg_response_time_ms` - Average API response time
- `cache_hit_rate_percent` - Cache hit rate percentage
- `alerts` - Alert threshold evaluation states
- `alert_delivery` - Alert delivery result metadata
- `uptime_seconds` - Service uptime in seconds

### Verify Prometheus Metrics

```bash
# Check Prometheus-compatible metrics
curl http://localhost:8000/metrics
```

### Verify Alert History

```bash
# Get recent production alerts (requires admin key)
curl -H "X-API-Key: your-admin-key" \
  "http://localhost:8000/agents/integration/production/alerts?limit=10" | jq
```

Filter by severity:
```bash
curl -H "X-API-Key: your-admin-key" \
  "http://localhost:8000/agents/integration/production/alerts?severity=critical" | jq
```

### Verify Dashboard Access

```bash
# Open the metrics dashboard in a browser
# File location: /opt/aitbc/website/dashboards/metrics.html
```

The dashboard polls:
- `GET /v1/metrics` for live JSON metrics
- `GET /v1/health` for API health-state checks
- `GET /metrics` for Prometheus-compatible scraping

## Troubleshooting

### Metrics Not Updating

If `/v1/metrics` shows stale or zeroed metrics:

1. **Check middleware is active**
   - Verify request metrics middleware is registered in `app/main.py`
   - Check that `metrics_collector` is imported and used

2. **Check cache stats integration**
   - Verify `cache_manager.get_stats()` is called in the metrics endpoint
   - Check that cache manager is properly initialized

3. **Check system snapshot capture**
   - Verify `capture_system_snapshot()` is not raising exceptions
   - Check that `os.getloadavg()` and `resource` module are available on your platform

### Alert Delivery Not Working

If alerts are not being delivered:

1. **Check webhook configuration**
   - Verify `AITBC_ALERT_WEBHOOK_URL` environment variable is set
   - Test webhook URL with a simple curl POST request
   - Check webhook server logs for incoming requests

2. **Check alert suppression**
   - Alert dispatcher uses 5-minute cooldown by default
   - Check if alerts are being suppressed due to recent deliveries
   - Verify cooldown logic in `alert_dispatcher._is_suppressed()`

3. **Check alert history**
   - Use `/agents/integration/production/alerts` to see recent alert attempts
   - Check `delivery_status` field: `sent`, `suppressed`, or `failed`
   - Check `error` field for failed deliveries

4. **Check log fallback**
   - If webhook URL is not configured, alerts fall back to log output
   - Check coordinator API logs for warning messages about alerts

### Dashboard Not Loading

If the metrics dashboard is not displaying data:

1. **Check API endpoints are accessible**
   - Verify `/v1/metrics` returns valid JSON
   - Verify `/v1/health` returns healthy status
   - Check browser console for CORS or network errors

2. **Check dashboard file path**
   - Ensure dashboard is served from correct location
   - Verify static file serving is configured in web server

3. **Check browser console**
   - Look for JavaScript errors
   - Check for failed API requests
   - Verify polling interval is reasonable (default 5 seconds)

### Alert Thresholds Not Triggering

If alerts should trigger but do not:

1. **Verify threshold values**
   - Error rate threshold: 1%
   - Average response time threshold: 500ms
   - Memory usage threshold: 90%
   - Cache hit rate threshold: 70%

2. **Check metrics calculation**
   - Verify metrics are being collected correctly
   - Check that response times are recorded in seconds (not milliseconds)
   - Verify cache hit rate calculation includes both hits and misses

3. **Check alert evaluation logic**
   - Verify `get_alert_states()` is called during metrics collection
   - Check that alert states are included in `/v1/metrics` response

## Next

- [Quick Start](./1_quick-start.md) — Get started
- [Configuration](./2_configuration.md) - Configure your node
- [Operations](./3_operations.md) — Day-to-day ops
