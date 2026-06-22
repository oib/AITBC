# Hermes Messaging Setup

This guide covers setting up PING/PONG messaging via the Agent Coordinator WebSocket service.

## Prerequisites

- Agent Coordinator running on the hub (port 8107)
- Nginx `/agent/` location configured with WebSocket upgrade headers (see `examples/nginx/nginx-aitbc.conf`)

## Test PING/PONG

From a follower node, use the CLI to ping the hub:

```bash
aitbc hermes ping --coordinator-url https://hub.aitbc.bubuit.net/agent
```

Expected output:
```
Connecting to wss://hub.aitbc.bubuit.net/agent/api/v1/agent/messages/stream?agent_id=follower
PING sent to hub-coordinator
PONG received from hub-coordinator
  content: PONG from hub-coordinator
  timestamp: 2026-06-22T...
```

No daemon, polling, or registration required — the Agent Coordinator's built-in `ping_handler` responds automatically over WebSocket.

## Verify Operation

```bash
# Check Agent Coordinator is running on the hub
curl http://hub.aitbc.bubuit.net/agent/health

# Check WebSocket status
curl http://hub.aitbc.bubuit.net/agent/api/v1/agent/ws/status
```

## See Also

- [Agent Messaging Guide](../../hermes/guides/agent-messaging.md)
- [Blockchain Setup](blockchain-setup.md)
- [Coin Requests](coin-requests.md)
- [Troubleshooting](../reference/troubleshooting.md)
