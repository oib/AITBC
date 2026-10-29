# Match Request Submission

Submit a job to the pool-hub matcher and receive the top-scoring miners — the live equivalent of "joining" compute capacity to work.

> Previously described a removed pool-CRUD surface (v0.6.7); rewritten to the live pool-hub/coordinator surface.

- **Status**: ✅
- **Release**: current

## Implementation Details

- `Pool Hub` exposes `POST /v1/match` — handler `match_endpoint` in `apps/pool-hub/src/poolhub/app/routers/match.py:34`. Body (`MatchRequestPayload`, `apps/pool-hub/src/poolhub/app/schemas.py:10`): `job_id`, `requirements` (normalized — `min_vram_gb`, `min_ram_gb`, `capabilities_any`), `hints` (`region`), `top_k`.
- The handler persists a `match_requests` row (`models.py:91`) via `MatchRepository.create_request`, pulls active miners via `MinerRepository.list_active_miners` (`apps/pool-hub/src/poolhub/repositories/miner_repository.py:146`), filters/ranks in `_select_candidates` (`match.py:78`) — hard filters on VRAM/RAM/required-capabilities/region, then score-sorted top_k — and records each pick as a `match_results` row (`models.py:104`) with `score`, `explain` (`_compose_explain`, `match.py:115`), `eta_ms`, `price`.
- Response (`MatchResponse`, `schemas.py:38`): `job_id` plus `candidates` of `MatchCandidate` (`schemas.py:18`) with `miner_id`, `addr`, `proto`, `score`, `explain`, `eta_ms`, `price`.
- On the coordinator side, a miner "joins" work by polling: `POST /v1/miners/poll` (`poll`, `apps/coordinator-api/src/coordinator_api/contexts/infrastructure/routers/miner.py:359`) returns the next assigned job.

## Examples

- `POST /v1/match` (`match_endpoint` in `apps/pool-hub/src/poolhub/app/routers/match.py:34`) on `Pool Hub`
- `POST /v1/miners/poll` (`poll` in `apps/coordinator-api/src/coordinator_api/contexts/infrastructure/routers/miner.py:359`) on `Coordinator API`

## Operational Notes

- **Status / Release:** `✅` / current
- There is no `join pool` call — matching is per-request: every `POST /v1/match` re-evaluates the live miner roster, so "membership" is implicit in being registered and heartbeating.
