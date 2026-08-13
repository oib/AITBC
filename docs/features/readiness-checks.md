# Readiness Checks

Readiness checks for database connectivity

- **Status**: ✅
- **Release**: —

## Implementation Details

- `apps/coordinator-api/src/coordinator_api/database_async.py` — Async database module with connection pooling for Coordinator API.
- `apps/shared-core/src/shared_core/core/database.py` — Shared database utilities for AITBC services.
- `apps/blockchain-node/scripts/migrate_database_encryption.py` — Database encryption migration tool for AITBC blockchain node. This CLI tool provides commands to enc...
- `apps/pool-hub/src/poolhub/database.py`
- `Coordinator API` exposes `GET /health/ready` (operation `readiness_health_ready_get`) — Readiness probe
- `Openapi` exposes `GET /health/ready` (operation `readiness_health_ready_get`) — Readiness probe

## Examples

- `POST /init` (`init_database` in `apps/edge/src/aitbc_edge/routers/database.py`)
- `GET /` (`list_databases` in `apps/edge/src/aitbc_edge/routers/database.py`)
- `GET /{database_id}` (`get_database` in `apps/edge/src/aitbc_edge/routers/database.py`)
- `DELETE /{database_id}` (`delete_database` in `apps/edge/src/aitbc_edge/routers/database.py`)
- `POST /{database_id}/sync` (`sync_database` in `apps/edge/src/aitbc_edge/routers/database.py`)
- `GET /health/ready` (`readiness_health_ready_get`) on `Coordinator API`
- `GET /health/ready` (`readiness_health_ready_get`) on `Openapi`

## Operational Notes

- **Status / Release:** `✅` / `—`
