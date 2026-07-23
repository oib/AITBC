# Verify Evidence

Verify evidence (arbitrator only)

- **Status**: ✅
- **Release**: —
## Implementation Details
- API endpoint `POST /verify-evidence` implemented in `apps/blockchain-node/src/aitbc_chain/rpc/routers/disputes.py`
- API endpoint `POST /requests` implemented in `apps/edge/src/aitbc_edge/routers/serve.py`
- API endpoint `GET /requests` implemented in `apps/edge/src/aitbc_edge/routers/serve.py`
- API endpoint `GET /requests/{request_id}` implemented in `apps/edge/src/aitbc_edge/routers/serve.py`
- API endpoint `POST /requests/{request_id}/cancel` implemented in `apps/edge/src/aitbc_edge/routers/serve.py`
- `Blockchain Node` exposes `POST /rpc/disputes/verify-evidence` (operation `verify_evidence_route_rpc_disputes_verify_evidence_post`) — Verify evidence (arbitrator only)
- `Blockchain Node` exposes `POST /rpc/disputes/evidence` (operation `submit_evidence_route_rpc_disputes_evidence_post`) — Submit evidence for a dispute
- `Blockchain Node` exposes `POST /rpc/disputes/vote` (operation `submit_arbitration_vote_route_rpc_disputes_vote_post`) — Submit arbitration vote (arbitrator only)
## Examples

- `POST /verify-evidence` (`verify_evidence_route` in `apps/blockchain-node/src/aitbc_chain/rpc/routers/disputes.py`)
- `POST /requests` (`submit_compute_request` in `apps/edge/src/aitbc_edge/routers/serve.py`)
- `GET /requests` (`list_compute_requests` in `apps/edge/src/aitbc_edge/routers/serve.py`)
- `GET /requests/{request_id}` (`get_compute_request` in `apps/edge/src/aitbc_edge/routers/serve.py`)
- `POST /requests/{request_id}/cancel` (`cancel_compute_request` in `apps/edge/src/aitbc_edge/routers/serve.py`)
- `POST /rpc/disputes/verify-evidence` (`verify_evidence_route_rpc_disputes_verify_evidence_post`) on `Blockchain Node`
- `POST /rpc/disputes/evidence` (`submit_evidence_route_rpc_disputes_evidence_post`) on `Blockchain Node`
- `POST /rpc/disputes/vote` (`submit_arbitration_vote_route_rpc_disputes_vote_post`) on `Blockchain Node`
## Operational Notes
- Feature status is `✅` (release `—`). Add operational notes as details become available.
