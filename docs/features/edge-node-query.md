# Edge Node Query

Query edge node registration from blockchain

- **Status**: ✅
- **Release**: v0.10.1
## Implementation Details
- `aitbc/marketplace/blockchain_rpc.py` — from __future__ import annotations import logging from typing import Any, cast import httpx logger =...
- `apps/pool-hub/src/poolhub/clients/blockchain.py` — Return the exact bytes that are hashed and signed for a transaction.
- `apps/edge/src/aitbc_edge/clients/blockchain_rpc.py` — Blockchain RPC client for Edge API Service
- `apps/blockchain-node/aitbc-blockchain-p2p-wrapper.py` — blockchain-p2p service wrapper
- `apps/gpu/src/gpu_service/services/edge_gpu_service.py` — Edge GPU service for managing GPU operations
- `Blockchain Node` exposes `GET /rpc/edge/info/{node_id}` (operation `get_edge_node_rpc_edge_info__node_id__get`) — Query edge node registration
- `Blockchain Node` exposes `GET /rpc/gpu/info/{gpu_id}` (operation `get_gpu_rpc_gpu_info__gpu_id__get`) — Query GPU registration
- `Blockchain Node` exposes `POST /rpc/edge/register` (operation `register_edge_node_rpc_edge_register_post`) — Register edge node on-chain
## Examples

- `POST /graphs/{graph_id}/nodes` (`contribute_knowledge` in `apps/coordinator-api/src/coordinator_api/contexts/knowledge/routers/knowledge.py`)
- `GET /graphs/{graph_id}/query` (`query_knowledge_graph` in `apps/coordinator-api/src/coordinator_api/contexts/knowledge/routers/knowledge.py`)
- `POST /join` (`join_island` in `apps/edge/src/aitbc_edge/routers/islands.py`)
- `POST /leave` (`leave_island` in `apps/edge/src/aitbc_edge/routers/islands.py`)
- `GET /` (`list_islands` in `apps/edge/src/aitbc_edge/routers/islands.py`)
- `GET /rpc/edge/info/{node_id}` (`get_edge_node_rpc_edge_info__node_id__get`) on `Blockchain Node`
- `GET /rpc/gpu/info/{gpu_id}` (`get_gpu_rpc_gpu_info__gpu_id__get`) on `Blockchain Node`
- `POST /rpc/edge/register` (`register_edge_node_rpc_edge_register_post`) on `Blockchain Node`
## Operational Notes
- **Status / Release:** `✅` / `v0.10.1`
