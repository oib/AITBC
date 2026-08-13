# Submit Evidence

Submit evidence for a dispute

- **Status**: ✅
- **Release**: —

## Implementation Details

- `apps/blockchain-node/src/aitbc_chain/models/dispute.py` — Dispute-related Pydantic models for RPC endpoints.
- `apps/blockchain-node/src/aitbc_chain/rpc/dispute_resolution_service.py` — Dispute Resolution Service Module
- `apps/blockchain-node/src/aitbc_chain/contracts/dispute_resolution.py` — Dispute Resolution Smart Contract Handles dispute filing, evidence submission, arbitration, and reso...
- `apps/coordinator-api/src/coordinator_api/contexts/governance/services/dispute_resolution.py` — Status of a dispute
- API endpoint `POST /evidence` implemented in `apps/coordinator-api/src/coordinator_api/contexts/governance/routers/disputes.py`
- `Blockchain Node` exposes `POST /rpc/disputes/evidence` (operation `submit_evidence_route_rpc_disputes_evidence_post`) — Submit evidence for a dispute
- `Blockchain Node` exposes `GET /rpc/disputes/{dispute_id}/evidence` (operation `get_dispute_evidence_route_rpc_disputes__dispute_id__evidence_get`) — Get evidence for a dispute
- `Coordinator API` exposes `POST /v1/disputes/evidence` (operation `submit_evidence_v1_disputes_evidence_post`) — Submit evidence

## Examples

- `POST /evidence` (`submit_evidence` in `apps/coordinator-api/src/coordinator_api/contexts/governance/routers/disputes.py`)
- `POST /evidence` (`submit_evidence_route` in `apps/blockchain-node/src/aitbc_chain/rpc/routers/disputes.py`)
- `GET /{dispute_id}/evidence` (`get_dispute_evidence_route` in `apps/blockchain-node/src/aitbc_chain/rpc/routers/disputes.py`)
- `POST /requests` (`submit_compute_request` in `apps/edge/src/aitbc_edge/routers/serve.py`)
- `GET /requests` (`list_compute_requests` in `apps/edge/src/aitbc_edge/routers/serve.py`)
- `POST /rpc/disputes/evidence` (`submit_evidence_route_rpc_disputes_evidence_post`) on `Blockchain Node`
- `GET /rpc/disputes/{dispute_id}/evidence` (`get_dispute_evidence_route_rpc_disputes__dispute_id__evidence_get`) on `Blockchain Node`
- `POST /v1/disputes/evidence` (`submit_evidence_v1_disputes_evidence_post`) on `Coordinator API`

## Operational Notes

- Feature status is `✅` (release `—`). Add operational notes as details become available.
