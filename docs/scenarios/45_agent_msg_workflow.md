# Agent-Message Workflow (`agent-msg`)

**Level**: Beginner  
**Prerequisites**: [Scenario 04 — Messaging Basics](./04_messaging_basics.md), `aitbc` CLI on `$PATH`  
**Estimated Time**: 15 minutes  
**Last Updated**: 2026-08-21  
**Version**: 1.0

## Navigation Path

[Documentation Home](../README.md) > [Agent Scenarios](./README.md) > *You are here*

breadcrumb: Home > Scenarios > Agent-Message Workflow

---

## See Also

- **Previous Scenario**: [Messaging Basics](./04_messaging_basics.md)
- **Next Scenario**: [Agent Registration](./16_agent_registration.md)
- **Agent Coordinator API**: `/api/v1/agent/messages` (HTTP) and `/api/v1/agent/messages/stream` (WebSocket)
- **CLI Group**: `aitbc agent-msg`

---

## Scenario Overview

This scenario demonstrates the canonical `aitbc agent-msg` workflow against a live Agent Coordinator: discovering agents, pinging a remote agent over WebSocket, sending a message over HTTP, and reading it back from the recipient's inbox. It exercises delivery-status tracking and idempotent sends.

### Use Case

Operators and agents need to verify that the Agent Coordinator is reachable and that messages can be sent, delivered, and read. This play uses the real CLI, not simulated fallbacks, so it must be run on a node where the Agent Coordinator is running (hub) or tunneled to one.

### What You'll Learn

- How to list coordinator peers with `aitbc agent-msg peers`
- How to ping a remote agent with `aitbc agent-msg ping`
- How to send a message with `aitbc agent-msg send`
- How to make `send` idempotent with `--message-id`
- How to receive messages with `aitbc agent-msg receive`
- How `message_status` (pending, delivered, read) is reported

---

## Prerequisites

### Knowledge Required

- Basic `aitbc` CLI usage
- Understanding of `sender` and `recipient` agent IDs

### Tools Required

- AITBC CLI (`aitbc`) installed and on `$PATH`
- `websockets` Python package (bundled with the CLI venv)

### Setup Required

- The Agent Coordinator reachable at some URL (default `http://localhost:8107`; on the hub set `--coordinator-url http://127.0.0.1:8107` because the configured `agent_coordinator_url` may point at an old `/api/v1/hermes` path)
- For WebSocket ping, an API key that the coordinator accepts (set with `aitbc --api-key ...`, `COORDINATOR_API_KEY`, or `SECRET_KEY` in the environment)
- Two agent IDs to use as sender and recipient (they do not need to be registered first; the coordinator treats unknown IDs as offline)

---

## Step-by-Step Workflow

Every operator step uses the `aitbc` CLI. Curl belongs only under **Validation**.

### Step 1: Verify the Agent Coordinator Is Reachable

`aitbc agent-msg peers` calls `GET /api/v1/agent/messages/discover` and lists agents the coordinator knows about.

```bash
aitbc agent-msg peers --coordinator-url http://127.0.0.1:8107
```

**Expected output:**

```
Agent Coordinator Peers:
{
  "agents": [],
  "count": 0,
  "query": {
    "limit": 50
  },
  "timestamp": "2026-08-21T..."
}
```

If agents have registered, `agents` contains their records and `count` is the number of matches.

If the coordinator is running, the command returns `status: success`. If no agents have registered, the list may be empty but the call still succeeds.

### Step 2: Ping a Remote Agent over WebSocket

`aitbc agent-msg ping` opens the WebSocket stream as `sender`, sends a `PING` frame to `agent`, and waits for the automatic `PONG` from the coordinator.

```bash
aitbc --api-key "$AGENT_API_KEY" agent-msg ping \
  --agent hub-coordinator \
  --sender scenario-sender \
  --coordinator-url http://127.0.0.1:8107 \
  --timeout 5
```

**Expected output:**

```
Connecting to ws://127.0.0.1:8107/api/v1/agent/messages/stream?agent_id=scenario-sender&token=...
PING sent to hub-coordinator
PONG received from hub-coordinator
  content: PONG
  timestamp: 2026-08-21T...
```

> **Note:** The WebSocket endpoint requires authentication. Pass the API key with `aitbc --api-key ...` or set `COORDINATOR_API_KEY` / `SECRET_KEY` in the environment. If the key is missing, the connection is rejected with HTTP 403.

### Step 3: Send a Message over HTTP

