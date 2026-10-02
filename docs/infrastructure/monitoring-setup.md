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

## CLI integration

The `aitbc prometheus` command lets operators query the local Prometheus instance without writing `curl`:

```bash
aitbc prometheus targets              # scrape target health
aitbc prometheus rules                # loaded recording/alert rules
aitbc prometheus alerts               # current firing/pending alerts
aitbc prometheus alerts --watch       # poll; emit alerts as they start firing and when they resolve (stdout/journal)
aitbc prometheus alerts --watch --alert-log /var/log/aitbc/alerts.log   # and keep them in a file of their own
aitbc prometheus alert-history          # replay that file: events + what is still firing
aitbc prometheus query "blockchain_block_height"
aitbc prometheus check                # promtool config + rules
```

`--prometheus-url` overrides the default `http://127.0.0.1:9090`, or set `prometheus_url` in `.aitbc.yaml`.

In watch mode, each alert state change is emitted as a single JSON line to stdout and also logged: `prometheus_alert_firing` when an alert starts firing (again, if it had resolved), `prometheus_alert_still_firing` when a reminder interval is set (see below), and `prometheus_alert_resolved`, with `duration_seconds`, when it stops. Every record carries `via` (`startup` when the watcher sees a firing alert on its first poll after (re)start, `transition` for a state change, `silence_expired` for an alert that left a silence while still firing, `reminder`), `timestamp` (naive UTC ISO) and `timestamp_unix` (epoch). A poll that Prometheus does not answer changes nothing, so an outage never reads as every alert resolving. With `--alert-log PATH` the same lines are also appended to PATH, rotated at 5 MiB with 5 backups. That file holds only these events plus the `prometheus_watch_started` marker the watcher writes once per (re)start, unlike the service log, which carries one httpx line per poll; if PATH cannot be written the watcher says so once and carries on with the journal and the service log.

A systemd unit is provided in `scripts/monitoring/aitbc-prometheus-watch.service`. Install it with:

```bash
sudo cp scripts/monitoring/aitbc-prometheus-watch.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now aitbc-prometheus-watch
```

Alert events appear in the journal and, with the installed unit (which passes `--alert-log /var/log/aitbc/alerts.log`), in that file. Follow either with:

```bash
journalctl -u aitbc-prometheus-watch -f
tail -f /var/log/aitbc/alerts.log
```

### Watcher configuration file

The unit loads `/etc/aitbc/prometheus-watch.env` when present. Each key feeds the matching CLI option, so tuning does not require editing the unit:

```bash
# /etc/aitbc/prometheus-watch.env — EnvironmentFile= does not strip inline
# comments; annotate on their own lines.
AITBC_WATCH_INTERVAL=15
AITBC_WATCH_NOTIFY_URL="https://ops.example/hook https://backup.example/hook"
AITBC_WATCH_SILENCE_FILE=/etc/aitbc/silences.json
AITBC_WATCH_REMIND_INTERVAL=14400
AITBC_WATCH_METRICS_FILE=/var/lib/prometheus/node-exporter/aitbc_prometheus_watch.prom
```

`WatchdogSec=75` in the unit restarts the service if the loop hangs; keep it at least 5× `AITBC_WATCH_INTERVAL`.

### Webhook notifications

Each `--notify-url` (repeatable, or space-separated in `AITBC_WATCH_NOTIFY_URL`) receives a `POST` with the full event record as its JSON body — `prometheus_watch_started`, `prometheus_alert_firing`, `prometheus_alert_still_firing` and `prometheus_alert_resolved`, the latter including `duration_seconds`. A URL gets one immediate retry on failure; after that the failure is logged and counted in `aitbc_prometheus_watch_notify_errors_total`, and the watch loop continues — the alert is never lost, it is always in the event log. Keep receiver endpoints free of authentication for private networks, or terminate auth on the receiving side; the URLs are the only secret here, so the env file should be `0600 root:aitbc`.

### Silences

`--silence-file` points at a JSON list reloaded every poll, so editing it takes effect within one interval without a restart:

```json
[
  {"match": {"alertname": "ServiceDown", "labels": {"instance": "hub1:9100"}},
   "until": "2026-10-05T00:00:00Z", "reason": "exporter intentionally stopped"},
  {"match": {"labels": {"node": "node2"}},
   "reason": "node2 maintenance — no expiry"}
]
```

