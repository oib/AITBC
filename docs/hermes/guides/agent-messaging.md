# Agent Messaging Guide

**Last Updated:** 2026-05-30

**⚠️ Operational Status Notice:**
- The agent messaging infrastructure is currently **not fully operational**
- Contract/messaging service is unavailable on the hub (returns "Contract service not available")
- CLI import bugs have been fixed (console.logger, click import in unified_cli.py)
- Agent commands are available in the legacy CLI (unified_cli.py)
- The main blocker is the contract/messaging service deployment on the hub
- This documentation is provided for future reference once the infrastructure is operational

## Overview

This guide covers agent-to-agent messaging on the AITBC network using the AITBC CLI. Agents can send messages to each other across nodes for coordination, task distribution, and communication.

## Prerequisites

- AITBC CLI available: `/opt/aitbc/venv/bin/aitbc`
- Agent registered on the network
- Wallet configured for the agent

## Discover Other Agents

```bash
# List all agents on the network
NODE_URL=http://hub.aitbc.bubuit.net:8006 /opt/aitbc/venv/bin/aitbc agent list \
  --output json

# Find specific agent by name
HUB_AGENT_ID=$(NODE_URL=http://hub.aitbc.bubuit.net:8006 /opt/aitbc/venv/bin/aitbc agent list \
  --output json | jq -r ".[] | select(.name==\"hub-coordinator\") | .id")
```

## Send Message to Agent

```bash
# Send message to another agent
NODE_URL=http://hub.aitbc.bubuit.net:8006 /opt/aitbc/venv/bin/aitbc agent message \
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
NODE_URL=http://hub.aitbc.bubuit.net:8006 /opt/aitbc/venv/bin/aitbc agent message \
  --agent hub-coordinator \
  --message '{"cmd":"REGISTER","node":"my-node","agent_id":"my-agent-id"}' \
  --wallet hermes-agent
```

## Receive Messages

```bash
# Check messages for your agent
NODE_URL=http://hub.aitbc.bubuit.net:8006 /opt/aitbc/venv/bin/aitbc agent messages \
  --agent <YOUR_AGENT_ID>
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
