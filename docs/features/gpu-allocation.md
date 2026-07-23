# GPU Allocation

Record GPU allocation/booking on-chain

- **Status**: ✅
- **Release**: —
## Implementation Details
- `apps/blockchain-node/src/aitbc_chain/state/gpu_resources.py` — GPU resource state models for blockchain tracking.
- `apps/blockchain-node/src/aitbc_chain/rpc/gpu_resources.py` — GPU resource RPC endpoints for AITBC blockchain.
- `apps/coordinator-api/src/coordinator_api/contexts/marketplace/routers/marketplace_gpu.py` — Get pricing engine instance
- `apps/gpu/src/gpu_service/domain/gpu_marketplace.py` — Persistent SQLModel tables for the GPU marketplace.
- `Blockchain Node` exposes `POST /rpc/gpu/register` (operation `register_gpu_rpc_gpu_register_post`) — Register GPU on-chain
- `Blockchain Node` exposes `POST /rpc/gpu/allocate` (operation `allocate_gpu_rpc_gpu_allocate_post`) — Allocate GPU on-chain
- `Blockchain Node` exposes `POST /rpc/edge/register` (operation `register_edge_node_rpc_edge_register_post`) — Register edge node on-chain
## Examples

- `POST /marketplace/gpu/{gpu_id}/confirm` (`confirm_gpu_booking` in `apps/coordinator-api/src/coordinator_api/contexts/marketplace/routers/marketplace_gpu.py`)
- `POST /join` (`join_island` in `apps/edge/src/aitbc_edge/routers/islands.py`)
- `POST /leave` (`leave_island` in `apps/edge/src/aitbc_edge/routers/islands.py`)
- `GET /` (`list_islands` in `apps/edge/src/aitbc_edge/routers/islands.py`)
- `GET /{island_id}` (`get_island` in `apps/edge/src/aitbc_edge/routers/islands.py`)
- `POST /rpc/gpu/register` (`register_gpu_rpc_gpu_register_post`) on `Blockchain Node`
- `POST /rpc/gpu/allocate` (`allocate_gpu_rpc_gpu_allocate_post`) on `Blockchain Node`
- `POST /rpc/edge/register` (`register_edge_node_rpc_edge_register_post`) on `Blockchain Node`
## Operational Notes
- **Status / Release:** `✅` / `—`
- Listens for on-chain events and propagates them to interested subscribers in real-time.