`match.alertname` and every entry in `match.labels` must match (subset match); an empty `match` silences nothing. `until` is ISO-8601; omit it for a permanent silence. A silenced transition is still written to the alert log with `"silenced": true` — silence suppresses the webhook push, never the record. An alert whose silence expires or is removed while it still fires emits a fresh `prometheus_alert_firing` with `"via": "silence_expired"` and notifies again. A malformed silence file fails open: it warns once and silences nothing.

For a permanently retired scrape target prefer deleting it at the source — remove the job from that node's own `prometheus.yml` (or stop the remote write that ships its `up` series to the hub) rather than carrying an eternal silence.

### Reading the alert log

`aitbc prometheus alert-history` replays the event log — `--path` (default `/var/log/aitbc/alerts.log`, rotated files pass directly), `--since 24h` or an ISO timestamp, `--alertname`, `--node`, `--state firing|resolved|silenced`, `--last N`:

```bash
aitbc prometheus alert-history --since 24h
aitbc prometheus alert-history --node node0 --state firing
```

The result lists the matching events plus `firing_now`, the alert set still open at end of file — reconstructed from the whole stream, so a resolve outside the `--since` window still clears its alert.

### Still-firing reminders

`--remind-interval SECONDS` re-emits `prometheus_alert_still_firing` (recorded and notified) while an alert stays firing. Silenced alerts are not reminded, and reminders restart their cadence after a Prometheus outage instead of bursting.

### Watcher self-heartbeat

With `--metrics-file` (env `AITBC_WATCH_METRICS_FILE`) the watcher atomically writes a node-exporter textfile every poll:

- `aitbc_prometheus_watch_poll_timestamp_seconds` — last poll attempt (proves the loop is alive even while Prometheus is down)
- `aitbc_prometheus_watch_prometheus_reachable` — 1/0
- `aitbc_prometheus_watch_firing`, `aitbc_prometheus_watch_silenced_firing` — current counts
- `aitbc_prometheus_watch_notify_errors_total` — failed webhook deliveries

The shipped rules include `PrometheusWatchStale` (fires when the heartbeat is absent or older than five minutes). Deployment needs the textfile directory writable by the `aitbc` user — the fleet recipe is `chgrp aitbc /var/lib/prometheus/node-exporter && chmod 2775 ...` (the Debian nodes have no `acl` package for `setfacl`) — and a `ReadWritePaths=/var/lib/prometheus/node-exporter` drop-in for the unit (the deployed unit is a symlink into the checkout, so a drop-in in `aitbc-prometheus-watch.service.d/` carries it rather than uncommenting the repo file). The watcher writes the file world-readable; node-exporter runs as `prometheus` and skips unreadable files with `node_textfile_scrape_error 1`. A node that never ran the watcher has no series and stays invisible to the stale rule; if node-exporter itself dies, `ServiceDown` on the node job is the alert that fires instead.

### Public alerts page

