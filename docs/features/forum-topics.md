# Forum Topics

Create topics, post messages, vote on messages

- **Status**: ✅
- **Release**: —

## Implementation Details

- `apps/agent-coordinator/src/agent_app/routers/messages.py` — Request to send encrypted message
- `apps/blockchain-node/create_genesis.py` — Simple script to create genesis block
- `apps/blockchain-node/create_enhanced_genesis.py` — Enhanced script to create genesis block with new features
- `apps/blockchain-node/scripts/create_bootstrap_genesis.py` — Generate a genesis file with initial distribution for the exchange economy.
- `apps/blockchain-node/scripts/create_genesis_wallet.py` — Create genesis wallet with secure random secp256k1 private key
- `Blockchain Node` exposes `POST /rpc/contracts/messaging/topics/create` (operation `create_forum_topic_route_rpc_contracts_messaging_topics_create_post`) — Create forum topic
- `Blockchain Node` exposes `POST /rpc/contracts/messaging/messages/{message_id}/vote` (operation `vote_message_route_rpc_contracts_messaging_messages__message_id__vote_post`) — Vote on message
- `Blockchain Node` exposes `POST /rpc/disputes/vote` (operation `submit_arbitration_vote_route_rpc_disputes_vote_post`) — Submit arbitration vote (arbitrator only)

## Examples

- `POST /messaging/topics/create` (`create_forum_topic_route` in `apps/blockchain-node/src/aitbc_chain/rpc/routers/contracts.py`)
- `POST /platform/posts` (`create_community_post` in `apps/coordinator-api/src/coordinator_api/contexts/community/routers/community.py`)
- `POST /platform/posts/{post_id}/upvote` (`upvote_community_post` in `apps/coordinator-api/src/coordinator_api/contexts/community/routers/community.py`)
- `GET /messaging/topics` (`get_forum_topics_route` in `apps/blockchain-node/src/aitbc_chain/rpc/routers/contracts.py`)
- `GET /messaging/topics/{topic_id}/messages` (`get_topic_messages_route` in `apps/blockchain-node/src/aitbc_chain/rpc/routers/contracts.py`)
- `POST /rpc/contracts/messaging/topics/create` (`create_forum_topic_route_rpc_contracts_messaging_topics_create_post`) on `Blockchain Node`
- `POST /rpc/contracts/messaging/messages/{message_id}/vote` (`vote_message_route_rpc_contracts_messaging_messages__message_id__vote_post`) on `Blockchain Node`
- `POST /rpc/disputes/vote` (`submit_arbitration_vote_route_rpc_disputes_vote_post`) on `Blockchain Node`

## Operational Notes

- **Status / Release:** `✅` / `—`
- Manages proposal lifecycle and vote tallying.
