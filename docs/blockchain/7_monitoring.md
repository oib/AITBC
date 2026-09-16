# Node Monitoring

**Last Updated:** 2026-09-16

Monitor your blockchain node's performance and health.

There is no `aitbc-chain dashboard`/`metrics`/`alert` command. Monitoring is
built from three pieces: **journald logs**, **`/metrics` endpoints**, and the
**`aitbc blockchain` CLI**.

## Quick Checks

```bash
# Chain status, height, and per-chain sync state
aitbc blockchain status
aitbc blockchain height
aitbc blockchain sync-status

# Live chain monitor (snapshot or realtime view)
aitbc blockchain monitor --chain-id ait-hub.aitbc.bubuit.net
aitbc blockchain monitor --chain-id ait-hub.aitbc.bubuit.net --realtime --interval 10

# Node service status
systemctl status aitbc-blockchain-node aitbc-blockchain-rpc
```

## Logs

All blockchain units log to journald — there is no `~/.aitbc/logs` directory:

```bash
# Follow node logs
journalctl -u aitbc-blockchain-node -f

# RPC service logs
journalctl -u aitbc-blockchain-rpc -f

# Hub gossip relay (hub only)
journalctl -u aitbc-blockchain-p2p -f

# Errors from the last hour across the stack
journalctl -u 'aitbc-blockchain-*' --since "1 hour ago" -p err
```

The node also writes a rotating file under `/var/log/aitbc/` (configured by
`aitbc_logging`), but journald is the primary source.

## Prometheus Metrics

### Blockchain node

The node process (`aitbc-blockchain-node`) serves Prometheus metrics on its
own port:

```bash
# AITBC_NODE_METRICS_PORT, default 9009
curl -s http://localhost:9009/metrics
```

The RPC app (`aitbc-blockchain-rpc`, port 8202) also exposes metrics and
health on its own listener:

```bash
curl -s http://localhost:8202/metrics   # Prometheus text exposition
curl -s http://localhost:8202/health    # {status, supported_chains, proposer_id, node_wallet}
```

Available metric families include `rpc_requests_total`,
`rpc_request_duration_seconds`, `rpc_get_head_*`, `rpc_get_block_*`,
`rpc_rate_limited_total`, plus the default process metrics.

### Coordinator API

The coordinator (port 8203) exposes, **at root — no `/v1` prefix**:

- `GET /metrics` — live **JSON** metrics for dashboard consumption
- `GET /prometheus` — Prometheus-compatible text exposition
- `GET /health`, `/health/live`, `/health/ready` — health and probes
- `GET /rate-limit-metrics` — rate limiting metrics
- `GET /v1/metrics` — a *different* payload: coordinator/job/miner/system
  counts used by the CLI monitor group

```bash
curl -s http://localhost:8203/metrics | jq
curl -s http://localhost:8203/prometheus | head
curl -s http://localhost:8203/health
```

`/metrics` includes:

- API request and error counters
- Average API response time
- Cache hit/miss and hit-rate data
- Lightweight process memory and CPU snapshot
- Alert threshold evaluation state
- Alert delivery result metadata

### Dashboard Flow

The web dashboard at `/opt/aitbc/website/dashboards/metrics.html` consumes:

- `GET /metrics` for live JSON metrics
- `GET /health` for API health-state checks
- `GET /prometheus` for Prometheus-compatible scraping

## Alerting

Alerts are dispatched by the coordinator's alert dispatcher — configured via
environment (`AITBC_ALERT_WEBHOOK_URL` for the webhook target), not a CLI
command. If no webhook is configured, alerts fall back to log output.

Alert history is served by the coordinator at
`/v1/agents/integration/production/alerts`.

> **Admin credentials required.** Every endpoint on that router carries
> `AdminDep`. The router was mounted on 2026-09-11; before that it was
> imported but never passed to `include_router()`, so the paths were absent
> from the OpenAPI schema entirely. Note that 8203 answers `401` for any
> unauthenticated request regardless of whether the path exists, so a `401`
> here is not evidence the route is mounted — check `/openapi.json`.

## Coordinator Metrics Verification

### Verify JSON Metrics Endpoint

```bash
# Check live JSON metrics for dashboard consumption (root path, not /v1)
curl -s http://localhost:8203/metrics | jq
```

Expected fields:

- `api_requests` — Total API request count
- `api_errors` — Total API error count
- `error_rate_percent` — Calculated error rate percentage
- `avg_response_time_ms` — Average API response time
- `cache_hit_rate_percent` — Cache hit rate percentage
- `alerts` — Alert threshold evaluation states
- `alert_delivery` — Alert delivery result metadata
- `uptime_seconds` — Service uptime in seconds

### Verify Prometheus Metrics

```bash
# Prometheus text exposition lives under /prometheus on the coordinator
curl -s http://localhost:8203/prometheus

# The blockchain RPC serves it at /metrics instead
curl -s http://localhost:8202/metrics
```

### Verify Dashboard Access

```bash
# Open the metrics dashboard in a browser
# File location: /opt/aitbc/website/dashboards/metrics.html
```

The dashboard polls:

- `GET /metrics` for live JSON metrics
- `GET /health` for API health-state checks
- `GET /prometheus` for Prometheus-compatible scraping

## Troubleshooting

### Metrics Not Updating

If `/metrics` shows stale or zeroed metrics:

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
   - Query `/v1/agents/integration/production/alerts` on 8203 (admin credentials required), or read `delivery_status` from the dispatcher logs
   - Check `delivery_status` field: `sent`, `suppressed`, or `failed`
   - Check `error` field for failed deliveries

4. **Check log fallback**
   - If webhook URL is not configured, alerts fall back to log output
   - Check coordinator API logs for warning messages about alerts

### Dashboard Not Loading

If the metrics dashboard is not displaying data:

1. **Check API endpoints are accessible**
   - Verify `/metrics` returns valid JSON
   - Verify `/health` returns healthy status
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
   - Check that alert states are included in `/metrics` response

## Next

- [Node Quick Start](../getting-started/node-quickstart.md) — Get started
- [Configuration](./2_configuration.md) - Configure your node
- [Operations](./3_operations.md) — Day-to-day ops
