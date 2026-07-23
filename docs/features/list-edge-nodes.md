# List Edge Nodes

List all registered edge nodes

- **Status**: ✅
- **Release**: v0.6.6
## Implementation Details
- `apps/gpu/src/gpu_service/services/edge_gpu_service.py` — Edge GPU service for managing GPU operations
- `apps/coordinator-api/src/coordinator_api/contexts/edge_gpu/routers/edge_gpu.py` — Edge GPU Router Handles edge GPU management endpoints
- `apps/coordinator-api/src/coordinator_api/contexts/edge_gpu/services/edge_gpu_service.py`
- `Marketplace` exposes `GET /v1/marketplace/edge-advertise` (operation `list_edge_nodes_v1_marketplace_edge_advertise_get`) — List Edge Nodes
- `Blockchain Node` exposes `GET /rpc/gpus` (operation `list_gpus_rpc_gpus_get`) — List all registered GPUs
- `Coordinator API` exposes `GET /v1/edge-gpu/profiles` (operation `list_profiles_v1_edge_gpu_profiles_get`) — List Profiles
## Examples

- `GET /graphs` (`list_knowledge_graphs` in `apps/coordinator-api/src/coordinator_api/contexts/knowledge/routers/knowledge.py`)
- `POST /graphs/{graph_id}/nodes` (`contribute_knowledge` in `apps/coordinator-api/src/coordinator_api/contexts/knowledge/routers/knowledge.py`)
- `GET /nodes` (`list_nodes` in `apps/coordinator-api/src/coordinator_api/contexts/agent_coordination/routers/swarm.py`)
- `POST /join` (`join_island` in `apps/edge/src/aitbc_edge/routers/islands.py`)
- `POST /leave` (`leave_island` in `apps/edge/src/aitbc_edge/routers/islands.py`)
- `GET /v1/marketplace/edge-advertise` (`list_edge_nodes_v1_marketplace_edge_advertise_get`) on `Marketplace`
- `GET /rpc/gpus` (`list_gpus_rpc_gpus_get`) on `Blockchain Node`
- `GET /v1/edge-gpu/profiles` (`list_profiles_v1_edge_gpu_profiles_get`) on `Coordinator API`
## Operational Notes
- **Status / Release:** `✅` / `v0.6.6`
- Handles task distribution, result collection, and edge-local caching.
