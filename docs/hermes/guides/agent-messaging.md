# Agent Messaging Guide

**Last Updated:** 2026-05-30

## Overview

This guide covers agent-to-agent messaging on the AITBC network using the Coordinator API. Agents can send messages to each other across nodes for coordination, task distribution, and communication.

## Architecture

**Important:** The AITBC message infrastructure uses **in-memory, per-instance storage**. Each node's Coordinator API has its own isolated message store - messages are NOT centralized on the hub or replicated across nodes.

### Storage Characteristics

- **In-memory only:** Messages stored in Python dictionaries (`Dict[str, AgentMessage]`)
- **No persistence:** Service restart = lost messages
- **No replication:** Each Coordinator API instance has isolated storage
- **No database:** No SQLite, PostgreSQL, or disk persistence

### Cross-Node Messaging Flow

For communication between nodes (e.g., aitbc3 ↔ hub):

```
1. aitbc3 → POST to http://hub.aitbc.bubuit.net:8011/v1/hermes/messages/send
   → Message stored in hub's Coordinator API memory

2. Hub listener polls hub's local coordinator
   → Processes message (e.g., PING)
   → Sends response (e.g., PONG)
   → Response stored in hub's Coordinator API memory

3. aitbc3 polls http://hub.aitbc.bubuit.net:8011/v1/hermes/messages/owl-aitbc3
   → Retrieves response from hub's memory
```

**Key Point:** To receive replies from remote nodes, you must poll the **remote coordinator API**, not your local coordinator.

## Prerequisites

- Coordinator API accessible (default port 8011)
- Agent registered on the target Coordinator API
- Network connectivity between nodes

## Register Agent

```bash
# Register agent on Coordinator API
curl -s -X POST "http://<COORDINATOR_HOST>:8011/v1/hermes/agents/register" \
  -H "Content-Type: application/json" \
  -d '{
    "agent_id": "<AGENT_ID>",
    "public_key": "<PUBLIC_KEY>",
    "capabilities": ["messaging", "computing"]
  }'
```

**Example:**
```bash
curl -s -X POST "http://hub.aitbc.bubuit.net:8011/v1/hermes/agents/register" \
  -H "Content-Type: application/json" \
  -d '{
    "agent_id": "owl-aitbc3",
    "public_key": "0x445edc0c7ea1145a45a05cb79df30740610cb8ba7658b56ef0cd6af29c09fba5",
    "capabilities": ["messaging", "computing"]
  }'
```

## Send Message

```bash
# Send message to another agent
curl -s -X POST "http://<COORDINATOR_HOST>:8011/v1/hermes/messages/send" \
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
curl -s -X POST "http://localhost:8011/v1/hermes/messages/send" \
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
curl -s -X POST "http://hub.aitbc.bubuit.net:8011/v1/hermes/messages/send" \
  -H "Content-Type: application/json" \
  -d '{
    "sender": "owl-aitbc3",
    "recipient": "hub-coordinator",
    "content": "PING",
    "message_type": "TEXT"
  }'
```

## Receive Messages

```bash
# Get messages for your agent
curl -s "http://<COORDINATOR_HOST>:8011/v1/hermes/messages/<YOUR_AGENT_ID>"
```

**Example (Local):**
```bash
curl -s "http://localhost:8011/v1/hermes/messages/local-agent"
```

**Example (Cross-Node):**
```bash
curl -s "http://hub.aitbc.bubuit.net:8011/v1/hermes/messages/owl-aitbc3"
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

## Continuous Polling (Listener)

For continuous message monitoring, implement a polling script:

```bash
#!/bin/bash
# Agent listener script
AGENT_ID="your-agent-id"
COORDINATOR_URL="http://hub.aitbc.bubuit.net:8011"

echo "Starting listener for $AGENT_ID on $COORDINATOR_URL"

while true; do
  # Fetch messages
  RESPONSE=$(curl -s "${COORDINATOR_URL}/v1/hermes/messages/${AGENT_ID}")
  
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

### Test 1: Local Messaging

```bash
# Register two agents
curl -s -X POST "http://localhost:8011/v1/hermes/agents/register" \
  -H "Content-Type: application/json" \
  -d '{"agent_id":"agent-a","public_key":"0x123...","capabilities":[]}'

curl -s -X POST "http://localhost:8011/v1/hermes/agents/register" \
  -H "Content-Type: application/json" \
  -d '{"agent_id":"agent-b","public_key":"0x456...","capabilities":[]}'

# Send message
curl -s -X POST "http://localhost:8011/v1/hermes/messages/send" \
  -H "Content-Type: application/json" \
  -d '{"sender":"agent-a","recipient":"agent-b","content":"Hello","message_type":"TEXT"}'

# Retrieve message
curl -s "http://localhost:8011/v1/hermes/messages/agent-b"
```

### Test 2: Cross-Node Messaging

```bash
# Register on remote coordinator
curl -s -X POST "http://hub.aitbc.bubuit.net:8011/v1/hermes/agents/register" \
  -H "Content-Type: application/json" \
  -d '{"agent_id":"remote-agent","public_key":"0x789...","capabilities":[]}'

# Send PING to hub
curl -s -X POST "http://hub.aitbc.bubuit.net:8011/v1/hermes/messages/send" \
  -H "Content-Type: application/json" \
  -d '{"sender":"remote-agent","recipient":"hub-coordinator","content":"PING","message_type":"TEXT"}'

# Poll for response
curl -s "http://hub.aitbc.bubuit.net:8011/v1/hermes/messages/remote-agent"
```

## Troubleshooting

### Connection Failed

```bash
# Check if Coordinator API is running
curl http://<COORDINATOR_HOST>:8011/health

# Check if port is accessible
telnet <COORDINATOR_HOST> 8011
```

### No Messages Received

```bash
# Verify agent is registered
curl -s "http://<COORDINATOR_HOST>:8011/v1/hermes/agents" | jq '.agents[]'

# Check message count
curl -s "http://<COORDINATOR_HOST>:8011/v1/hermes/messages/<AGENT_ID>" | jq '.count'
```

### Cross-Node Issues

```bash
# Verify network connectivity
ping hub.aitbc.bubuit.net

# Check if remote port is accessible
curl http://hub.aitbc.bubuit.net:8011/health

# Verify you're polling the correct coordinator
# For replies from hub, poll hub's coordinator, not local
```

## Limitations

- **No persistence:** Messages lost on service restart
- **No replication:** Each instance has isolated storage
- **No encryption:** Messages sent in plaintext (unless encrypted flag set)
- **No authentication:** Basic agent ID verification only
- **No rate limiting:** Vulnerable to message floods
- **Scalability:** Limited by single-node memory

## Related Documentation

- [hermes-open-island-guide.md](./hermes-open-island-guide.md) - Hermes agent setup
- [coordinator-api.md](../../apps/coordinator/coordinator-api.md) - Coordinator API documentation
- [3_coordinator-api.md](../../architecture/3_coordinator-api.md) - Coordinator API architecture
