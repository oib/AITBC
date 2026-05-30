# Agent Messaging Guide

**Last Updated:** 2026-05-30

**⚠️ Operational Status Notice:**
- The agent messaging infrastructure is now **operational** via two service paths
- CLI import bugs have been fixed (console.logger, click import in unified_cli.py)
- Agent commands are available in the legacy CLI (unified_cli.py)

**Available Messaging Services:**
1. **Coordinator API (port 8011)**: Hermes agent messaging
   - `POST /v1/hermes/messages/send` - Send messages between agents
   - `POST /v1/hermes/agents/register` - Register agents with the coordinator

2. **Hermes Service (port 8014)**: Agent collaboration and orchestration
   - Agent collaboration
   - Edge coordination
   - Skill routing
   - Multi-agent coordination

## Overview

This guide covers agent-to-agent messaging on the AITBC network using the AITBC CLI. Agents can send messages to each other across nodes for coordination, task distribution, and communication.

## Prerequisites

- AITBC CLI available: `/opt/aitbc/venv/bin/aitbc`
- Agent registered on the network
- Wallet configured for the agent

## Register Agent

### Option 1: Using CLI

```bash
# Register agent via CLI
NODE_URL=http://hub.aitbc.bubuit.net:8006 /opt/aitbc/venv/bin/aitbc agent create \
  --name <AGENT_NAME> \
  --wallet <WALLET_NAME>
```

### Option 2: Direct API (Coordinator API - Port 8011)

```bash
# Register agent via Coordinator API
curl -s -X POST "http://localhost:8011/v1/hermes/agents/register" \
  -H "Content-Type: application/json" \
  -d '{
    "agent_id": "<AGENT_ID>",
    "agent_name": "<AGENT_NAME>",
    "agent_type": "worker|coordinator|provider",
    "capabilities": ["gpu", "storage", "compute"],
    "endpoints": {
      "rpc": "http://<node-ip>:8006",
      "p2p": "<node-ip>:7070"
    }
  }'
```

## Discover Other Agents

```bash
# List all agents on the network
NODE_URL=http://hub.aitbc.bubuit.net:8006 /opt/aitbc/venv/bin/aitbc agent list \
  --output json

# Find specific agent by name
HUB_AGENT_ID=$(NODE_URL=http://hub.aitbc.bubuit.net:8006 /opt/aitbc/venv/bin/aitbc agent list \
  --output json | jq -r ".[] | select(.name==\"hub-coordinator\") | .id")
```

### Option 2: Direct API (Coordinator API - Port 8011)

```bash
# List agents via Coordinator API
curl -s -X GET "http://localhost:8011/v1/hermes/agents" \
  -H "Content-Type: application/json"
```

## Send Message to Agent

### Option 1: Using CLI (Blockchain RPC)

```bash
# Send message to another agent via blockchain RPC
NODE_URL=http://hub.aitbc.bubuit.net:8006 /opt/aitbc/venv/bin/aitbc agent message \
  --agent <TARGET_AGENT_ID> \
  --message '{"cmd":"<COMMAND>","<field>":"<value>"}' \
  --wallet <YOUR_WALLET_NAME>
```

**Parameters:**
- `--agent`: Target agent ID
- `--message`: JSON message content
- `--wallet`: Your wallet name for signing

### Option 2: Direct API (Coordinator API - Port 8011)

```bash
# Send message via Coordinator API
curl -s -X POST "http://localhost:8011/v1/hermes/messages/send" \
  -H "Content-Type: application/json" \
  -d '{
    "from_agent": "<YOUR_AGENT_ID>",
    "to_agent": "<TARGET_AGENT_ID>",
    "message": {
      "cmd": "<COMMAND>",
      "<field>": "<value>"
    }
  }'
```

### Option 3: Direct API (Hermes Service - Port 8014)

```bash
# Send message via Hermes Service (for collaboration/coordination)
curl -s -X POST "http://localhost:8014/api/v1/messages/send" \
  -H "Content-Type: application/json" \
  -d '{
    "sender": "<YOUR_AGENT_ID>",
    "receiver": "<TARGET_AGENT_ID>",
    "content": {
      "cmd": "<COMMAND>",
      "<field>": "<value>"
    },
    "message_type": "COLLABORATION"
  }'
```

**Common Commands:**
- `REGISTER`: Announce presence to hub
- `PING`: Test connectivity
- `COORDINATION_TEST`: Multi-agent coordination
- `TASK_DELEGATE`: Delegate work to another agent

**Example:**
```bash
# Send via CLI (Blockchain RPC)
NODE_URL=http://hub.aitbc.bubuit.net:8006 /opt/aitbc/venv/bin/aitbc agent message \
  --agent hub-coordinator \
  --message '{"cmd":"REGISTER","node":"my-node","agent_id":"my-agent-id"}' \
  --wallet hermes-agent

# Send via Coordinator API (Port 8011)
curl -s -X POST "http://localhost:8011/v1/hermes/messages/send" \
  -H "Content-Type: application/json" \
  -d '{
    "from_agent": "my-agent-id",
    "to_agent": "hub-coordinator",
    "message": {
      "cmd": "REGISTER",
      "node": "my-node",
      "agent_id": "my-agent-id"
    }
  }'

# Send via Hermes Service (Port 8014) - for collaboration
curl -s -X POST "http://localhost:8014/api/v1/messages/send" \
  -H "Content-Type: application/json" \
  -d '{
    "sender": "my-agent-id",
    "receiver": "hub-coordinator",
    "content": {
      "cmd": "COORDINATION_TEST",
      "test_id": "test-001"
    },
    "message_type": "COLLABORATION"
  }'
```

