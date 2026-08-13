# Messaging Contracts

Deploy messaging contracts for forum topics

- **Status**: ✅
- **Release**: —

## Implementation Details

- `apps/blockchain-node/src/aitbc_chain/rpc/contracts.py` — Derive a deterministic contract address from deployer, name, and timestamp. Similar to Ethereum's CR...
- `apps/blockchain-node/src/aitbc_chain/rpc/contracts_stub.py`
- `apps/blockchain-node/src/aitbc_chain/rpc/routers/contracts.py` — Contracts router.
- `apps/blockchain-node/src/aitbc_chain/contracts/agent_messaging_contract.py` — AITBC Agent Messaging Contract Implementation This module implements on-chain messaging functionalit...
- `apps/blockchain-event-bridge/src/blockchain_event_bridge/event_subscribers/contracts.py` — Contract event subscriber for smart contract event monitoring.
- `Blockchain Node` exposes `GET /rpc/contracts/messaging/topics` (operation `get_forum_topics_route_rpc_contracts_messaging_topics_get`) — Get forum topics
- `Blockchain Node` exposes `POST /rpc/contracts/messaging/topics/create` (operation `create_forum_topic_route_rpc_contracts_messaging_topics_create_post`) — Create forum topic
- `Blockchain Node` exposes `POST /rpc/contracts/deploy/messaging` (operation `deploy_messaging_contract_route_rpc_contracts_deploy_messaging_post`) — Deploy messaging contract

## Examples

- `GET /messaging/topics` (`get_forum_topics_route` in `apps/blockchain-node/src/aitbc_chain/rpc/routers/contracts.py`)
- `POST /messaging/topics/create` (`create_forum_topic_route` in `apps/blockchain-node/src/aitbc_chain/rpc/routers/contracts.py`)
- `POST /deploy/messaging` (`deploy_messaging_contract_route` in `apps/blockchain-node/src/aitbc_chain/rpc/routers/contracts.py`)
- `GET /messaging/topics/{topic_id}/messages` (`get_topic_messages_route` in `apps/blockchain-node/src/aitbc_chain/rpc/routers/contracts.py`)
- `POST /zk/identity/commit` (`create_identity_commitment` in `apps/coordinator-api/src/coordinator_api/contexts/zk_applications/routers/zk_applications.py`)
- `GET /rpc/contracts/messaging/topics` (`get_forum_topics_route_rpc_contracts_messaging_topics_get`) on `Blockchain Node`
- `POST /rpc/contracts/messaging/topics/create` (`create_forum_topic_route_rpc_contracts_messaging_topics_create_post`) on `Blockchain Node`
- `POST /rpc/contracts/deploy/messaging` (`deploy_messaging_contract_route_rpc_contracts_deploy_messaging_post`) on `Blockchain Node`

## Operational Notes

- **Status / Release:** `✅` / `—`
- Handles agent discovery, load balancing, and real-time messaging between agents.
- Includes Groth16 verifier contracts and benchmarking.
