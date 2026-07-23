# Apply Parameters

Apply governance-approved parameters to marketplace

- **Status**: ✅
- **Release**: v0.10.1
## Implementation Details
- `apps/governance/src/governance_service/services/governance_service.py` — Governance service for managing governance operations
- `apps/pool-hub/src/poolhub/app/routers/parameters.py` — Request body for applying a governance-approved parameter change.
- `apps/coordinator-api/src/coordinator_api/contexts/marketplace/domain/global_marketplace.py` — Global Marketplace Domain Models Domain models for global marketplace operations, multi-region suppo...
- `apps/coordinator-api/alembic/versions/add_global_marketplace.py` — Add global marketplace tables Revision ID: add_global_marketplace Revises: add_cross_chain_reputatio...
- `apps/coordinator-api/src/coordinator_api/contexts/governance/domain/governance.py` — Decentralized Governance Models Database models for agent DAO, voting, proposals, and governance ana...
- `Marketplace` exposes `POST /v1/marketplace/parameters/apply` (operation `apply_marketplace_parameter_v1_marketplace_parameters_apply_post`) — Apply Marketplace Parameter
- `Blockchain Node` exposes `POST /rpc/transactions/marketplace` (operation `submit_marketplace_transaction_route_rpc_transactions_marketplace_post`) — Submit marketplace transaction
- `Blockchain Node` exposes `POST /rpc/staking/stake` (operation `stake_tokens_route_rpc_staking_stake_post`) — Stake tokens
## Examples

- `GET /list` (`list_governance_parameters` in `apps/pool-hub/src/poolhub/app/routers/parameters.py`)
- `GET /` (`list_gpus` in `apps/edge/src/aitbc_edge/routers/gpu.py`)
- `GET /{gpu_id}` (`get_gpu_listing` in `apps/edge/src/aitbc_edge/routers/gpu.py`)
- `DELETE /{gpu_id}` (`remove_gpu_listing` in `apps/edge/src/aitbc_edge/routers/gpu.py`)
- `POST /scan` (`scan_gpus` in `apps/edge/src/aitbc_edge/routers/gpu.py`)
- `POST /v1/marketplace/parameters/apply` (`apply_marketplace_parameter_v1_marketplace_parameters_apply_post`) on `Marketplace`
- `POST /rpc/transactions/marketplace` (`submit_marketplace_transaction_route_rpc_transactions_marketplace_post`) on `Blockchain Node`
- `POST /rpc/staking/stake` (`stake_tokens_route_rpc_staking_stake_post`) on `Blockchain Node`
## Operational Notes
- **Status / Release:** `✅` / `v0.10.1`
- Only GPUs are registered on-chain, not edge nodes themselves - ✅ v0.6.6 changelog calls for "Edge node registration with blockchain" - ✅ Fix: Add `EdgeNode` mod...
