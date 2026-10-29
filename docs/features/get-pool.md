# Miner Detail & Status

Read a miner's registered detail and live status.

> Previously described a removed pool-CRUD surface (v0.6.7); rewritten to the live pool-hub/coordinator surface.

- **Status**: ✅
- **Release**: current

## Implementation Details

- `Pool Hub` exposes `GET /v1/miners/status` — handler `miner_status` in `apps/pool-hub/src/poolhub/app/routers/miners.py:105`. Authenticated via the miner's API key (`get_miner_from_token`, `apps/pool-hub/src/poolhub/app/deps.py`); returns `miner_id`, `last_seen_at`, `addr`, `capabilities` for the *authenticated* miner only.
- The persisted miner record is the `miners` table (`apps/pool-hub/src/poolhub/models.py:48`): `miner_id`, `api_key_hash`, `addr`, `proto`, `gpu_vram_gb`, `gpu_name`, `cpu_cores`, `ram_gb`, `max_parallel`, `base_price`, `tags`, `capabilities`, `trust_score`, `region`, `chain_id`, `wallet_address`.
- Live load/health lives in `miner_status` (`apps/pool-hub/src/poolhub/models.py:75`): `queue_len`, `busy`, `avg_latency_ms`, `temp_c`, `mem_free_gb`, `uptime_pct`, `last_heartbeat_at` — read internally via `MinerRepository.get_status` (`apps/pool-hub/src/poolhub/repositories/miner_repository.py:143`) and `get_miner` (:136).
- `Coordinator API` exposes `GET /v1/admin/miners` — handler `list_miners` in `apps/coordinator-api/src/coordinator_api/contexts/infrastructure/routers/admin.py:159` (admin JWT); returns per-miner `status`, `inflight`, `concurrency`, `region`, `last_heartbeat`, `average_job_duration_ms`, `jobs_completed`, `jobs_failed`, `last_receipt_id`.
- `Blockchain Node` exposes `GET /rpc/mining/miners` (operation `list_miners_route_rpc_mining_miners_get`) — list active miners as aggregated from the coordinator.
- Per-miner SLA detail: `GET /v1/sla/metrics/{miner_id}` (`get_miner_sla_metrics`, `apps/pool-hub/src/poolhub/app/routers/sla.py:100`).

## Examples

- `GET /v1/miners/status` (`miner_status` in `apps/pool-hub/src/poolhub/app/routers/miners.py:105`) on `Pool Hub`
- `GET /v1/admin/miners` (`list_miners` in `apps/coordinator-api/src/coordinator_api/contexts/infrastructure/routers/admin.py:159`) on `Coordinator API`
- `GET /v1/sla/metrics/{miner_id}` (`get_miner_sla_metrics` in `apps/pool-hub/src/poolhub/app/routers/sla.py:100`) on `Pool Hub`
- `GET /rpc/mining/miners` (`list_miners_route_rpc_mining_miners_get`) on `Blockchain Node`

## Operational Notes

- **Status / Release:** `✅` / current
- There is no `GET /v1/miners/{id}` on the pool-hub — a miner can only read its own status; a fleet-wide view requires the coordinator admin endpoint or the SLA metrics endpoints.
