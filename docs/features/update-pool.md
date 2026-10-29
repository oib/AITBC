# Update Miner Capabilities

Update a registered miner's capabilities, pricing, and concurrency settings.

> Previously described a removed pool-CRUD surface (v0.6.7); rewritten to the live pool-hub/coordinator surface.

- **Status**: ✅
- **Release**: current

## Implementation Details

- `Coordinator API` exposes `PUT /v1/miners/{miner_id}/capabilities` — handler `update_miner_capabilities` in `apps/coordinator-api/src/coordinator_api/contexts/infrastructure/routers/miner.py:769` (audit-verified). Authenticated as the miner (`MinerDep`); takes a `MinerRegister` body, re-registers via `MinerService.register`, returns `miner_id`, `status: "updated"`, `capabilities`, and a fresh `session_token` (404 when unknown).
- Re-registration on the coordinator is itself an update path: `POST /v1/miners/register` (`register`, `miner.py:331`) is "Register or update miner" — re-posting replaces the stored record.
- `Pool Hub` has no capabilities-update endpoint; its miners router (`apps/pool-hub/src/poolhub/app/routers/miners.py`) exposes only register/heartbeat/status. The pool-hub-side equivalents are:
  - re-`POST /v1/miners/register` (`register_miner`, `miners.py:47`) to replace the `miners` row (`capabilities`, `tags`, `base_price`, `max_parallel`, `gpu_*` fields — `models.py:48`),
  - `PUT`-equivalent per-service config updates via `POST /v1/services/{service_type}` (`create_or_update_service_config`, `services.py:56`) or `PATCH /v1/services/{service_type}` (`patch_service_config`, `services.py:101`) on the `service_configs` table (`models.py:135`).

## Examples

- `PUT /v1/miners/{miner_id}/capabilities` (`update_miner_capabilities` in `apps/coordinator-api/src/coordinator_api/contexts/infrastructure/routers/miner.py:769`) on `Coordinator API`
- `POST /v1/miners/register` (`register` in `apps/coordinator-api/src/coordinator_api/contexts/infrastructure/routers/miner.py:331`) on `Coordinator API`
- `POST /v1/miners/register` (`register_miner` in `apps/pool-hub/src/poolhub/app/routers/miners.py:47`) on `Pool Hub`
- `PATCH /v1/services/{service_type}` (`patch_service_config` in `apps/pool-hub/src/poolhub/app/routers/services.py:101`) on `Pool Hub`

## Operational Notes

- **Status / Release:** `✅` / current
- There are no "pool settings" to update — a miner's mutable surface is its coordinator registration and its pool-hub service configs.
