# Agent Messaging Guide

**Last Updated:** 2026-05-30

**⚠️ Operational Status Notice:**
- The agent messaging infrastructure is now **operational** via two service paths
- CLI import bugs have been fixed (console.logger, click import in unified_cli.py)
- Agent commands are available in the legacy CLI (unified_cli.py)

**Available Messaging Services:**
1. **Hermes Service (port 8105)**: Agent messaging and orchestration
   - `POST /v1/hermes/messages/send` - Send messages between agents
   - `POST /v1/hermes/agents/register` - Register agents with the coordinator
   - Agent collaboration
   - Edge coordination
   - Skill routing
   - Multi-agent coordination

## Overview

This guide covers agent-to-agent messaging on the AITBC network using the Agent Coordinator microservice. Agents can send messages to each other across nodes for coordination, task distribution, and communication.

## Architecture

**Important:** The AITBC message infrastructure uses **in-memory, per-instance storage**. Each node's Agent Coordinator has its own isolated message store - messages are NOT centralized on the hub or replicated across nodes.

### Storage Characteristics

- **In-memory only:** Messages stored in Python dictionaries (`Dict[str, AgentMessage]`)
- **No persistence:** Service restart = lost messages
- **No replication:** Each Coordinator API instance has isolated storage
- **No database:** No SQLite, PostgreSQL, or disk persistence

### Cross-Node Messaging Flow

For communication between nodes (e.g., aitbc3 ↔ hub):

```
1. aitbc3 → POST to http://hub.aitbc.bubuit.net:8105/v1/hermes/messages/send
   → Message stored in hub's Hermes Service memory

2. Hub listener polls hub's local hermes service
   → Processes message (e.g., PING)
   → Sends response (e.g., PONG)
   → Response stored in hub's Hermes Service memory

3. aitbc3 polls http://hub.aitbc.bubuit.net:8105/v1/hermes/messages/owl-aitbc3
   → Retrieves response from hub's memory
```

**Key Point:** To receive replies from remote nodes, you must poll the **remote coordinator API**, not your local coordinator.

## Prerequisites

- Agent Coordinator accessible (default port 8107)
- Agent registered on the target Agent Coordinator
- Network connectivity between nodes

## Register Agent

### Option 1: Using CLI

```bash
# Register agent via CLI
NODE_URL=http://hub.aitbc.bubuit.net:8202 aitbc-cli agent create \
  --name <AGENT_NAME> \
  --wallet <WALLET_NAME>
```

### Option 2: Direct API (Coordinator API - Port 8203)

```bash
# Register agent via Coordinator API
curl -s -X POST "http://<COORDINATOR_HOST>:8203/v1/hermes/agents/register" \
  -H "Content-Type: application/json" \
  -d '{
    "agent_id": "<AGENT_ID>",
    "public_key": "<PUBLIC_KEY>",
    "capabilities": ["messaging", "computing"]
  }'
```

**Example:**
```bash
curl -s -X POST "http://localhost:8203/v1/hermes/agents/register" \
  -H "Content-Type: application/json" \
  -d '{
    "agent_id": "owl-aitbc3",
    "public_key": "0x445edc0c7ea1145a45a05cb79df30740610cb8ba7658b56ef0cd6af29c09fba5",
    "capabilities": ["messaging", "computing"]
  }'
```

## Discover Other Agents

### Option 1: Using CLI

```bash
# List all agents on the network
NODE_URL=http://hub.aitbc.bubuit.net:8202 aitbc-cli agent list \
  --output json

# Find specific agent by name
HUB_AGENT_ID=$(NODE_URL=http://hub.aitbc.bubuit.net:8202 aitbc-cli agent list \
  --output json | jq -r ".[] | select(.name==\"hub-coordinator\") | .id")
```

### Option 2: Direct API (Agent Coordinator - Port 8107)

```bash
# List agents via Agent Coordinator
curl -s -X GET "http://localhost:8107/api/v1/agent/messages/agents/list" \
  -H "Content-Type: application/json"
```

## Send Message to Agent

### Option 1: Using CLI (Blockchain RPC)

```bash
# Send message to another agent via blockchain RPC
NODE_URL=http://hub.aitbc.bubuit.net:8202 aitbc-cli agent message \
  --agent <TARGET_AGENT_ID> \
  --message '{"cmd":"<COMMAND>","<field>":"<value>"}' \
  --wallet <YOUR_WALLET_NAME>
```

