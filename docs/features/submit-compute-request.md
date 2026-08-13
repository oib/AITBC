# Submit Compute Request

Submit compute request with optional payment verification

- **Status**: ✅
- **Release**: v0.6.6

## Implementation Details

- `aitbc/bridge/verification.py`
- `aitbc/crypto/payment_escrow.py` — Status of a payment escrow.
- `aitbc/middleware/request_id.py` — Request ID correlation middleware for structured logging
- `aitbc/models/coin_request.py` — Database schema for coin requests. Moved from hermes_service.storage.schema in v0.5.9 §1 to provide ...
- `Blockchain Node` exposes `POST /rpc/disputes/evidence` (operation `submit_evidence_route_rpc_disputes_evidence_post`) — Submit evidence for a dispute
- `Blockchain Node` exposes `POST /rpc/disputes/vote` (operation `submit_arbitration_vote_route_rpc_disputes_vote_post`) — Submit arbitration vote (arbitrator only)
- `Blockchain Node` exposes `POST /rpc/islands/bridge` (operation `request_bridge_route_rpc_islands_bridge_post`) — Request a bridge to another island

## Examples

- `POST /requests` (`submit_compute_request` in `apps/edge/src/aitbc_edge/routers/serve.py`)
- `GET /requests` (`list_compute_requests` in `apps/edge/src/aitbc_edge/routers/serve.py`)
- `GET /requests/{request_id}` (`get_compute_request` in `apps/edge/src/aitbc_edge/routers/serve.py`)
- `POST /requests/{request_id}/cancel` (`cancel_compute_request` in `apps/edge/src/aitbc_edge/routers/serve.py`)
- `GET /requests/{request_id}/result` (`get_compute_result` in `apps/edge/src/aitbc_edge/routers/serve.py`)
- `POST /rpc/disputes/evidence` (`submit_evidence_route_rpc_disputes_evidence_post`) on `Blockchain Node`
- `POST /rpc/disputes/vote` (`submit_arbitration_vote_route_rpc_disputes_vote_post`) on `Blockchain Node`
- `POST /rpc/islands/bridge` (`request_bridge_route_rpc_islands_bridge_post`) on `Blockchain Node`

## Operational Notes

- **Status / Release:** `✅` / `v0.6.6`
- Provides unified entry point with authentication, rate limiting, and request forwarding.
- This is the **actual product** — AITBC is a compute marketplace where providers offer GPU/compute resources and consumers pay for them using AIT coins.
