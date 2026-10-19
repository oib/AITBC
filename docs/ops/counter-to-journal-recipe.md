# Pairing a counter change with the journal lines around it

Recipe (not a dedicated tool — TOOL-MCP-2, gap 3). Two read-only CLI calls
per host cover the case: `prometheus metric` reads the node's **own**
`:9009/metrics` exposition (not Prometheus' last scrape, so a counter bumped
since the last scrape or reset by a restart reads truthfully), and
`system logs` filters the unit's journal in a window.

## Steps

1. Read the counter twice — before and after the window of interest — on the
   host that owns it:

   ```bash
   aitbc prometheus metric --name v9_would_reject_total          # t0
   # ... window ...
   aitbc prometheus metric --name v9_would_reject_total          # t1
   ```

   Each result carries `read_at` (UTC) — use it for the journal window so no
   host-timezone conversion is needed. A counter delta of 0 means no matching
   journal lines are expected; a positive delta brackets the events.

   Metrics other than the blockchain node's live on their own endpoints —
   pass `--url` (loopback only), e.g. the RPC/bridge exposition:

   ```bash
   aitbc prometheus metric --name blockchain_bridge_pending_transfers \
       --url http://127.0.0.1:8202/metrics
   ```

2. Pull the unit's journal lines in the same window:

   ```bash
   aitbc system logs --service blockchain-node \
       --since "2026-10-17 18:23:00" --grep "reject" --lines 200
   ```

   `--since` accepts any journalctl time spec; `--grep` a journalctl pattern
   (≤200 chars). Repeat with a wider `--lines` if the window is noisy.

3. Via MCP the same pair is `aitbc_prometheus_metric` (read-only) and
   `aitbc_system_logs` — both take `role`/`host`, so one call per host works
   exactly like `aitbc_prometheus_query`, except the counter value is the
   live exposition value rather than the last scrape.

## Why not `aitbc_prometheus_query` for the counter

`query` returns what Prometheus last scraped. After a restart (or for a
fresh counter such as `v9_would_reject_total`) the scraped series lags,
resets, or is absent — `prometheus metric` reads the source directly.

## Related

- `aitbc system env-names --service <svc> --process [--names ...] [--value N]`
  for variables present only in the running process environment
  (`/proc/<MainPID>/environ`) — names only, with `declared_only` /
  `process_only` drift flags against the declared env files.
