# Miner Registration

Register a GPU miner with the pool-hub and/or coordinator so it becomes matchable for jobs.

> Previously described a removed pool-CRUD surface (v0.6.7); rewritten to the live pool-hub/coordinator surface.

- **Status**: ✅
- **Release**: current

## Implementation Details

- `Pool Hub` exposes `POST /v1/miners/register` — handler `register_miner` in `apps/pool-hub/src/poolhub/app/routers/miners.py:47`. Body (`MinerRegisterRequest`, :20): `miner_id`, `api_key` (stored SHA-256-hashed), `addr`, `proto`, `gpu_vram_gb`, `gpu_name`, `cpu_cores`, `ram_gb`, `max_parallel`, `base_price`, `tags`, `capabilities`, `region`, `chain_id`, `wallet_address`. Writes the `miners` row (`apps/pool-hub/src/poolhub/models.py:48`) via `MinerRepository.register_miner` (`apps/pool-hub/src/poolhub/repositories/miner_repository.py:24`) and mirrors it into Redis.
- `Coordinator API` exposes `POST /v1/miners/register` — handler `register` in `apps/coordinator-api/src/coordinator_api/contexts/infrastructure/routers/miner.py:331` ("Register or update miner"); issues a session token used for `MinerDep` auth on the job/earnings/deregister routes.
- After registration the miner stays "active" by heartbeating: `POST /v1/miners/heartbeat` on the pool-hub (`miner_heartbeat`, `miners.py:85`, authenticated via `get_miner_from_token`) updates `miner_status` (`models.py:75`); `POST /v1/miners/heartbeat` on the coordinator (`miner.py:344`) keeps it out of the `StaleMinerReaper` path.
- Optional on-chain registration is available through `BlockchainClient.register_miner` (`apps/pool-hub/src/poolhub/clients/blockchain.py`), which submits a signed `GPU_REGISTER` envelope.

## Examples

- `POST /v1/miners/register` (`register_miner` in `apps/pool-hub/src/poolhub/app/routers/miners.py:47`) on `Pool Hub`
- `POST /v1/miners/register` (`register` in `apps/coordinator-api/src/coordinator_api/contexts/infrastructure/routers/miner.py:331`) on `Coordinator API`
- `POST /v1/miners/heartbeat` (`miner_heartbeat` in `apps/pool-hub/src/poolhub/app/routers/miners.py:85`) on `Pool Hub`

## Operational Notes

- **Status / Release:** `✅` / current
- There is no pool-creation step: a miner registers once and immediately becomes a candidate for `POST /v1/match` based on its declared capabilities, VRAM/RAM, region, and trust score.