The hub site serves `alerts.html` (linked from every page's nav), rendered from two blockchain-explorer endpoints that only make sense on the hub — its Prometheus aggregates the fleet via remote-write, so the firing list is fleet-wide:

- `GET /explorer-api/api/alerts` — firing + pending alerts with watcher-heartbeat health; when Prometheus is unreachable the response falls back to replaying the watcher's event log (`"source": "event_log"`) instead of going blank. `silenced` flags come from the log replay since Prometheus does not know watcher silences.
- `GET /explorer-api/api/alerts/history?limit=&alertname=&node=&state=` — the watcher event log, newest first; same filters as `aitbc prometheus alert-history`.
- `GET /explorer-api/api/journal/recent?unit=&priority=&limit=&since_minutes=` — recent journal entries restricted to `aitbc-*` units (priority one of `emerg|alert|crit|err|warning`, limit ≤ 200, since ≤ 7 days). Powers the page's Service Journal card; non-aitbc units are rejected and also filtered out after the fetch, so public traffic can never read e.g. sshd or kernel logs.

No nginx change is needed — all ride the existing `/explorer-api/` location. The explorer reads `PROMETHEUS_URL` (default `http://127.0.0.1:9090`) and `AITBC_ALERT_LOG` (default `/var/log/aitbc/alerts.log`) from its env files; on other nodes the endpoints answer with whatever local data exists. Journal access comes from `SupplementaryGroups=systemd-journal` in the explorer unit — where an older unit runs, the endpoint returns an empty list with `journal_access: false`.

### Journal error coverage

`aitbc-journal-errors.timer` (every 5 min) runs `scripts/monitoring/journal-errors-textfile.py`, which counts `journalctl -p warning` entries per unit over a rolling 15-minute window into `/var/lib/prometheus/node-exporter/aitbc_journal.prom`:

- `aitbc_journal_error_messages{unit}` — priorities emerg..err; `AITBCJournalErrors` fires when any is `> 0` for 5 min
- `aitbc_journal_warning_messages{unit}` — priority warning; page-visible, not alerted
- `aitbc_journal_scan_success` / `aitbc_journal_scan_timestamp_seconds` — collector health

The unit runs as `aitbc` with `SupplementaryGroups=systemd-journal`; install as symlinks into the checkout like the other monitoring units:

```bash
sudo ln -sfn /opt/aitbc/scripts/monitoring/aitbc-journal-errors.{service,timer} /etc/systemd/system/
sudo systemctl daemon-reload && sudo systemctl enable --now aitbc-journal-errors.timer
```

A single logged error keeps the count non-zero until it slides out of the 15-minute window, so `AITBCJournalErrors` stays up for roughly 15–20 min per burst — long enough to be seen, short enough to clear itself.

## Prometheus-first metrics

### Core AITBC metrics

The blockchain node main process exposes `/metrics` on `AITBC_NODE_METRICS_PORT` (default `9009`). The RPC process and the coordinator API also expose `/metrics` (or `/prometheus`) on their normal ports. Key series to watch:

**Note on RPC metrics.** The RPC process imports Python modules that define node-only gauges such as `blockchain_block_height`, `blockchain_poa_valid_subscribers` and `blockchain_sync_lag_blocks`, but it does not update them. Those series are zero or stale on the RPC target, so `scripts/monitoring/prometheus.yml` drops them with `metric_relabel_configs` on the `node2-blockchain-rpc` job. The canonical values are scraped from the node target on port `9009`.

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
            blockchain_poa_valid_subscribers{chain_id!~".*island.*"} == 0
            and on() (increase(blockchain_poa_broadcast_skipped_total{chain_id!~".*island.*"}[1m]) > 0)
          )
        for: 1m
        labels:
          severity: critical
        annotations:
          summary: "Block {{ $labels.chain_id }} produced but has zero valid subscribers"
          description: "Proposer is producing blocks on {{ $labels.chain_id }} but no follower is subscribed; blocks are not being broadcast."

      - alert: BroadcastSkipped
        expr: increase(blockchain_poa_broadcast_skipped_total{chain_id!~".*island.*"}[5m]) > 0
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

### Authority account balances

The node exporters carry no account balances, so nothing warned when the escrow settlement authority ran short of fee float. Escrow release and refund debit `max(36, amount // 100)` units (1% of the settled amount) from that account; once its balance is below the fee, both fail and the escrowed funds stay locked until it is topped up. `scripts/monitoring/authority-balances-textfile.py` reads the settlement and bridge release authorities from the local RPC and writes them as a node_exporter textfile, once a minute, from `aitbc-authority-balances.timer`:

| Series | Meaning |
|---|---|
| `aitbc_authority_balance_units{role,address}` | balance in units (1 AIT = 36,000,000); left out when the read failed, so a stale value never reads as current |
| `aitbc_authority_nonce{role,address}` | account nonce |
| `aitbc_authority_scrape_success{role,address}` | 1 when the account was read in the last run, else 0 |
| `aitbc_authority_scrape_timestamp_seconds` | Unix time the last run finished |

Alerts in `scripts/monitoring/aitbc_rules.yml` (tests in `aitbc_rules_test.yml`):

| Alert | Fires when | Severity |
|---|---|---|
| `AuthorityFloatLow` | settlement authority below 9,000,000 units (0.25 AIT, about 25 AIT of settled volume) for 2 minutes | warning |
| `AuthorityFloatCritical` | settlement authority below 1,800,000 units (0.05 AIT, about 5 AIT of settled volume) for 2 minutes | critical |
| `BridgeAuthorityAccountMoved` | the bridge release authority's balance fell or its nonce changed within 15 minutes | critical |
| `AuthorityBalanceUnreadable` | an account could not be read for 5 minutes | warning |
| `AuthorityBalanceStale` | the textfile is missing or older than 5 minutes, for 5 minutes | warning |

