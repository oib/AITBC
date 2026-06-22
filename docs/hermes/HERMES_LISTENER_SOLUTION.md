# Hermes Agent Listener for AITBC Network

**Last Updated:** 2026-06-22

## Current Solution: WebSocket Ping/Pong

The Agent Coordinator (port 8107) has a built-in WebSocket handler that automatically responds to PING messages with PONG — no polling daemon required.

### How it works

1. Follower connects via WebSocket to `/api/v1/agent/messages/stream?agent_id=<follower_id>`
2. Follower sends `{"type": "message", "payload": {"content": "PING", "recipient_id": "hub-coordinator"}}`
3. Coordinator's `trigger_handlers()` matches "PING" and invokes `ping_handler`
4. `ping_handler` sends `{"type": "PONG", "content": "PONG from hub-coordinator"}` back over the WebSocket

### Usage

```bash
# From a follower node
aitbc hermes ping --coordinator-url https://hub.aitbc.bubuit.net/agent
```

### Implementation files

- `apps/agent-coordinator/src/app/websocket/agent_stream.py` — `ping_handler` function and `trigger_handlers` dispatcher
- `cli/aitbc_cli/commands/hermes.py` — `aitbc hermes ping` CLI command
- `examples/nginx/nginx-aitbc.conf` — nginx `/agent/` location with WebSocket upgrade headers

## Legacy: Blockchain-based Agent Daemon

The `agent_daemon.py` script (`aitbc-agent-daemon.service`) uses blockchain transactions for ping/pong. It polls the blockchain DB for transactions containing "ping" and replies with "pong" transactions. This is superseded by the WebSocket approach above.

- `apps/agent-coordinator/scripts/agent_daemon.py` — legacy blockchain-based listener
- `apps/agent-daemon/aitbc-agent-daemon.service` — systemd service file

The legacy daemon is still deployed but should not be used for new agent messaging. Use the WebSocket `aitbc hermes ping` command instead.
