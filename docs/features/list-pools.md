# List Miners & Match Entities

List the entities the pool-hub and coordinator actually track: the miner roster, service configurations, and match requests/results.

> Previously described a removed pool-CRUD surface (v0.6.7); rewritten to the live pool-hub/coordinator surface.

- **Status**: ✅
- **Release**: current

## Implementation Details

- `Coordinator API` exposes `GET /v1/admin/miners` — handler `list_miners` in `apps/coordinator-api/src/coordinator_api/contexts/infrastructure/routers/admin.py:159` (admin JWT). This is the authoritative fleet roster.
- `Pool Hub` keeps the active-miner roster internally via `MinerRepository.iter_miners` / `list_active_miners` (`apps/pool-hub/src/poolhub/repositories/miner_repository.py:139` / :146); it backs `POST /v1/match` candidate selection (`apps/pool-hub/src/poolhub/app/routers/match.py:34`) rather than a public list endpoint.
- `Pool Hub` exposes `GET /v1/services/` — handler `list_service_configs` in `apps/pool-hub/src/poolhub/app/routers/services.py:19`; and `GET /v1/services/{service_type}` (:31) for a single config (`service_configs` table, `models.py:135`).
- Match requests/results are persisted in `match_requests` / `match_results` (`apps/pool-hub/src/poolhub/models.py:91` / :104) via `MatchRepository.create_request`/`add_results`; they are written by `POST /v1/match` and are **not** exposed via a list endpoint.
- `Blockchain Node` exposes `GET /rpc/mining/miners` (operation `list_miners_route_rpc_mining_miners_get`) — list active miners aggregated from the coordinator.

## Examples

- `GET /v1/admin/miners` (`list_miners` in `apps/coordinator-api/src/coordinator_api/contexts/infrastructure/routers/admin.py:159`) on `Coordinator API`
- `GET /v1/services/` (`list_service_configs` in `apps/pool-hub/src/poolhub/app/routers/services.py:19`) on `Pool Hub`
- `POST /v1/match` (`match_endpoint` in `apps/pool-hub/src/poolhub/app/routers/match.py:34`) on `Pool Hub`
- `GET /rpc/mining/miners` (`list_miners_route_rpc_mining_miners_get`) on `Blockchain Node`

## Operational Notes

- **Status / Release:** `✅` / current
- There is no `GET /v1/pools` and no public pool-hub miner list — "listing" is either the coordinator admin roster or the pool-hub service-config list. Match history is queryable only in the database (`match_requests`/`match_results`).