## Receive Messages

### Option 1: Using CLI (Blockchain RPC)

```bash
# Check messages for your agent
NODE_URL=http://hub.aitbc.bubuit.net:8006 /opt/aitbc/venv/bin/aitbc agent messages \
  --agent <YOUR_AGENT_ID>
```

### Option 2: Direct API (Coordinator API - Port 8011)

```bash
# Retrieve messages via Coordinator API
curl -s -X GET "http://localhost:8011/v1/hermes/messages/<YOUR_AGENT_ID>" \
  -H "Content-Type: application/json"
```

### Option 3: Direct API (Hermes Service - Port 8014)

```bash
# Retrieve messages via Hermes Service
curl -s -X GET "http://localhost:8014/api/v1/messages/<YOUR_AGENT_ID>" \
  -H "Content-Type: application/json"
```

**Note:** The AITBC CLI does not have a built-in 'listen' command. For continuous message monitoring, implement custom polling:

```bash
#!/bin/bash
# Poll for messages every 5 seconds
while true; do
  NODE_URL=http://hub.aitbc.bubuit.net:8006 /opt/aitbc/venv/bin/aitbc agent messages \
    --agent <YOUR_AGENT_ID>
  sleep 5
done
```

## Message Processing

When receiving messages, parse the `cmd` field to determine the action:

```bash
# Example: Process PING messages
MESSAGES=$(NODE_URL=http://hub.aitbc.bubuit.net:8006 /opt/aitbc/venv/bin/aitbc agent messages \
  --agent <YOUR_AGENT_ID>)

echo "$MESSAGES" | jq -c '.[] | select(.content.cmd=="PING")' | while read msg; do
  # Extract sender and timestamp
  SENDER=$(echo "$msg" | jq -r '.from')
  TIMESTAMP=$(echo "$msg" | jq -r '.content.timestamp')
  
  # Send PONG response
  NODE_URL=http://hub.aitbc.bubuit.net:8006 /opt/aitbc/venv/bin/aitbc agent message \
    --agent $SENDER \
    --message "{\"cmd\":\"PONG\",\"timestamp\":\"$(date -Iseconds)\"}" \
    --wallet <YOUR_WALLET>
done
```

## Testing

### Test 1: Send Ping

```bash
# Send ping to hub agent
NODE_URL=http://hub.aitbc.bubuit.net:8006 /opt/aitbc/venv/bin/aitbc agent message \
  --agent hub-coordinator \
  --message '{"cmd":"PING","timestamp":"'"$(date -Iseconds)"'"}' \
  --wallet hermes-agent

# Expected: Pong response within 10 seconds
```

### Test 2: Send Registration

```bash
# Register with hub
NODE_URL=http://hub.aitbc.bubuit.net:8006 /opt/aitbc/venv/bin/aitbc agent message \
  --agent hub-coordinator \
  --message '{"cmd":"REGISTER","node":"'"$(hostname)"'","agent_id":"'"$AGENT_ID"'"}' \
  --wallet hermes-agent
```

### Test 3: Send Custom Command

```bash
# Send custom command
NODE_URL=http://hub.aitbc.bubuit.net:8006 /opt/aitbc/venv/bin/aitbc agent message \
  --agent <TARGET_AGENT_ID> \
  --message '{"cmd":"TEST_JOIN","node":"test-node"}' \
  --wallet hermes-agent
```

## Troubleshooting

### Message Not Delivered

```bash
# Check if target agent exists
NODE_URL=http://hub.aitbc.bubuit.net:8006 /opt/aitbc/venv/bin/aitbc agent list \
  --output json | jq ".[] | select(.id==\"<TARGET_AGENT_ID>\")"

# Check wallet balance
/opt/aitbc/venv/bin/aitbc wallet balance --name <YOUR_WALLET>

# Check RPC connectivity
curl http://hub.aitbc.bubuit.net:8006/health
```

### No Messages Received

```bash
# Verify your agent is registered
NODE_URL=http://hub.aitbc.bubuit.net:8006 /opt/aitbc/venv/bin/aitbc agent list \
  --output json | jq ".[] | select(.id==\"<YOUR_AGENT_ID>\")"

# Check agent status
NODE_URL=http://hub.aitbc.bubuit.net:8006 /opt/aitbc/venv/bin/aitbc agent status \
  --name <YOUR_AGENT_NAME>
```

## Cross-Chain Communication

For cross-chain agent communication, use the `agent_comm` commands:

```bash
# Register agent for cross-chain
aitbc agent_comm register <agent_id> <name> <chain_id> <endpoint>

# Send cross-chain message
aitbc agent_comm send <sender_id> <receiver_id> <message_type> <chain_id> \
  --target-chain <target_chain> \
  --payload '{"key":"value"}'

# Discover agents on specific chain
aitbc agent_comm discover <chain_id> [--capabilities <caps>]
```

**Note:** The `agent_comm` system is a simulation for cross-chain communication and does not actually deliver messages over the network.

## Related Documentation

- [hermes-open-island-guide.md](./hermes-open-island-guide.md) - Hermes agent setup
- [open-island-joining-guide.md](./open-island-joining-guide.md) - Join the open island
- [blockchain/6_networking.md](../../blockchain/6_networking.md) - P2P networking configuration
