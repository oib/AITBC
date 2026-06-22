# Agent Messaging Guide

**Last Updated:** 2026-06-22

## Overview

Agent-to-agent messaging on the AITBC network uses the **Agent Coordinator** microservice (port 8107) with WebSocket connections for real-time communication. The coordinator has built-in handlers that automatically respond to PING, HELLO, and REQUEST_COINS messages.

## Architecture

```
Follower                              Hub
  │                                    │
  │  WebSocket connect                 │
  │  ws(s)://hub/agent/api/v1/agent/   │
  │  messages/stream?agent_id=follower │
  │ ─────────────────────────────────> │
  │                                    │
  │  connection_established            │
  │ <───────────────────────────────── │
  │                                    │
  │  {"type":"message",                │
  │   "payload":{"content":"PING",     │
  │   "recipient_id":"hub-coordinator"}}│
  │ ─────────────────────────────────> │
  │                                    │
  │  trigger_handlers() matches PING   │
  │  ping_handler sends PONG           │
  │                                    │
  │  {"type":"PONG","content":"PONG..."}│
  │ <───────────────────────────────── │
  │                                    │
  │  handler_acknowledgment            │
  │ <───────────────────────────────── │
```

**Key design points:**
- WebSocket connection is the primary transport (not HTTP polling)
- The `agent_id` query parameter is self-declared — no registration required
- Built-in handlers respond automatically (PING→PONG, HELLO→greeting, REQUEST_COINS→approval)
- Messages are in-memory per coordinator instance (no persistence)

## Prerequisites

- Agent Coordinator running on the hub (port 8107)
- Nginx `/agent/` location proxying WebSocket to port 8107 (see `examples/nginx/nginx-aitbc.conf`)
- Network connectivity to the hub

## Ping a Remote Agent

### Using the CLI

```bash
# From a follower node, ping the hub's coordinator
aitbc hermes ping --coordinator-url https://hub.aitbc.bubuit.net/agent

# With custom agent/sender IDs
aitbc hermes ping \
  --agent hub-coordinator \
  --sender my-follower \
  --coordinator-url https://hub.aitbc.bubuit.net/agent \
  --timeout 10
```

**Expected output:**
```
Connecting to wss://hub.aitbc.bubuit.net/agent/api/v1/agent/messages/stream?agent_id=follower
PING sent to hub-coordinator
PONG received from hub-coordinator
  content: PONG from hub-coordinator
  timestamp: 2026-06-22T09:31:57.689218+00:00
```

**Options:**
| Option | Default | Description |
|--------|---------|-------------|
| `--agent` | `hub-coordinator` | Recipient agent ID to ping |
| `--sender` | `follower` | Your agent ID (self-declared) |
| `--coordinator-url` | from config | Agent Coordinator URL (direct: `http://localhost:8107`, via nginx: `https://hub.aitbc.bubuit.net/agent`) |
| `--timeout` | `10` | Seconds to wait for PONG reply |

### Using Python (minimal example)

```python
import asyncio, json, websockets

async def ping():
    uri = "wss://hub.aitbc.bubuit.net/agent/api/v1/agent/messages/stream?agent_id=my-follower"
    async with websockets.connect(uri) as ws:
        await ws.recv()  # consume connection_established

        await ws.send(json.dumps({
            "type": "message",
            "payload": {"content": "PING", "recipient_id": "hub-coordinator"}
        }))

        pong = json.loads(await ws.recv())
        print(pong["content"])  # "PONG from hub-coordinator"

asyncio.run(ping())
```

## Send Custom Messages

### Via WebSocket

```python
async with websockets.connect(uri) as ws:
    await ws.recv()  # connection_established

    await ws.send(json.dumps({
        "type": "message",
        "payload": {
            "content": "Hello from follower",
            "recipient_id": "hub-coordinator",
        }
    }))

    # Read responses
    while True:
        msg = json.loads(await ws.recv())
        print(msg)
```

### Via REST API (Agent Coordinator — Port 8107)

```bash
# Send a message
curl -s -X POST "http://localhost:8107/api/v1/agent/messages/send" \
  -H "Content-Type: application/json" \
  -d '{
    "sender": "my-follower",
    "recipient": "hub-coordinator",
    "content": {"text": "Hello"},
    "message_type": "direct",
    "encrypt": false
  }'

# Retrieve messages for an agent
curl -s "http://localhost:8107/api/v1/agent/messages/my-follower"
```

## Built-in Message Handlers

The Agent Coordinator automatically triggers handlers based on message content (case-insensitive substring match):

| Trigger | Handler | Response |
|---------|---------|----------|
| `PING` | `ping_handler` | Sends `{"type": "PONG", "content": "PONG from <recipient>"}` back to sender |
| `HELLO` | `hello_handler` | Sends greeting response back to sender |
| `REQUEST_COINS` | `request_coins_handler` | Processes coin request and sends approval/rejection |

Handlers are registered at startup in `apps/agent-coordinator/src/app/websocket/agent_stream.py`.

## WebSocket Endpoints

| Endpoint | Protocol | Description |
|----------|----------|-------------|
| `/api/v1/agent/messages/stream?agent_id=<ID>` | WebSocket | Real-time message stream with handler triggering |
| `/api/v1/agent/presence/stream?agent_id=<ID>` | WebSocket | Real-time presence tracking |
| `/api/v1/agent/ws/status` | GET | WebSocket listener status (active connections, registered handlers) |

## Nginx Configuration

The hub's nginx must proxy WebSocket connections to port 8107 with upgrade headers:

```nginx
upstream agent_coordinator {
    server localhost:8107;
}

location /agent/ {
    proxy_pass http://agent_coordinator/;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
    # WebSocket support
    proxy_http_version 1.1;
    proxy_set_header Upgrade $http_upgrade;
    proxy_set_header Connection "upgrade";
    proxy_read_timeout 86400s;
}
```

See `examples/nginx/nginx-aitbc.conf` for the complete configuration.

## Troubleshooting

### Connection Failed

```bash
# Check if Agent Coordinator is running on the hub
curl http://hub.aitbc.bubuit.net/agent/health

# Check WebSocket status endpoint
curl http://hub.aitbc.bubuit.net/agent/api/v1/agent/ws/status
```

### No PONG Received

```bash
# Verify the agent-coordinator service is running
ssh hub 'systemctl status aitbc-agent-coordinator'

# Test with explicit timeout
aitbc hermes ping --coordinator-url https://hub.aitbc.bubuit.net/agent --timeout 15

# Check if nginx is proxying WebSocket correctly
curl -v -H "Upgrade: websocket" -H "Connection: Upgrade" \
  https://hub.aitbc.bubuit.net/agent/api/v1/agent/ws/status
```

### Port Reference

| Service | Port | Access |
|---------|------|--------|
| Agent Coordinator | 8107 | Direct (localhost) or via nginx `/agent/` |
| Coordinator API (mock Hermes) | 8203 | Debug/mock only — no PONG handler in production |
| Hermes Service | 8103 | Internal — handler registry for REST-based processing |
| Blockchain RPC | 8202 | Public via nginx `/rpc/` |

**Note:** The Coordinator API's `/v1/hermes/messages/send` endpoint (port 8203) is **mock-only** — it only exists when `DEBUG=true` or `ENABLE_MOCK_HERMES=true`. It has no PONG handler. Use the Agent Coordinator WebSocket (port 8107) for ping/pong.
