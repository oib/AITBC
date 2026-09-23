# Apply Parameters

Apply governance-approved parameters to market

- **Status**: ✅
- **Release**: v0.10.1

## Implementation Details

- `apps/governance/src/governance_service/services/governance_service.py` — Governance service for managing governance operations
- `apps/pool-hub/src/poolhub/app/routers/parameters.py` — Request body for applying a governance-approved parameter change.
- `apps/coordinator-api/src/coordinator_api/contexts/market/domain/global_market.py` — Global Market Domain Models Domain models for global market operations, multi-region suppo...
- `apps/coordinator-api/alembic/versions/add_global_market.py` — Add global market tables Revision ID: add_global_market Revises: add_cross_chain_reputatio...
- `apps/coordinator-api/src/coordinator_api/contexts/governance/domain/governance.py` — Decentralized Governance Models Database models for agent DAO, voting, proposals, and governance ana...
- `Market` exposes `POST /v1/market/parameters/apply` (operation `apply_market_parameter_v1_market_parameters_apply_post`) — Apply Market Parameter
- `Blockchain Node` exposes `POST /rpc/transactions/market` (operation `submit_market_transaction_route_rpc_transactions_market_post`) — Submit market transaction
- `Blockchain Node` exposes `POST /rpc/staking/stake` (operation `stake_tokens_route_rpc_staking_stake_post`) — Stake tokens

## Examples

- `GET /list` (`list_governance_parameters` in `apps/pool-hub/src/poolhub/app/routers/parameters.py`)
- `GET /` (`list_gpus` in `apps/edge/src/aitbc_edge/routers/gpu.py`)
- `GET /{gpu_id}` (`get_gpu_listing` in `apps/edge/src/aitbc_edge/routers/gpu.py`)
- `DELETE /{gpu_id}` (`remove_gpu_listing` in `apps/edge/src/aitbc_edge/routers/gpu.py`)
- `POST /scan` (`scan_gpus` in `apps/edge/src/aitbc_edge/routers/gpu.py`)
- `POST /v1/market/parameters/apply` (`apply_market_parameter_v1_market_parameters_apply_post`) on `Market`
- `POST /rpc/transactions/market` (`submit_market_transaction_route_rpc_transactions_market_post`) on `Blockchain Node`
- `POST /rpc/staking/stake` (`stake_tokens_route_rpc_staking_stake_post`) on `Blockchain Node`

## Operational Notes

- **Status / Release:** `✅` / `v0.10.1`
- Only GPUs are registered on-chain, not edge nodes themselves - ✅ v0.6.6 changelog calls for "Edge node registration with blockchain" - ✅ Fix: Add `EdgeNode` mod...
