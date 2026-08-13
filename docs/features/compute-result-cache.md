# Compute Result Cache

Cache compute results with TTL

- **Status**: ✅
- **Release**: —

## Implementation Details

- `apps/coordinator-api/src/coordinator_api/utils/cache.py` — Simple in-memory cache with TTL support and memory management
- `aitbc/trading/offer_cache.py` — Get a single offer from the cache.
- `aitbc/caching/lru_cache.py` — LRU (Least Recently Used) cache implementation
- `aitbc/caching/redis_cache.py` — Redis cache wrapper for distributed caching
- `Coordinator API` exposes `GET /v1/jobs/{job_id}/result` (operation `get_job_result_v1_jobs__job_id__result_get`) — Get job result
- `Coordinator API` exposes `POST /v1/miners/{job_id}/result` (operation `submit_result_v1_miners__job_id__result_post`) — Submit job result
- `Coordinator API` exposes `GET /v1/multi-modal-rl/jobs/{job_id}/result` (operation `get_job_result_v1_multi_modal_rl_jobs__job_id__result_get`) — Get Job Result

## Examples

- `GET /requests/{request_id}/result` (`get_compute_result` in `apps/edge/src/aitbc_edge/routers/serve.py`)
- `POST /miners/{job_id}/result` (`submit_result` in `apps/coordinator-api/src/coordinator_api/contexts/infrastructure/routers/miner.py`)
- `POST /join` (`join_island` in `apps/edge/src/aitbc_edge/routers/islands.py`)
- `POST /leave` (`leave_island` in `apps/edge/src/aitbc_edge/routers/islands.py`)
- `GET /` (`list_islands` in `apps/edge/src/aitbc_edge/routers/islands.py`)
- `GET /v1/jobs/{job_id}/result` (`get_job_result_v1_jobs__job_id__result_get`) on `Coordinator API`
- `POST /v1/miners/{job_id}/result` (`submit_result_v1_miners__job_id__result_post`) on `Coordinator API`
- `GET /v1/multi-modal-rl/jobs/{job_id}/result` (`get_job_result_v1_multi_modal_rl_jobs__job_id__result_get`) on `Coordinator API`

## Operational Notes

- **Status / Release:** `✅` / `—`
- Handles task distribution, result collection, and edge-local caching.
