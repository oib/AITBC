# AITBC Performance Monitoring Setup

## Overview

This document describes the AITBC monitoring stack. It is **agent-first**: metrics are stored as time series in Prometheus, anomalies are exposed as alert rules and structured log events, and any rendering layer is optional. Grafana is not part of the stack because the operational evidence comes from `journalctl`, `curl /health`, `redis-cli` and source-level queries rather than dashboards.

## Monitoring Infrastructure

### Components

1. **Prometheus** - Metrics collection, storage, evaluation and alerting (systemd service).
2. **Node Exporter** - System-level metrics (installed as `prometheus-node-exporter`).
3. **Custom Metrics Exporters** - Application-specific `/metrics` endpoints served by AITBC services.
4. **Alertmanager** (optional) - Routes firing alerts to a webhook, log file, or external system.

### Why no Grafana?

Grafana is a human-facing rendering layer. None of the live incident investigations in this project have used a dashboard; they used the Prometheus query API, service logs and health endpoints. Keeping Grafana running consumes memory and package maintenance cycles for no operational benefit. If a human-on-call rotation is added later, dashboards can be reintroduced, but the metrics substrate does not depend on them.

## Prometheus-first metrics

### Core AITBC metrics

The blockchain node main process exposes `/metrics` on `AITBC_NODE_METRICS_PORT` (default `9009`). The RPC process and the coordinator API also expose `/metrics` (or `/prometheus`) on their normal ports. Key series to watch:

- `blockchain_block_height` - current block height.
- `blockchain_poa_valid_subscribers{chain_id}` - number of valid subscribers at block broadcast time.
- `blockchain_poa_broadcast_skipped_total{chain_id}` - blocks skipped because no subscribers were present.
- `blockchain_block_processing_duration_seconds` - block processing latency histogram.
- `blockchain_transactions_total{status}` - transaction outcomes.
- `blockchain_rpc_request_duration_seconds` / `blockchain_rpc_requests_total{method,status}` - RPC latency and errors.
- `gossip_subscribers_total`, `gossip_subscribers_topic_*`, `gossip_broadcast_subscribers_total` - in-memory and broadcast subscriber counts.
- `gossip_publications_rate_per_sec`, `gossip_queue_size_by_topic` - gossip throughput and back-pressure.

### Application-specific metrics

Coordinate with each service's metrics endpoint:

- `coordinator_jobs_submitted_total`, `coordinator_jobs_completed_total`, `coordinator_jobs_failed_total`
- `jobs_in_queue`, `miner_active_jobs`, `miner_error_rate`
- `poolhub_miners_online`

## Alert rules

Store rules in `/etc/prometheus/aitbc_rules.yml` and load them from `prometheus.yml`.

```yaml
groups:
  - name: aitbc
    rules:
      - alert: BlockProposedButNoSubscribers
        expr: |
          (
            blockchain_poa_valid_subscribers == 0
            and on() (increase(blockchain_poa_broadcast_skipped_total[1m]) > 0)
          )
        for: 1m
        labels:
          severity: critical
        annotations:
          summary: "Block {{ $labels.chain_id }} produced but has zero valid subscribers"
          description: "Proposer is producing blocks on {{ $labels.chain_id }} but no follower is subscribed; blocks are not being broadcast."

      - alert: BroadcastSkipped
        expr: increase(blockchain_poa_broadcast_skipped_total[5m]) > 0
        for: 1m
        labels:
          severity: warning
        annotations:
          summary: "Blocks are being skipped on {{ $labels.chain_id }} due to no subscribers"

      - alert: ServiceDown
        expr: up == 0
        for: 1m
        labels:
          severity: critical
        annotations:
          summary: "Service {{ $labels.instance }} is down"

      - alert: BlockProcessingTooSlow
        expr: histogram_quantile(0.95, rate(blockchain_block_processing_duration_seconds_bucket[5m])) > 1
        for: 5m
        labels:
          severity: warning
        annotations:
          summary: "Block processing p95 exceeds 1 second"

      - alert: RpcErrorsSpiking
        expr: rate(blockchain_rpc_requests_total{status=~"4xx|5xx"}[5m]) > 0.05
        for: 5m
        labels:
          severity: warning
        annotations:
          summary: "RPC error rate is spiking"
```

## Scrape configuration

`/etc/prometheus/prometheus.yml` should scrape all live nodes. On `aitbc3` (which has more resources than `hub`), Prometheus can pull from both the shop and the hub:

