# Get Agent Identity

Get agent identity information

- **Status**: ✅
- **Release**: —
## Implementation Details
- `apps/agent-coordinator/src/agent_app/routing/agent_discovery.py` — Agent Discovery and Registration System for AITBC Agent Coordination
- `apps/coordinator-api/src/coordinator_api/contexts/portfolio/domain/agent_portfolio.py` — Agent Portfolio Domain Models Domain models for agent portfolio management, trading strategies, and ...
- `apps/coordinator-api/src/coordinator_api/contexts/agent_identity/domain/agent_identity.py` — Agent Identity Domain Models for Cross-Chain Agent Identity Management Implements SQLModel definitio...
- `Blockchain Node` exposes `GET /rpc/identity/{agent_id}` (operation `get_agent_identity_route_rpc_identity__agent_id__get`) — Get agent identity
- `Coordinator API` exposes `GET /v1/agent-identity/identities/{agent_id}` (operation `get_agent_identity_v1_agent_identity_identities__agent_id__get`) — Get Agent Identity
- `Coordinator API` exposes `GET /v1/agent-identity/identities/{agent_id}/cross-chain/mapping` (operation `get_cross_chain_mapping_v1_agent_identity_identities__agent_id__cross_chain_mapping_get`) — Get Cross Chain Mapping
## Examples

- `GET /identities/{agent_id}` (`get_agent_identity` in `apps/coordinator-api/src/coordinator_api/contexts/agent_identity/routers/agent_identity.py`)
- `GET /identity/{agent_id}` (`get_agent_identity_route` in `apps/blockchain-node/src/aitbc_chain/rpc/routers/staking.py`)
- `GET /agents/{agent_id}/summary` (`get_trading_summary` in `apps/coordinator-api/src/coordinator_api/contexts/trading/routers/trading.py`)
- `GET /agents/{agent_wallet}/metrics` (`get_agent_metrics` in `apps/coordinator-api/src/coordinator_api/contexts/staking/routers/staking.py`)
- `GET /agents/{agent_wallet}/staking-pool` (`get_staking_pool` in `apps/coordinator-api/src/coordinator_api/contexts/staking/routers/staking.py`)
- `GET /rpc/identity/{agent_id}` (`get_agent_identity_route_rpc_identity__agent_id__get`) on `Blockchain Node`
- `GET /v1/agent-identity/identities/{agent_id}` (`get_agent_identity_v1_agent_identity_identities__agent_id__get`) on `Coordinator API`
- `GET /v1/agent-identity/identities/{agent_id}/cross-chain/mapping` (`get_cross_chain_mapping_v1_agent_identity_identities__agent_id__cross_chain_mapping_get`) on `Coordinator API`
## Operational Notes
- **Status / Release:** `✅` / `—`
