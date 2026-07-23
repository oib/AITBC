# Escrow Verification

Verify escrow payment before serving (job_id-based)

- **Status**: ✅
- **Release**: v0.10.1
## Implementation Details
- `apps/blockchain-node/src/aitbc_chain/contracts/escrow.py` — Smart Contract Escrow System Handles automated payment holding and release for AI job marketplace
- `apps/blockchain-node/src/aitbc_chain/rpc/escrow_routes.py` — Escrow RPC endpoints for the blockchain node. Provides create/release/refund/get endpoints backed by...
- `apps/coordinator-api/src/coordinator_api/contexts/infrastructure/domain/job.py` — Check if job is completed
- `Blockchain Node` exposes `POST /rpc/bridge/settlement/{escrow_id}/verify` (operation `verify_lock_route_rpc_bridge_settlement__escrow_id__verify_post`) — Verify lock proof
- `Blockchain Node` exposes `POST /rpc/escrow/create` (operation `create_escrow_rpc_escrow_create_post`) — Create escrow for a job
- `Blockchain Node` exposes `POST /rpc/escrow/{job_id}/release` (operation `release_escrow_rpc_escrow__job_id__release_post`) — Release escrow to provider
## Examples

- `GET /jobs/{job_id}/payment` (`get_job_payment` in `apps/coordinator-api/src/coordinator_api/contexts/payments/routers/payments.py`)
- `POST /{escrow_id}/verify` (`verify_lock_route` in `apps/blockchain-node/src/aitbc_chain/rpc/routers/settlement.py`)
- `POST /requests` (`submit_compute_request` in `apps/edge/src/aitbc_edge/routers/serve.py`)
- `GET /requests` (`list_compute_requests` in `apps/edge/src/aitbc_edge/routers/serve.py`)
- `GET /requests/{request_id}` (`get_compute_request` in `apps/edge/src/aitbc_edge/routers/serve.py`)
- `POST /rpc/bridge/settlement/{escrow_id}/verify` (`verify_lock_route_rpc_bridge_settlement__escrow_id__verify_post`) on `Blockchain Node`
- `POST /rpc/escrow/create` (`create_escrow_rpc_escrow_create_post`) on `Blockchain Node`
- `POST /rpc/escrow/{job_id}/release` (`release_escrow_rpc_escrow__job_id__release_post`) on `Blockchain Node`
## Operational Notes
- **Status / Release:** `✅` / `v0.10.1`
- Only GPUs are registered on-chain, not edge nodes themselves - ✅ v0.6.6 changelog calls for "Edge node registration with blockchain" - ✅ Fix: Add `EdgeNode` mod...
- **Verification**: `GET /rpc/sync/config` returns the active flag state (after service restart).
