# Pool-Hub SLA Metrics & Reward Payouts

Aggregate operational statistics for the miner fleet: SLA metrics/violations, capacity snapshots, and reward payout records.

> Previously described a removed pool-CRUD surface (v0.6.7); rewritten to the live pool-hub/coordinator surface.

- **Status**: ✅
- **Release**: current

## Implementation Details

- `Pool Hub` exposes `GET /v1/sla/metrics` (`get_all_sla_metrics`, `apps/pool-hub/src/poolhub/app/routers/sla.py:117`) and `GET /v1/sla/metrics/{miner_id}` (:100) over the `sla_metrics` table (`apps/pool-hub/src/poolhub/models.py:157`: `metric_type`, `metric_value`, `threshold`, `is_violation`).
- `GET /v1/sla/violations` (`get_sla_violations`, `sla.py:133`) reads `sla_violations` (`models.py:174`: `violation_type`, `severity`, `violation_duration_ms`, `resolved_at`). `GET /v1/sla/status` (`get_sla_status`, `sla.py:323`) returns a fleet-wide SLA summary.
- Capacity stats: `GET /v1/sla/capacity/snapshots` (:164), `GET /v1/sla/capacity/forecast` (:184), `GET /v1/sla/capacity/recommendations` (:206) over `capacity_snapshots` (`models.py:193`: `total_miners`, `active_miners`, `capacity_utilization_pct`, `forecast_capacity`).
- Collection is manual or scheduled: `POST /v1/sla/metrics/collect` (`collect_sla_metrics`, `sla.py:151`); the `SLACollectorScheduler` and `BillingIntegrationScheduler` only run when `POOLHUB_ENABLE_SLA_COLLECTION` / `POOLHUB_ENABLE_BILLING_SYNC` are set (`apps/pool-hub/src/poolhub/app/main.py:47-60`).
- Reward payouts: the `reward_payouts` table (`models.py:211`) records per-miner per-epoch payouts with a `uq_reward_payout_miner_chain_epoch` unique constraint; rows are claimed and settled inside `BlockchainClient.distribute_rewards` (`apps/pool-hub/src/poolhub/clients/blockchain.py:149`), which submits the reward transaction and marks rows `paid`/`failed`. There is no HTTP endpoint exposing payout rows — they are a DB-level audit trail (note: `distribute_rewards` currently has no in-tree caller).
- Prometheus metrics for the service itself: `GET /metrics` (`metrics_endpoint`, `apps/pool-hub/src/poolhub/app/routers/metrics.py:10`).
- `Coordinator API` exposes `POST /v1/miners/{miner_id}/earnings` (`get_miner_earnings`, `apps/coordinator-api/src/coordinator_api/contexts/infrastructure/routers/miner.py:688`) — per-miner earnings aggregation from completed jobs.

## Examples

- `GET /v1/sla/metrics` (`get_all_sla_metrics` in `apps/pool-hub/src/poolhub/app/routers/sla.py:117`) on `Pool Hub`
- `GET /v1/sla/violations` (`get_sla_violations` in `apps/pool-hub/src/poolhub/app/routers/sla.py:133`) on `Pool Hub`
- `GET /v1/sla/status` (`get_sla_status` in `apps/pool-hub/src/poolhub/app/routers/sla.py:323`) on `Pool Hub`
- `GET /v1/sla/capacity/snapshots` (`get_capacity_snapshots` in `apps/pool-hub/src/poolhub/app/routers/sla.py:164`) on `Pool Hub`
- `POST /v1/miners/{miner_id}/earnings` (`get_miner_earnings` in `apps/coordinator-api/src/coordinator_api/contexts/infrastructure/routers/miner.py:688`) on `Coordinator API`
- `GET /metrics` (`metrics_endpoint` in `apps/pool-hub/src/poolhub/app/routers/metrics.py:10`) on `Pool Hub`

## Operational Notes

- **Status / Release:** `✅` / current
- "Pool stats" in the old sense = the SLA/capacity endpoints plus the `reward_payouts` audit table. SLA metrics are only populated when collection runs (manual POST or the schedulers being enabled).
