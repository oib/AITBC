# Verify Agent Identity

Verify agent identity

- **Status**: ✅
- **Release**: —
## Implementation Details
- `apps/coordinator-api/src/coordinator_api/contexts/agent_identity/domain/agent_identity.py` — Agent Identity Domain Models for Cross-Chain Agent Identity Management Implements SQLModel definitio...
- `apps/coordinator-api/src/coordinator_api/contexts/agent_identity/routers/agent_identity.py` — Agent Identity API Router REST API endpoints for agent identity management and cross-chain operation...
- `apps/coordinator-api/examples/agent_identity_sdk_example.py` — AITBC Agent Identity SDK Example Demonstrates basic usage of the Agent Identity SDK
- `Blockchain Node` exposes `POST /rpc/identity/verify` (operation `verify_agent_identity_route_rpc_identity_verify_post`) — Verify agent identity
- `Coordinator API` exposes `POST /v1/agent-identity/identities/{agent_id}/cross-chain/{chain_id}/verify` (operation `verify_cross_chain_identity_v1_agent_identity_identities__agent_id__cross_chain__chain_id__verify_post`) — Verify Cross Chain Identity
- `Coordinator API` exposes `POST /v1/agent-identity/identities/batch-verify` (operation `batch_verify_identities_v1_agent_identity_identities_batch_verify_post`) — Batch Verify Identities
## Examples

- `POST /identities/{agent_id}/cross-chain/{chain_id}/verify` (`verify_cross_chain_identity` in `apps/coordinator-api/src/coordinator_api/contexts/agent_identity/routers/agent_identity.py`)
- `POST /identity/verify` (`verify_agent_identity_route` in `apps/blockchain-node/src/aitbc_chain/rpc/routers/staking.py`)
- `POST /identities` (`create_agent_identity` in `apps/coordinator-api/src/coordinator_api/contexts/agent_identity/routers/agent_identity.py`)
- `GET /identities/{agent_id}` (`get_agent_identity` in `apps/coordinator-api/src/coordinator_api/contexts/agent_identity/routers/agent_identity.py`)
- `PUT /identities/{agent_id}` (`update_agent_identity` in `apps/coordinator-api/src/coordinator_api/contexts/agent_identity/routers/agent_identity.py`)
- `POST /rpc/identity/verify` (`verify_agent_identity_route_rpc_identity_verify_post`) on `Blockchain Node`
- `POST /v1/agent-identity/identities/{agent_id}/cross-chain/{chain_id}/verify` (`verify_cross_chain_identity_v1_agent_identity_identities__agent_id__cross_chain__chain_id__verify_post`) on `Coordinator API`
- `POST /v1/agent-identity/identities/batch-verify` (`batch_verify_identities_v1_agent_identity_identities_batch_verify_post`) on `Coordinator API`
## Operational Notes
- **Status / Release:** `✅` / `—`
- Handles agent discovery, load balancing, and real-time messaging between agents.
