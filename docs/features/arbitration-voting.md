# Arbitration Voting

Submit arbitration vote (arbitrator only)

- **Status**: ✅
- **Release**: —

## Implementation Details

- API endpoint `POST /vote` implemented in `apps/blockchain-node/src/aitbc_chain/rpc/routers/disputes.py`
- API endpoint `GET /{dispute_id}/votes` implemented in `apps/blockchain-node/src/aitbc_chain/rpc/routers/disputes.py`
- API endpoint `POST /requests` implemented in `apps/edge/src/aitbc_edge/routers/serve.py`
- API endpoint `GET /requests` implemented in `apps/edge/src/aitbc_edge/routers/serve.py`
- API endpoint `GET /requests/{request_id}` implemented in `apps/edge/src/aitbc_edge/routers/serve.py`
- `Blockchain Node` exposes `POST /rpc/disputes/vote` (operation `submit_arbitration_vote_route_rpc_disputes_vote_post`) — Submit arbitration vote (arbitrator only)
- `Coordinator API` exposes `POST /v1/disputes/vote` (operation `cast_vote_v1_disputes_vote_post`) — Cast arbitrator vote
- `Blockchain Node` exposes `POST /rpc/disputes/evidence` (operation `submit_evidence_route_rpc_disputes_evidence_post`) — Submit evidence for a dispute

## Examples

- `POST /vote` (`submit_arbitration_vote_route` in `apps/blockchain-node/src/aitbc_chain/rpc/routers/disputes.py`)
- `GET /{dispute_id}/votes` (`get_arbitration_votes_route` in `apps/blockchain-node/src/aitbc_chain/rpc/routers/disputes.py`)
- `POST /requests` (`submit_compute_request` in `apps/edge/src/aitbc_edge/routers/serve.py`)
- `GET /requests` (`list_compute_requests` in `apps/edge/src/aitbc_edge/routers/serve.py`)
- `GET /requests/{request_id}` (`get_compute_request` in `apps/edge/src/aitbc_edge/routers/serve.py`)
- `POST /rpc/disputes/vote` (`submit_arbitration_vote_route_rpc_disputes_vote_post`) on `Blockchain Node`
- `POST /v1/disputes/vote` (`cast_vote_v1_disputes_vote_post`) on `Coordinator API`
- `POST /rpc/disputes/evidence` (`submit_evidence_route_rpc_disputes_evidence_post`) on `Blockchain Node`

## Operational Notes

- **Status / Release:** `✅` / `—`
- Manages proposal lifecycle and vote tallying.
