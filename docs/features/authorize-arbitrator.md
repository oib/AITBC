# Authorize Arbitrator

Authorize an arbitrator (admin only)

- **Status**: ✅
- **Release**: —
## Implementation Details
- `apps/coordinator-api/src/coordinator_api/contexts/infrastructure/routers/admin.py` — Create a test miner for debugging marketplace sync
- API endpoint `POST /arbitrators/authorize` implemented in `apps/blockchain-node/src/aitbc_chain/rpc/routers/disputes.py`
- API endpoint `GET /arbitrators` implemented in `apps/blockchain-node/src/aitbc_chain/rpc/routers/disputes.py`
- API endpoint `POST /stake` implemented in `apps/coordinator-api/src/coordinator_api/contexts/staking/routers/staking.py`
- API endpoint `GET /stake/{stake_id}` implemented in `apps/coordinator-api/src/coordinator_api/contexts/staking/routers/staking.py`
- `Blockchain Node` exposes `POST /rpc/disputes/arbitrators/authorize` (operation `authorize_arbitrator_route_rpc_disputes_arbitrators_authorize_post`) — Authorize an arbitrator (admin only)
- `Blockchain Node` exposes `POST /rpc/disputes/verify-evidence` (operation `verify_evidence_route_rpc_disputes_verify_evidence_post`) — Verify evidence (arbitrator only)
- `Blockchain Node` exposes `POST /rpc/disputes/vote` (operation `submit_arbitration_vote_route_rpc_disputes_vote_post`) — Submit arbitration vote (arbitrator only)
## Examples

- `POST /arbitrators/authorize` (`authorize_arbitrator_route` in `apps/blockchain-node/src/aitbc_chain/rpc/routers/disputes.py`)
- `GET /arbitrators` (`get_authorized_arbitrators_route` in `apps/blockchain-node/src/aitbc_chain/rpc/routers/disputes.py`)
- `POST /stake` (`create_stake` in `apps/coordinator-api/src/coordinator_api/contexts/staking/routers/staking.py`)
- `GET /stake/{stake_id}` (`get_stake` in `apps/coordinator-api/src/coordinator_api/contexts/staking/routers/staking.py`)
- `GET /stakes` (`get_stakes` in `apps/coordinator-api/src/coordinator_api/contexts/staking/routers/staking.py`)
- `POST /rpc/disputes/arbitrators/authorize` (`authorize_arbitrator_route_rpc_disputes_arbitrators_authorize_post`) on `Blockchain Node`
- `POST /rpc/disputes/verify-evidence` (`verify_evidence_route_rpc_disputes_verify_evidence_post`) on `Blockchain Node`
- `POST /rpc/disputes/vote` (`submit_arbitration_vote_route_rpc_disputes_vote_post`) on `Blockchain Node`
## Operational Notes
- Feature status is `✅` (release `—`). Add operational notes as details become available.