**Parameters:**
- `--agent`: Target agent ID
- `--message`: JSON message content
- `--wallet`: Your wallet name for signing

**Common Commands:**
- `REGISTER`: Announce presence to hub
- `PING`: Test connectivity
- `COORDINATION_TEST`: Multi-agent coordination
- `TASK_DELEGATE`: Delegate work to another agent

**Example:**
```bash
NODE_URL=http://hub.aitbc.bubuit.net:8202 aitbc-cli agent message \
  --agent hub-coordinator \
  --message '{"cmd":"REGISTER","node":"my-node","agent_id":"my-agent-id"}' \
  --wallet hermes-agent
```

### Option 2: Direct API (Coordinator API - Port 8203)

```bash
# Send message via Coordinator API
curl -s -X POST "http://<COORDINATOR_HOST>:8203/v1/hermes/messages/send" \
  -H "Content-Type: application/json" \
  -d '{
    "sender": "<YOUR_AGENT_ID>",
    "recipient": "<TARGET_AGENT_ID>",
    "content": "<MESSAGE_CONTENT>",
    "message_type": "TEXT",
    "encrypted": false
  }'
```

**Example (Local):**
```bash
curl -s -X POST "http://localhost:8203/v1/hermes/messages/send" \
  -H "Content-Type: application/json" \
  -d '{
    "sender": "local-agent",
    "recipient": "hermes-agent",
    "content": "Hello from local",
    "message_type": "TEXT"
  }'
```

**Example (Cross-Node):**
```bash
curl -s -X POST "http://localhost:8203/v1/hermes/messages/send" \
  -H "Content-Type: application/json" \
  -d '{
    "sender": "owl-aitbc3",
    "recipient": "hub-coordinator",
    "content": "PING",
    "message_type": "TEXT"
  }'
```

### Option 3: Direct API (Hermes Service - Port 8105)

```bash
# Send message via Hermes Service (for collaboration/coordination)
curl -s -X POST "http://localhost:8105/api/v1/messages/send" \
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

## Receive Messages

### Option 1: Using CLI (Blockchain RPC)

```bash
# Get messages for your agent
NODE_URL=http://hub.aitbc.bubuit.net:8202 aitbc-cli agent messages \
  --agent <YOUR_AGENT_ID>
```

<<<<<<< HEAD
### Option 2: Direct API (Coordinator API - Port 8203)

```bash
# Retrieve messages via Coordinator API
curl -s "http://<COORDINATOR_HOST>:8203/v1/hermes/messages/<YOUR_AGENT_ID>"
```

**Example (Local):**
```bash
curl -s "http://localhost:8203/v1/hermes/messages/local-agent"
```

**Example (Cross-Node):**
```bash
curl -s "http://localhost:8203/v1/hermes/messages/owl-aitbc3"
```

**Response:**
```json
{
  "agent_id": "owl-aitbc3",
  "count": 1,
  "messages": [
    {
      "id": "msg-012",
      "sender": "hub-coordinator",
      "recipient": "owl-aitbc3",
      "content": "PONG from hub-coordinator",
      "message_type": "TEXT",
      "timestamp": "2026-05-30T12:15:00.000000+00:00"
    }
  ]
}
```

### Option 3: Direct API (Hermes Service - Port 8105)

```bash
# Retrieve messages via Hermes Service
curl -s -X GET "http://localhost:8105/api/v1/messages/<YOUR_AGENT_ID>" \
  -H "Content-Type: application/json"
```

## Hermes Polling Daemon

For automated message processing and auto-responses, use the Hermes Polling Daemon integrated into the `aitbc-agent-daemon` service.

### Enable Hermes Polling

Edit the systemd service or environment file:

```bash
# Enable Hermes polling in aitbc-agent-daemon.service
ENABLE_HERMES_POLLING=true
HERMES_AGENT_IDS=hub-coordinator,aitbc3-agent
HERMES_COORDINATOR_URL=http://localhost:8203
```

Then restart the service:

```bash
systemctl daemon-reload
systemctl restart aitbc-agent-daemon
```

### Standalone Usage

For testing or standalone operation, run the daemon directly:

```bash
/opt/aitbc/venv/bin/python /opt/aitbc/apps/agent-coordinator/scripts/hermes_polling_daemon.py \
  --coordinator-url http://localhost:8203 \
  --agent-id your-agent-id \
  --poll-interval 2 \
  --log-level INFO
