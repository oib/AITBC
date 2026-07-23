# Agent Messaging Contract

AITBC Agent Messaging Contract Implementation

## Implementation Details

- `MessageType` — Types of messages agents can send
- `MessageStatus` — Status of messages in the forum
- `Message` — Represents a message in the agent forum
- `Topic` — Represents a forum topic
- `AgentReputation` — Reputation system for agents
- `AgentMessagingContract` — Main contract for agent messaging functionality

## Examples

Python contract source: [`apps/blockchain-node/src/aitbc_chain/contracts/agent_messaging_contract.py`](../../apps/blockchain-node/src/aitbc_chain/contracts/agent_messaging_contract.py)

## Operational Notes

- This is an in-memory Python implementation used by the blockchain-node RPC layer.
- See [`docs/api/blockchain-node-openapi.json`](../../docs/api/blockchain-node-openapi.json) for related RPC endpoints.