The bridge release authority has no low-balance alert on purpose. `BRIDGE_RELEASE` and `BRIDGE_REFUND` carry a pseudo-sender (no account, no nonce, no debit) and the authority only signs them, so its balance cannot run out; a balance that falls or a nonce that moves means its key sent a transaction.

Install on the node that runs Prometheus (hub): copy the `.service` and `.timer` to `/etc/systemd/system/`, edit `AITBC_WATCH_ACCOUNTS` when an authority is rotated (the settlement authority is the on-chain `escrow_settlement_authority` parameter, the bridge authority is `bridge_release_authority`), then:

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now aitbc-authority-balances.timer
sudo promtool check rules /etc/prometheus/aitbc_rules.yml   # after copying the rules file
sudo systemctl reload prometheus
curl -s localhost:9100/metrics | grep '^aitbc_authority_'
```

Roll back with `systemctl disable --now aitbc-authority-balances.timer`, removing `/var/lib/prometheus/node-exporter/aitbc_authority.prom`, and restoring the previous rules file. Nothing here touches a validator, a node process or the chain.

## Scrape configuration

By default Prometheus only scrapes the local node. Remote targets are not planned, so the sample `/etc/prometheus/prometheus.yml` only lists `localhost` jobs:

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
  - job_name: 'node2-blockchain-node'
    static_configs:
      - targets: ['localhost:9009']
        labels:
          node: <node2>
          service: blockchain-node

  - job_name: 'node2-blockchain-rpc'
    static_configs:
      - targets: ['localhost:8202']
        labels:
          node: <node2>
          service: blockchain-rpc

  # Coordinator API and market only run on the hub node by default.
  # - job_name: 'node2-coordinator-api'
  #   static_configs:
  #     - targets: ['localhost:8203']  # check-ports: ignore
  #       labels:
  #         node: <node2>
  #         service: coordinator-api
  #   metrics_path: '/prometheus'
  #   scrape_interval: 15s
  #
  # - job_name: 'node2-market'
  #   static_configs:
  #     - targets: ['localhost:8104']
  #       labels:
  #         node: <node2>
  #         service: market
  #   metrics_path: '/metrics'
  #   scrape_interval: 15s
```

## Making Prometheus more useful on `<node2>`

Since `<node2>` has more hardware than `hub`:

1. **Run Prometheus on the local node.** The default configuration scrapes only `localhost`. If a central view is needed later, deploy a separate central Prometheus with an explicit remote-write or federation plan.
2. **Add recording rules** for expensive queries used in alerts and ad-hoc investigation:
   ```yaml
   - record: aitbc:block_interval_seconds:rate5m
     expr: 60 / rate(blockchain_block_height[5m])
   ```
3. **Expose process and chain metrics.** The blockchain node main process now serves `/metrics` on port `9009` via `AITBC_NODE_METRICS_PORT` and exports chain height, valid subscriber counts and broadcast-skip counters.
4. **Promote operational log lines.** `BROADCAST SKIPPED` and similar events are now logged at `WARNING` and counted in `blockchain_poa_broadcast_skipped_total` so an agent sees both the event and the metric.
5. **Run `prometheus-node-exporter` on every node.** System metrics are cheap and make it easy to distinguish code bugs from resource exhaustion.
6. **Use the fleet retention standard.** `<node2>` runs the same Prometheus retention as every other node (see *Maintenance → Retention standard*); there is no per-node override. Size the disk from `node_filesystem_avail_bytes`.
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

### Retention standard

Every node runs Prometheus with the package default retention: no `--storage.tsdb.retention.*` flags, which Prometheus 2.53 resolves to 15 days and no size limit. Do not set per-node retention overrides; to change retention, change it on every node.

The flags live in `/etc/default/prometheus` (`ARGS=`, read by `prometheus.service`) and only role flags belong there. Today that is one: `hub` receives remote writes.

```
# every node except hub
ARGS=""
# hub
ARGS="--web.enable-remote-write-receiver"
```

Check the effective value on a node (it should print `15d`):

```bash
curl -s http://localhost:9090/api/v1/status/runtimeinfo | python3 -c 'import sys,json; print(json.load(sys.stdin)["data"]["storageRetention"])'
```

For scale, on 2026-10-01 the TSDB held between 0.06 and 1.0 GiB per node for 15 days of data.

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
