# File Dispute

File a new dispute for resolution

- **Status**: ✅
- **Release**: —

## Implementation Details

- `apps/coordinator-api/src/coordinator_api/contexts/governance/services/dispute_resolution.py` — Status of a dispute
- `apps/blockchain-node/src/aitbc_chain/contracts/dispute_resolution.py` — Dispute Resolution Smart Contract Handles dispute filing, evidence submission, arbitration, and reso...
- `apps/blockchain-node/src/aitbc_chain/rpc/dispute_resolution_service.py` — Dispute Resolution Service Module
- `apps/blockchain-node/src/aitbc_chain/models/dispute.py` — Dispute-related Pydantic models for RPC endpoints.
- `apps/wallet/scripts/import_file_wallets.py` — Import file-based wallets from ~/.aitbc/wallets/ into the wallet daemon.
- `Blockchain Node` exposes `POST /rpc/disputes/file` (operation `file_dispute_route_rpc_disputes_file_post`) — File a new dispute
- `Blockchain Node` exposes `POST /rpc/bridge/settlement/{escrow_id}/dispute` (operation `file_escrow_dispute_route_rpc_bridge_settlement__escrow_id__dispute_post`) — File a dispute for an escrow
- `Coordinator API` exposes `POST /v1/disputes/file` (operation `file_dispute_v1_disputes_file_post`) — File a dispute

## Examples

- `POST /file` (`file_dispute` in `apps/coordinator-api/src/coordinator_api/contexts/governance/routers/disputes.py`)
- `POST /{escrow_id}/dispute` (`file_escrow_dispute_route` in `apps/blockchain-node/src/aitbc_chain/rpc/routers/settlement.py`)
- `POST /file` (`file_dispute_route` in `apps/blockchain-node/src/aitbc_chain/rpc/routers/disputes.py`)
- `GET /v1/trading/requests` (`get_requests` in `apps/trading/src/trading_service/routers/legacy_trading.py`)
- `GET /v1/trading/requests/{request_id}` (`get_request` in `apps/trading/src/trading_service/routers/legacy_trading.py`)
- `POST /rpc/disputes/file` (`file_dispute_route_rpc_disputes_file_post`) on `Blockchain Node`
- `POST /rpc/bridge/settlement/{escrow_id}/dispute` (`file_escrow_dispute_route_rpc_bridge_settlement__escrow_id__dispute_post`) on `Blockchain Node`
- `POST /v1/disputes/file` (`file_dispute_v1_disputes_file_post`) on `Coordinator API`

## Operational Notes

- **Status / Release:** `✅` / `—`
