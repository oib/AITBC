# Blockchain Node Observability

This directory contains Prometheus-only assets for the devnet environment. Grafana is not used in production or staging because the operational workflow is agent-first: metrics are queried via the Prometheus API, alerts are evaluated by Prometheus, and investigations start with logs and health endpoints.

## Stack

The blockchain RPC exposes `/metrics` (see `apps/blockchain-node/src/aitbc_chain/app.py`). That endpoint merges:

1. `prometheus_client` metrics defined in `apps/blockchain-node/src/aitbc_chain/metrics.py`.
2. The legacy `MetricsRegistry` render from `aitbc_chain.metrics` (gossip subscriber counts, queue sizes, etc.).

Prometheus scrapes this endpoint on a configurable interval.

## Files

- `prometheus.yml` – Sample scrape config for the devnet blockchain node and a mock coordinator/miner.
- `alerts.yml` – Example alert rules for block production, miner errors, coordinator receipts and RPC errors.
- `gossip-recording-rules.yml` – Recording rules that derive queue/subscriber gauges and publication rates from gossip metrics.

## Usage

```bash
# Launch Prometheus with the sample config
prometheus --config.file=apps/blockchain-node/observability/prometheus.yml

# Or on a live node, reload the running Prometheus service
sudo systemctl reload prometheus
```

## Gossip observability

Recent updates instrumented the gossip broker with Prometheus counters and gauges. Key metrics surfaced via the recording rules and alert rules include:

- `gossip_publications_rate_per_sec` and `gossip_broadcast_publications_rate_per_sec` – per-second publication throughput for in-memory and broadcast backends.
- `gossip_publications_topic_rate_per_sec` – topic-level publication rate time series.
- `gossip_queue_size_by_topic` – instantaneous queue depth per topic.
- `gossip_subscribers_by_topic`, `gossip_subscribers_total`, `gossip_broadcast_subscribers_total` – subscriber counts.

These are also merged into the `/metrics` response so a central Prometheus on `aitbc3` can scrape them.
