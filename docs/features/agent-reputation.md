# Agent Reputation

Get agent reputation from messaging contracts

- **Status**: ✅
- **Release**: —
## Implementation Details
- `apps/blockchain-node/src/aitbc_chain/rpc/contracts.py` — Derive a deterministic contract address from deployer, name, and timestamp. Similar to Ethereum's CR...
- `apps/blockchain-node/src/aitbc_chain/rpc/contracts_stub.py`
- `apps/blockchain-node/src/aitbc_chain/rpc/routers/contracts.py` — Contracts router.
- `apps/blockchain-node/src/aitbc_chain/contracts/agent_messaging_contract.py` — AITBC Agent Messaging Contract Implementation This module implements on-chain messaging functionalit...
- `apps/coordinator-api/src/coordinator_api/contexts/reputation/domain/reputation.py` — Agent Reputation and Trust System Domain Models Implements SQLModel definitions for agent reputation...
- `Blockchain Node` exposes `GET /rpc/contracts/messaging/agents/{agent_id}/reputation` (operation `get_agent_reputation_route_rpc_contracts_messaging_agents__agent_id__reputation_get`) — Get agent reputation
- `Blockchain Node` exposes `GET /rpc/contracts/messaging/state` (operation `get_messaging_contract_state_route_rpc_contracts_messaging_state_get`) — Get messaging contract state
- `Blockchain Node` exposes `GET /rpc/contracts/messaging/topics` (operation `get_forum_topics_route_rpc_contracts_messaging_topics_get`) — Get forum topics
## Examples

- `GET /messaging/agents/{agent_id}/reputation` (`get_agent_reputation_route` in `apps/blockchain-node/src/aitbc_chain/rpc/routers/contracts.py`)
- `GET /profile/{agent_id}` (`get_reputation_profile` in `apps/coordinator-api/src/coordinator_api/contexts/reputation/routers/reputation.py`)
- `GET /events/{agent_id}` (`get_reputation_events` in `apps/coordinator-api/src/coordinator_api/contexts/reputation/routers/reputation.py`)
- `GET /{agent_id}/cross-chain` (`get_cross_chain_reputation` in `apps/coordinator-api/src/coordinator_api/contexts/reputation/routers/reputation.py`)
- `GET /agents/{agent_id}/summary` (`get_trading_summary` in `apps/coordinator-api/src/coordinator_api/contexts/trading/routers/trading.py`)
- `GET /rpc/contracts/messaging/agents/{agent_id}/reputation` (`get_agent_reputation_route_rpc_contracts_messaging_agents__agent_id__reputation_get`) on `Blockchain Node`
- `GET /rpc/contracts/messaging/state` (`get_messaging_contract_state_route_rpc_contracts_messaging_state_get`) on `Blockchain Node`
- `GET /rpc/contracts/messaging/topics` (`get_forum_topics_route_rpc_contracts_messaging_topics_get`) on `Blockchain Node`
## Operational Notes
- **Status / Release:** `✅` / `—`