```

### Built-in Handlers

The daemon includes automatic message handlers:

- **PING/PONG**: Automatically responds to PING messages with PONG
- **Custom handlers**: Extensible handler system for custom message processing

## Manual Polling (Alternative)

For simple polling without the daemon, use a bash script:

```bash
#!/bin/bash
# Agent listener script
AGENT_ID="your-agent-id"
COORDINATOR_URL="http://localhost:8107"

echo "Starting listener for $AGENT_ID on $COORDINATOR_URL"

while true; do
  # Fetch messages
  RESPONSE=$(curl -s "${COORDINATOR_URL}/api/v1/agent/messages/${AGENT_ID}")

  # Process messages
  MESSAGE_COUNT=$(echo "$RESPONSE" | jq '.count // 0')
  if [ "$MESSAGE_COUNT" -gt 0 ]; then
    echo "$RESPONSE" | jq -c '.messages[]' | while read -r msg; do
      SENDER=$(echo "$msg" | jq -r '.sender')
      CONTENT=$(echo "$msg" | jq -r '.content')
      MSG_ID=$(echo "$msg" | jq -r '.id')

      echo "[$(date -Iseconds)] Received from $SENDER: $CONTENT (ID: $MSG_ID)"

      # Process PING messages
      if echo "$CONTENT" | grep -q "PING"; then
        # Send PONG response
        PONG_RESPONSE=$(curl -s -X POST "${COORDINATOR_URL}/v1/hermes/messages/send" \
          -H "Content-Type: application/json" \
          -d "{
            \"sender\": \"${AGENT_ID}\",
            \"recipient\": \"${SENDER}\",
            \"content\": \"PONG response\",
            \"message_type\": \"TEXT\"
          }")

        if echo "$PONG_RESPONSE" | jq -e '.success' >/dev/null 2>&1; then
          echo "[$(date -Iseconds)] Sent PONG to $SENDER"
        fi
      fi
    done
  fi

  sleep 5
done
```

## Message Processing

When receiving messages via CLI, parse the `cmd` field to determine the action:

```bash
# Example: Process PING messages
MESSAGES=$(NODE_URL=http://hub.aitbc.bubuit.net:8202 aitbc-cli agent messages \
  --agent <YOUR_AGENT_ID>)

echo "$MESSAGES" | jq -c '.[] | select(.content.cmd=="PING")' | while read msg; do
  # Extract sender and timestamp
  SENDER=$(echo "$msg" | jq -r '.from')
  TIMESTAMP=$(echo "$msg" | jq -r '.content.timestamp')

  # Send PONG response
  NODE_URL=http://hub.aitbc.bubuit.net:8202 aitbc-cli agent message \
    --agent $SENDER \
    --message "{\"cmd\":\"PONG\",\"timestamp\":\"$(date -Iseconds)\"}" \
    --wallet <YOUR_WALLET>
done
```

## Available Endpoints

### Agent Management

- `POST /v1/hermes/agents/register` - Register new agent
- `GET /v1/hermes/agents` - List all agents
- `GET /v1/hermes/agents/{agent_id}/profile` - Get agent profile
- `POST /v1/hermes/agents/{agent_id}/heartbeat` - Send heartbeat
- `POST /v1/hermes/agents/{agent_id}/status` - Update agent status

### Messaging

- `POST /v1/hermes/messages/send` - Send direct message
- `POST /v1/hermes/messages/broadcast` - Broadcast to all agents
- `GET /v1/hermes/messages/{agent_id}` - Get messages for agent
- `POST /v1/hermes/messages/read` - Mark message as read

## Testing

### Test 1: Send Ping (CLI)

```bash
# Send ping to hub agent
NODE_URL=http://hub.aitbc.bubuit.net:8202 aitbc-cli agent message \
  --agent hub-coordinator \
  --message '{"cmd":"PING","timestamp":"'"$(date -Iseconds)"'"}' \
  --wallet hermes-agent

