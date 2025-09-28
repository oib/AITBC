# Blockchain Node Observability

This directory contains Prometheus and Grafana assets for the devnet environment. The stack relies on the HTTP `/metrics` endpoint exposed by:

1. The blockchain node API (`http://127.0.0.1:8080/metrics`).
2. The mock coordinator/miner exporter (`http://127.0.0.1:8090/metrics`).

## Files

- `prometheus.yml` – Scrapes both blockchain node and mock coordinator/miner metrics.
- `grafana-dashboard.json` – Panels for block interval, RPC throughput, miner activity, coordinator receipt flow, **plus new gossip queue, subscriber, and publication rate panels**.
- `alerts.yml` – Alertmanager rules highlighting proposer stalls, miner errors, and coordinator receipt drop-offs.
- `gossip-recording-rules.yml` – Prometheus recording rules that derive queue/subscriber gauges and publication rates from gossip metrics.

## Usage

```bash
# Launch Prometheus using the sample config
prometheus --config.file=apps/blockchain-node/observability/prometheus.yml

# Import the dashboard JSON into Grafana
grafana-cli dashboards import apps/blockchain-node/observability/grafana-dashboard.json

# Run Alertmanager with the example rules
alertmanager --config.file=apps/blockchain-node/observability/alerts.yml

# Reload Prometheus and Alertmanager after tuning thresholds
kill -HUP $(pgrep prometheus)
kill -HUP $(pgrep alertmanager)
```

> **Tip:** The devnet helper `scripts/devnet_up.sh` seeds the metrics endpoints. After running it, both scrape targets will begin emitting data in under a minute.

## Gossip Observability

Recent updates instrumented the gossip broker with Prometheus counters and gauges. Key metrics surfaced via the recording rules and dashboard include:

- `gossip_publications_rate_per_sec` and `gossip_broadcast_publications_rate_per_sec` – per-second publication throughput for in-memory and broadcast backends.
- `gossip_publications_topic_rate_per_sec` – topic-level publication rate time series (Grafana panel “Gossip Publication Rate by Topic”).
- `gossip_queue_size_by_topic` – instantaneous queue depth per topic (“Gossip Queue Depth by Topic”).
- `gossip_subscribers_by_topic`, `gossip_subscribers_total`, `gossip_broadcast_subscribers_total` – subscriber counts (“Gossip Subscriber Counts”).

Use these panels to monitor convergence/back-pressure during load tests (for example with `scripts/ws_load_test.py`) when running against a Redis-backed broadcast backend.