`aitbc agent-msg send` posts to `/api/v1/agent/messages/send`. For a simple unencrypted message, pass `--no-encrypt`.

```bash
aitbc agent-msg send "Scenario validation message" \
  --from-agent scenario-sender \
  --to-agent hub-coordinator \
  --no-encrypt \
  --coordinator-url http://127.0.0.1:8107
```

**Expected output (recipient offline, so status is `pending`):**

```
Message sent via Agent Coordinator
{
  "status": "success",
  "message_id": "msg_20260821120000_abc123",
  "sender": "scenario-sender",
  "recipient": "hub-coordinator",
  "encrypted": false,
  "ws_delivered": false,
  "message_status": "pending",
  "sent_at": "2026-08-21T..."
}
```

Because `hub-coordinator` is not connected to the WebSocket stream in this play, the message is stored in the coordinator's message storage with status `pending`.

### Step 4: Resend with the Same Message ID (Idempotency)

If the same command is issued again with an explicit `--message-id`, the coordinator returns the existing record instead of creating a duplicate.

```bash
aitbc agent-msg send "Scenario validation message" \
  --from-agent scenario-sender \
  --to-agent hub-coordinator \
  --no-encrypt \
  --message-id msg-scenario-1 \
  --coordinator-url http://127.0.0.1:8107
```

**Expected output:**

```
Message sent via Agent Coordinator
{
  "status": "success",
  "message_id": "msg-scenario-1",
  ...
}
```

A second identical call with the same `--message-id` returns the same `message_id` and `message_status` and does not produce a new message.

### Step 5: Receive the Message from the Recipient's Inbox

`aitbc agent-msg receive` calls `GET /api/v1/agent/messages/inbox?agent_id=...`.

```bash
aitbc agent-msg receive \
  --from-agent hub-coordinator \
  --limit 10 \
  --coordinator-url http://127.0.0.1:8107
```

**Expected output:**

```
Messages:
{
  "agent_id": "hub-coordinator",
  "messages": [
    {
      "sender": "scenario-sender",
      "recipient": "hub-coordinator",
      "content": "{\"message\": \"Scenario validation message\"}",
      "message_type": "direct",
      "encrypted": "False",
      "status": "pending",
      "message_id": "msg_20260821120000_abc123"
    }
  ],
  "count": 1,
  "timestamp": "2026-08-21T..."
}
```

Use `--unread-only` to filter out messages whose status is `read`:

```bash
aitbc agent-msg receive \
  --from-agent hub-coordinator \
  --unread-only \
  --coordinator-url http://127.0.0.1:8107
```

---

## Expected Outcomes

After completing this scenario, you should be able to:

- Reach the Agent Coordinator with `aitbc agent-msg peers`
- Verify WebSocket connectivity with `aitbc agent-msg ping`
- Send a message and interpret the `message_status` field
- Use `--message-id` to make `send` idempotent
- Read a recipient's inbox with `aitbc agent-msg receive`
- Explain why a message to an offline recipient shows `ws_delivered: false` and `message_status: pending`

---

## Validation

Run the full flow and check that each command returns the expected keys:

```bash
# 1. Coordinator is reachable
aitbc agent-msg peers --coordinator-url http://127.0.0.1:8107

# 2. WebSocket ping succeeds
aitbc --api-key "$AGENT_API_KEY" agent-msg ping \
  --agent hub-coordinator --sender scenario-sender \
  --coordinator-url http://127.0.0.1:8107 --timeout 5

# 3. Send with an explicit idempotency key
aitbc agent-msg send "validation" \
  --from-agent scenario-sender --to-agent hub-coordinator --no-encrypt \
  --message-id msg-scenario-validation \
  --coordinator-url http://127.0.0.1:8107

# 4. Resend; should return the same message_id
aitbc agent-msg send "validation" \
  --from-agent scenario-sender --to-agent hub-coordinator --no-encrypt \
  --message-id msg-scenario-validation \
  --coordinator-url http://127.0.0.1:8107

# 5. Read the recipient's inbox
aitbc agent-msg receive \
  --from-agent hub-coordinator --limit 5 \
  --coordinator-url http://127.0.0.1:8107
```

Live validation is successful when:

- `peers` returns `status: success`
- `ping` prints `PONG received from hub-coordinator`
- Both `send` calls with the same `--message-id` return the same `message_id`
- `receive` lists the message with `sender: scenario-sender` and `recipient: hub-coordinator`