```yaml
global:
  scrape_interval: 15s
  evaluation_interval: 15s

alerting:
  alertmanagers:
    - static_configs:
        - targets: ['localhost:9093']

rule_files:
  - aitbc_rules.yml

scrape_configs:
  - job_name: 'prometheus'
    static_configs:
      - targets: ['localhost:9090']

  - job_name: 'node-exporter-local'
    static_configs:
      - targets: ['localhost:9100']

  # Blockchain node main process metrics (chain height, subscribers, broadcast skipped)
  - job_name: 'aitbc3-blockchain-node'
    static_configs:
      - targets: ['localhost:9009']
        labels:
          node: aitbc3
          service: blockchain-node

  - job_name: 'aitbc3-blockchain-rpc'
    static_configs:
      - targets: ['localhost:8202']
        labels:
          node: aitbc3
          service: blockchain-rpc

  - job_name: 'aitbc3-coordinator-api'
    static_configs:
      - targets: ['localhost:8203']
        labels:
          node: aitbc3
          service: coordinator-api

  - job_name: 'aitbc3-marketplace'
    static_configs:
      - targets: ['localhost:8104']
        labels:
          node: aitbc3
          service: marketplace

  - job_name: 'hub-blockchain-node'
    static_configs:
      - targets: ['hub.aitbc.bubuit.net:9009']
        labels:
          node: hub
          service: blockchain-node

  - job_name: 'hub-blockchain-rpc'
    static_configs:
      - targets: ['hub.aitbc.bubuit.net:8202']
        labels:
          node: hub
          service: blockchain-rpc

  - job_name: 'hub-coordinator-api'
    static_configs:
      - targets: ['hub.aitbc.bubuit.net:8203']
        labels:
          node: hub
          service: coordinator-api
```

## Making Prometheus more useful on aitbc3

Since `aitbc3` has more hardware than `hub`:

1. **Centralise scraping there.** Point Prometheus at both `aitbc3` and `hub` so one place holds the full network view.
2. **Add recording rules** for expensive queries used in alerts and ad-hoc investigation:
   ```yaml
   - record: aitbc:block_interval_seconds:rate5m
     expr: 60 / rate(blockchain_block_height[5m])
   ```
3. **Expose process and chain metrics.** The blockchain node main process now serves `/metrics` on port `9009` via `AITBC_NODE_METRICS_PORT` and exports chain height, valid subscriber counts and broadcast-skip counters.
4. **Promote operational log lines.** `BROADCAST SKIPPED` and similar events are now logged at `WARNING` and counted in `blockchain_poa_broadcast_skipped_total` so an agent sees both the event and the metric.
5. **Run `prometheus-node-exporter` on every node.** System metrics are cheap and make it easy to distinguish code bugs from resource exhaustion.
6. **Keep retention aligned with disk.** With 523M of history, check `node_filesystem_avail_bytes` and set `--storage.tsdb.retention.size` accordingly.
7. **Use the Prometheus expression API for checks.** Example:
   ```bash
   curl -s 'http://localhost:9090/api/v1/query?query=blockchain_poa_valid_subscribers'
   ```

## Installation

### Debian stable

```bash
sudo apt update
sudo apt install prometheus prometheus-node-exporter
```

If you want Alertmanager:

```bash
sudo apt install prometheus-alertmanager
```

### Systemd

```bash
sudo systemctl enable --now prometheus
sudo systemctl enable --now prometheus-node-exporter
```

### Reload after config changes

```bash
sudo promtool check config /etc/prometheus/prometheus.yml
sudo promtool check rules /etc/prometheus/aitbc_rules.yml
sudo systemctl reload prometheus
# or, if the service does not pick up the new config:
sudo systemctl restart prometheus
```

## Testing

### Verify a metrics endpoint

```bash
curl -s http://localhost:8202/metrics | grep blockchain_poa_valid_subscribers
curl -s http://localhost:8203/prometheus | head
```

### Verify Prometheus targets

```bash
curl -s http://localhost:9090/api/v1/targets
curl -s http://localhost:9090/api/v1/rules
```

## Maintenance

### Regular tasks

1. Review firing and pending alerts.
2. Check retention and disk usage.
3. Verify all scrape targets are healthy.
4. Add recording rules for any query that becomes slow.

### Backup

```bash
# Prometheus data
sudo tar -czf /tmp/prometheus-backup.tar.gz /var/lib/prometheus
```

### Troubleshooting

| Symptom | Check |
|---------|-------|
| Metrics not appearing | `systemctl status prometheus`; `curl` the service `/metrics` endpoint. |
| High memory usage | Reduce scrape interval or retention; check for high-cardinality labels. |
| Alerts not firing | `promtool check rules` and `curl http://localhost:9090/api/v1/alerts`. |
| No subscribers alert | Verify gossip/Redis lease state; check `blockchain_poa_valid_subscribers`. |