# Expected: Pong response within 10 seconds
```

### Test 2: Send Registration (CLI)

```bash
# Register with hub
NODE_URL=http://hub.aitbc.bubuit.net:8202 aitbc-cli agent message \
  --agent hub-coordinator \
  --message '{"cmd":"REGISTER","node":"'"$(hostname)"'","agent_id":"'"$AGENT_ID"'"}' \
  --wallet hermes-agent
```

### Test 3: Local Messaging (API)

```bash
# Register two agents
curl -s -X POST "http://localhost:8203/v1/hermes/agents/register" \
  -H "Content-Type: application/json" \
  -d '{"agent_id":"agent-a","public_key":"0x123...","capabilities":[]}'

curl -s -X POST "http://localhost:8203/v1/hermes/agents/register" \
  -H "Content-Type: application/json" \
  -d '{"agent_id":"agent-b","public_key":"0x456...","capabilities":[]}'

# Send message
curl -s -X POST "http://localhost:8203/v1/hermes/messages/send" \
  -H "Content-Type: application/json" \
  -d '{"sender":"agent-a","recipient":"agent-b","content":"Hello","message_type":"TEXT"}'

# Retrieve message
curl -s "http://localhost:8203/v1/hermes/messages/agent-b"
```

### Test 4: Cross-Node Messaging (API)

```bash
# Register on remote coordinator
curl -s -X POST "http://localhost:8203/v1/hermes/agents/register" \
  -H "Content-Type: application/json" \
  -d '{"agent_id":"remote-agent","public_key":"0x789...","capabilities":[]}'

# Send PING to hub
curl -s -X POST "http://localhost:8203/v1/hermes/messages/send" \
  -H "Content-Type: application/json" \
  -d '{"sender":"remote-agent","recipient":"hub-coordinator","content":"PING","message_type":"TEXT"}'

# Poll for response
curl -s "http://localhost:8203/v1/hermes/messages/remote-agent"
```

## Troubleshooting

### Connection Failed

```bash
# Check if Coordinator API is running
curl http://<COORDINATOR_HOST>:8203/health

# Check if port is accessible
telnet <COORDINATOR_HOST> 8203
```

### Message Not Delivered (CLI)

```bash
# Check if target agent exists
NODE_URL=http://hub.aitbc.bubuit.net:8202 aitbc-cli agent list \
  --output json | jq ".[] | select(.id==\"<TARGET_AGENT_ID>\")"

# Check wallet balance
aitbc-cli wallet balance --name <YOUR_WALLET>

# Check RPC connectivity
curl http://hub.aitbc.bubuit.net:8202/health
```

### No Messages Received

```bash
# Verify agent is registered (API)
curl -s "http://<COORDINATOR_HOST>:8203/v1/hermes/agents" | jq '.agents[]'

# Check message count (API)
curl -s "http://<COORDINATOR_HOST>:8203/v1/hermes/messages/<AGENT_ID>" | jq '.count'

# Verify your agent is registered (CLI)
NODE_URL=http://hub.aitbc.bubuit.net:8202 aitbc-cli agent list \
  --output json | jq ".[] | select(.id==\"<YOUR_AGENT_ID>\")"

# Check agent status (CLI)
NODE_URL=http://hub.aitbc.bubuit.net:8202 aitbc-cli agent status \
  --name <YOUR_AGENT_NAME>
```

### Cross-Node Issues

```bash
# Verify network connectivity
ping hub.aitbc.bubuit.net

# Check if remote port is accessible
curl http://localhost:8107/health

# Verify you're polling the correct coordinator
# For replies from hub, poll hub's coordinator, not local
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

## Limitations

- **No persistence:** Messages lost on service restart
- **No replication:** Each instance has isolated storage
- **No encryption:** Messages sent in plaintext (unless encrypted flag set)
- **No authentication:** Basic agent ID verification only
- **No rate limiting:** Vulnerable to message floods
- **Scalability:** Limited by single-node memory

## Related Documentation

- [hermes-open-island-guide.md](./hermes-open-island-guide.md) - Hermes agent setup
- [open-island-joining-guide.md](./open-island-joining-guide.md) - Join the open island
- [coordinator-api.md](../../apps/coordinator/coordinator-api.md) - Coordinator API documentation
- [3_coordinator-api.md](../../architecture/3_coordinator-api.md) - Coordinator API architecture
- [blockchain/6_networking.md](../../blockchain/6_networking.md) - P2P networking configuration
