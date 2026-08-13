# Register Agent Identity

Register agent identity on-chain

- **Status**: ✅
- **Release**: —

## Implementation Details

- `apps/coordinator-api/src/coordinator_api/contexts/agent_identity/routers/agent_identity.py` — Agent Identity API Router REST API endpoints for agent identity management and cross-chain operation...
- `apps/agent-coordinator/src/agent_app/routing/agent_discovery.py` — Agent Discovery and Registration System for AITBC Agent Coordination
- `apps/coordinator-api/src/coordinator_api/contexts/agent_identity/domain/agent_identity.py` — Agent Identity Domain Models for Cross-Chain Agent Identity Management Implements SQLModel definitio...
- `Coordinator API` exposes `POST /v1/agent-identity/identities/{agent_id}/cross-chain/register` (operation `register_cross_chain_identity_v1_agent_identity_identities__agent_id__cross_chain_register_post`) — Register Cross Chain Identity
- `Openapi` exposes `POST /v1/agent-identity/identities/{agent_id}/cross-chain/register` (operation `register_cross_chain_identity_v1_agent_identity_identities__agent_id__cross_chain_register_post`) — Register Cross Chain Identity
- `Blockchain Node` exposes `POST /rpc/identity/register` (operation `register_agent_identity_route_rpc_identity_register_post`) — Register agent identity

## Examples

- `POST /identities/{agent_id}/cross-chain/register` (`register_cross_chain_identity` in `apps/coordinator-api/src/coordinator_api/contexts/agent_identity/routers/agent_identity.py`)
- `POST /identities/{agent_id}/cross-chain/{chain_id}/verify` (`verify_cross_chain_identity` in `apps/coordinator-api/src/coordinator_api/contexts/agent_identity/routers/agent_identity.py`)
- `GET /identities/{agent_id}/resolve/{chain_id}` (`resolve_agent_identity` in `apps/coordinator-api/src/coordinator_api/contexts/agent_identity/routers/agent_identity.py`)
- `POST /identity/register` (`register_agent_identity_route` in `apps/blockchain-node/src/aitbc_chain/rpc/routers/staking.py`)
- `POST /v1/trading/chains/register` (`register_chain` in `apps/trading/src/trading_service/routers/inter_chain.py`)
- `POST /v1/agent-identity/identities/{agent_id}/cross-chain/register` (`register_cross_chain_identity_v1_agent_identity_identities__agent_id__cross_chain_register_post`) on `Coordinator API`
- `POST /v1/agent-identity/identities/{agent_id}/cross-chain/register` (`register_cross_chain_identity_v1_agent_identity_identities__agent_id__cross_chain_register_post`) on `Openapi`
- `POST /rpc/identity/register` (`register_agent_identity_route_rpc_identity_register_post`) on `Blockchain Node`

## Operational Notes

- **Status / Release:** `✅` / `—`
- Handles agent discovery, load balancing, and real-time messaging between agents.
