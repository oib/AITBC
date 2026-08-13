# GPU Registration

Register GPU with immutable specs on blockchain

- **Status**: ✅
- **Release**: —

## Implementation Details

- `apps/blockchain-node/src/aitbc_chain/rpc/gpu_resources.py` — GPU resource RPC endpoints for AITBC blockchain.
- `apps/blockchain-node/src/aitbc_chain/state/gpu_resources.py` — GPU resource state models for blockchain tracking.
- `apps/pool-hub/src/poolhub/clients/blockchain.py` — Return the exact bytes that are hashed and signed for a transaction.
- `aitbc/marketplace/blockchain_rpc.py` — from **future** import annotations import logging from typing import Any, cast import httpx logger =...
- `apps/coordinator-api/src/coordinator_api/contexts/marketplace/routers/marketplace_gpu.py` — Get pricing engine instance
- `Blockchain Node` exposes `POST /rpc/register-account` (operation `create_account_route_rpc_register_account_post`) — Create/register a new account on the blockchain
- `Blockchain Node` exposes `POST /rpc/gpu/register` (operation `register_gpu_rpc_gpu_register_post`) — Register GPU on-chain
- `Blockchain Node` exposes `GET /rpc/gpu/info/{gpu_id}` (operation `get_gpu_rpc_gpu_info__gpu_id__get`) — Query GPU registration

## Examples

- `POST /marketplace/gpu/register` (`register_gpu` in `apps/coordinator-api/src/coordinator_api/contexts/marketplace/routers/marketplace_gpu.py`)
- `GET /` (`list_gpus` in `apps/edge/src/aitbc_edge/routers/gpu.py`)
- `GET /{gpu_id}` (`get_gpu_listing` in `apps/edge/src/aitbc_edge/routers/gpu.py`)
- `DELETE /{gpu_id}` (`remove_gpu_listing` in `apps/edge/src/aitbc_edge/routers/gpu.py`)
- `POST /scan` (`scan_gpus` in `apps/edge/src/aitbc_edge/routers/gpu.py`)
- `POST /rpc/register-account` (`create_account_route_rpc_register_account_post`) on `Blockchain Node`
- `POST /rpc/gpu/register` (`register_gpu_rpc_gpu_register_post`) on `Blockchain Node`
- `GET /rpc/gpu/info/{gpu_id}` (`get_gpu_rpc_gpu_info__gpu_id__get`) on `Blockchain Node`

## Operational Notes

- **Status / Release:** `✅` / `—`
