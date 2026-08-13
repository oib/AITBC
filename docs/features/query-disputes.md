# Query Disputes

Get active, arbitrator, or user disputes

- **Status**: ✅
- **Release**: —

## Implementation Details

- `apps/blockchain-node/src/aitbc_chain/rpc/routers/disputes.py` — Dispute resolution router.
- `apps/blockchain-node/src/aitbc_chain/rpc/disputes.py` — Dispute-related RPC endpoints.
- `apps/coordinator-api/src/coordinator_api/contexts/governance/routers/disputes.py` — Disputes Router - Dispute resolution API endpoints Provides: - Dispute filing - Evidence submission ...
- `apps/coordinator-api/alembic/versions/add_query_performance_indexes.py` — Create the missing query performance indexes.
- `Blockchain Node` exposes `GET /rpc/disputes/active` (operation `get_active_disputes_route_rpc_disputes_active_get`) — Get all active disputes
- `Blockchain Node` exposes `GET /rpc/disputes/arbitrators/{arbitrator_address}` (operation `get_arbitrator_disputes_route_rpc_disputes_arbitrators__arbitrator_address__get`) — Get disputes for an arbitrator
- `Blockchain Node` exposes `GET /rpc/disputes/user/{user_address}` (operation `get_user_disputes_route_rpc_disputes_user__user_address__get`) — Get disputes for a user

## Examples

- `GET /active` (`get_active_disputes_route` in `apps/blockchain-node/src/aitbc_chain/rpc/routers/disputes.py`)
- `GET /arbitrators/{arbitrator_address}` (`get_arbitrator_disputes_route` in `apps/blockchain-node/src/aitbc_chain/rpc/routers/disputes.py`)
- `GET /user/{user_address}` (`get_user_disputes_route` in `apps/blockchain-node/src/aitbc_chain/rpc/routers/disputes.py`)
- `GET /users/me` (`get_current_user` in `apps/coordinator-api/src/coordinator_api/contexts/infrastructure/routers/users.py`)
- `GET /users/{user_id}/balance` (`get_user_balance` in `apps/coordinator-api/src/coordinator_api/contexts/infrastructure/routers/users.py`)
- `GET /rpc/disputes/active` (`get_active_disputes_route_rpc_disputes_active_get`) on `Blockchain Node`
- `GET /rpc/disputes/arbitrators/{arbitrator_address}` (`get_arbitrator_disputes_route_rpc_disputes_arbitrators__arbitrator_address__get`) on `Blockchain Node`
- `GET /rpc/disputes/user/{user_address}` (`get_user_disputes_route_rpc_disputes_user__user_address__get`) on `Blockchain Node`

## Operational Notes

- **Status / Release:** `✅` / `—`
