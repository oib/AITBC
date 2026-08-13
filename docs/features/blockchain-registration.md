# Blockchain Registration

Register edge node on blockchain on startup

- **Status**: ✅
- **Release**: v0.10.1

## Implementation Details

- `apps/pool-hub/src/poolhub/clients/blockchain.py` — Return the exact bytes that are hashed and signed for a transaction.
- `aitbc/marketplace/blockchain_rpc.py` — from **future** import annotations import logging from typing import Any, cast import httpx logger =...
- `apps/edge/src/aitbc_edge/clients/blockchain_rpc.py` — Blockchain RPC client for Edge API Service
- `apps/blockchain-node/aitbc-blockchain-p2p-wrapper.py` — blockchain-p2p service wrapper
- `apps/gpu/src/gpu_service/services/edge_gpu_service.py` — Edge GPU service for managing GPU operations
- `Blockchain Node` exposes `POST /rpc/edge/register` (operation `register_edge_node_rpc_edge_register_post`) — Register edge node on-chain
- `Blockchain Node` exposes `GET /rpc/edge/info/{node_id}` (operation `get_edge_node_rpc_edge_info__node_id__get`) — Query edge node registration
- `Blockchain Node` exposes `POST /rpc/register-account` (operation `create_account_route_rpc_register_account_post`) — Create/register a new account on the blockchain

## Examples

- `POST /graphs/{graph_id}/nodes` (`contribute_knowledge` in `apps/coordinator-api/src/coordinator_api/contexts/knowledge/routers/knowledge.py`)
- `POST /nodes/register` (`register_node` in `apps/coordinator-api/src/coordinator_api/contexts/agent_coordination/routers/swarm.py`)
- `POST /consensus/node/register` (`register_consensus_node` in `apps/agent-coordinator/src/agent_app/routers/consensus.py`)
- `POST /join` (`join_island` in `apps/edge/src/aitbc_edge/routers/islands.py`)
- `POST /leave` (`leave_island` in `apps/edge/src/aitbc_edge/routers/islands.py`)
- `POST /rpc/edge/register` (`register_edge_node_rpc_edge_register_post`) on `Blockchain Node`
- `GET /rpc/edge/info/{node_id}` (`get_edge_node_rpc_edge_info__node_id__get`) on `Blockchain Node`
- `POST /rpc/register-account` (`create_account_route_rpc_register_account_post`) on `Blockchain Node`

## Operational Notes

- **Status / Release:** `✅` / `v0.10.1`
