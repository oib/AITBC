# Leaving the Miner Roster

Take a miner out of the matchable set — the live equivalent of "leaving a pool".

> Previously described a removed pool-CRUD surface (v0.6.7); rewritten to the live pool-hub/coordinator surface.

- **Status**: ✅
- **Release**: current

## Implementation Details

- There is no explicit pool-hub "leave" endpoint. A miner leaves the matchable set by stopping `POST /v1/miners/heartbeat` (`miner_heartbeat`, `apps/pool-hub/src/poolhub/app/routers/miners.py:85`): the heartbeat feeds `miner_status.last_heartbeat_at` (`models.py:75`) and `touch_heartbeat` (`apps/pool-hub/src/poolhub/repositories/miner_repository.py:118`), and once it goes stale the miner stops passing `list_active_miners` (:146), which is what `POST /v1/match` (`match.py:34`) draws candidates from.
- On the coordinator, leaving formally is `DELETE /v1/miners/{miner_id}` (`deregister_miner`, `apps/coordinator-api/src/coordinator_api/contexts/infrastructure/routers/miner.py:797`); the `StaleMinerReaper` (`apps/coordinator-api/src/coordinator_api/main.py:250`) marks silent miners `OFFLINE` automatically.
- A miner that merely wants to stop taking work but stay registered can also report itself busy via the heartbeat `status`/`current_jobs` fields (`MinerHeartbeatRequest`, `miners.py:38`), which sets `miner_status.busy`/`queue_len` and lowers match priority.

## Examples

- `DELETE /v1/miners/{miner_id}` (`deregister_miner` in `apps/coordinator-api/src/coordinator_api/contexts/infrastructure/routers/miner.py:797`) on `Coordinator API`
- `POST /v1/miners/heartbeat` (`miner_heartbeat` in `apps/pool-hub/src/poolhub/app/routers/miners.py:85`) on `Pool Hub` — ceasing it is the leave mechanism

## Operational Notes

- **Status / Release:** `✅` / current
- Match requests/results (`match_requests`, `match_results`) are retained after a miner leaves; they are historical records, not memberships.
