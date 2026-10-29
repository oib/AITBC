# Miner Deregistration

Deregister a miner from the coordinator and stop receiving job assignments.

> Previously described a removed pool-CRUD surface (v0.6.7); rewritten to the live pool-hub/coordinator surface.

- **Status**: ✅
- **Release**: current

## Implementation Details

- `Coordinator API` exposes `DELETE /v1/miners/{miner_id}` — handler `deregister_miner` in `apps/coordinator-api/src/coordinator_api/contexts/infrastructure/routers/miner.py:797`. Authenticated as the miner (`MinerDep`); calls `MinerService.deregister(miner_id)` and returns `{"miner_id": ..., "status": "deregistered"}` (404 when the miner is unknown).
- Deregistration service logic lives in `apps/coordinator-api/src/coordinator_api/contexts/infrastructure/services/miners.py`.
- There is **no** pool-hub-side deregister endpoint: `apps/pool-hub/src/poolhub/app/routers/miners.py` exposes only `POST /v1/miners/register` (:47), `POST /v1/miners/heartbeat` (:85) and `GET /v1/miners/status` (:105). Miner rows in `miners` / `miner_status` (`apps/pool-hub/src/poolhub/models.py:48` / :75) go stale instead of being deleted; heartbeats simply stop and the miner drops out of `list_active_miners` (`apps/pool-hub/src/poolhub/repositories/miner_repository.py:146`), so it stops appearing in `/v1/match` candidates.
- The coordinator additionally runs a `StaleMinerReaper` that marks stale-heartbeat miners `OFFLINE` (`apps/coordinator-api/src/coordinator_api/main.py:250`).

## Examples

- `DELETE /v1/miners/{miner_id}` (`deregister_miner` in `apps/coordinator-api/src/coordinator_api/contexts/infrastructure/routers/miner.py:797`) on `Coordinator API`
- `POST /v1/miners/heartbeat` (`miner_heartbeat` in `apps/pool-hub/src/poolhub/app/routers/miners.py:85`) on `Pool Hub` — stopping heartbeats is the pool-hub-side equivalent of leaving

## Operational Notes

- **Status / Release:** `✅` / current
- There are no "pools" to delete: the pool-hub has no `Pool` table (see `apps/pool-hub/src/poolhub/models.py`). Removing a compute provider means deregistering its miner id on the coordinator and/or ceasing heartbeats to the pool-hub.
