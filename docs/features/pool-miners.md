# Miner Roster

List the miners registered with the network — the live equivalent of "miners in a pool".

> Previously described a removed pool-CRUD surface (v0.6.7); rewritten to the live pool-hub/coordinator surface.

- **Status**: ✅
- **Release**: current

## Implementation Details

- `Coordinator API` exposes `GET /v1/admin/miners` — handler `list_miners` in `apps/coordinator-api/src/coordinator_api/contexts/infrastructure/routers/admin.py:159` (admin JWT, rate-limited). Returns `items[]` with `miner_id`, `status`, `inflight`, `concurrency`, `region`, `last_heartbeat`, `average_job_duration_ms`, `jobs_completed`, `jobs_failed`, `last_receipt_id` from the coordinator's `Miner` domain model.
- `Pool Hub` keeps its roster in the `miners` table (`apps/pool-hub/src/poolhub/models.py:48`) with live state in `miner_status` (:75); it is traversed internally by `MinerRepository.iter_miners` / `list_active_miners` (`apps/pool-hub/src/poolhub/repositories/miner_repository.py:139` / :146) for `POST /v1/match` — there is no public pool-hub roster endpoint.
- Per-miner operational reads: `GET /v1/miners/status` (self, `miners.py:105`), `POST /v1/miners/{miner_id}/jobs` (`list_miner_jobs`, coordinator `miner.py:644`), `POST /v1/miners/{miner_id}/earnings` (`get_miner_earnings`, coordinator `miner.py:688`).
- `Blockchain Node` exposes `GET /rpc/mining/miners` (operation `list_miners_route_rpc_mining_miners_get`) — active miners aggregated from the coordinator.

## Examples

- `GET /v1/admin/miners` (`list_miners` in `apps/coordinator-api/src/coordinator_api/contexts/infrastructure/routers/admin.py:159`) on `Coordinator API`
- `GET /v1/miners/status` (`miner_status` in `apps/pool-hub/src/poolhub/app/routers/miners.py:105`) on `Pool Hub`
- `POST /v1/miners/{miner_id}/jobs` (`list_miner_jobs` in `apps/coordinator-api/src/coordinator_api/contexts/infrastructure/routers/miner.py:644`) on `Coordinator API`
- `GET /rpc/mining/miners` (`list_miners_route_rpc_mining_miners_get`) on `Blockchain Node`

## Operational Notes

- **Status / Release:** `✅` / current
- The roster is flat — miners belong to the network, not to per-pool groupings; `region` and `capabilities` are the filtering dimensions used by `/v1/match`.
