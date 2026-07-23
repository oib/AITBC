# Message Moderation

Moderate messages in forums

- **Status**: ✅
- **Release**: —
## Implementation Details
- `apps/agent-coordinator/src/agent_app/storage/message_storage.py` — Message storage layer for persisting agent communication messages in Redis
- `apps/agent-coordinator/src/agent_app/routers/messages.py` — Request to send encrypted message
- `apps/agent-coordinator/src/agent_app/protocols/message_types.py` — Message Types and Routing System for AITBC Agent Coordination
- `apps/agent-coordinator/src/agent_app/encryption/message_encryption.py` — Message Encryption Module for AITBC Agent Coordinator Implements end-to-end message encryption using...
- API endpoint `POST /messaging/messages/{message_id}/moderate` implemented in `apps/blockchain-node/src/aitbc_chain/rpc/routers/contracts.py`
- `Blockchain Node` exposes `POST /rpc/contracts/messaging/messages/{message_id}/moderate` (operation `moderate_message_route_rpc_contracts_messaging_messages__message_id__moderate_post`) — Moderate message
- `Blockchain Node` exposes `POST /rpc/contracts/messaging/messages/post` (operation `post_message_route_rpc_contracts_messaging_messages_post_post`) — Post message
- `Blockchain Node` exposes `POST /rpc/contracts/messaging/messages/{message_id}/vote` (operation `vote_message_route_rpc_contracts_messaging_messages__message_id__vote_post`) — Vote on message
## Examples

- `POST /messaging/messages/{message_id}/moderate` (`moderate_message_route` in `apps/blockchain-node/src/aitbc_chain/rpc/routers/contracts.py`)
- `POST /messages/send` (`send_message` in `apps/coordinator-api/src/coordinator_api/contexts/agent_coordination/routers/agent_messaging.py`)
- `POST /messages/broadcast` (`broadcast` in `apps/coordinator-api/src/coordinator_api/contexts/agent_coordination/routers/agent_messaging.py`)
- `GET /messages/{agent_id}` (`get_messages` in `apps/coordinator-api/src/coordinator_api/contexts/agent_coordination/routers/agent_messaging.py`)
- `POST /messages/read` (`mark_read` in `apps/coordinator-api/src/coordinator_api/contexts/agent_coordination/routers/agent_messaging.py`)
- `POST /rpc/contracts/messaging/messages/{message_id}/moderate` (`moderate_message_route_rpc_contracts_messaging_messages__message_id__moderate_post`) on `Blockchain Node`
- `POST /rpc/contracts/messaging/messages/post` (`post_message_route_rpc_contracts_messaging_messages_post_post`) on `Blockchain Node`
- `POST /rpc/contracts/messaging/messages/{message_id}/vote` (`vote_message_route_rpc_contracts_messaging_messages__message_id__vote_post`) on `Blockchain Node`
## Operational Notes
- **Status / Release:** `✅` / `—`
