# Hermes Agent Listener for AITBC Network - Working Solution

## Problem
The user wanted to implement a Hermes agent listener for the AITBC network that would:
1. Continuously poll for incoming messages
2. Parse messages for PING commands
3. Respond to PING messages with PONG responses

## Challenge
The `aitbc-cli agent message` and `aitbc-cli agent messages` commands were returning simulated responses rather than actually communicating with the backend services, making it impossible to build a functional listener using the CLI alone.

## Solution
We discovered that while the CLI commands were simulated, the underlying Coordinator API service was fully functional and provided real agent messaging capabilities. The solution uses the existing service infrastructure:

1. **Hermes Polling Daemon** (`/opt/aitbc/apps/agent-coordinator/scripts/hermes_polling_daemon.py`)
   - Polls Coordinator API for messages
   - Processes messages with configurable handlers
   - Built-in deduplication to prevent reprocessing
   - Handles PING/PONG automatically

2. **Agent Daemon Wrapper** (`/opt/aitbc/apps/agent-services/aitbc-agent-daemon-wrapper.py`)
   - Manages Hermes polling daemons via environment variables
   - Spawns polling processes for configured agent IDs
   - Integrates with systemd service

3. **Systemd Service** (`/opt/aitbc/apps/agent-services/aitbc-agent-daemon.service`)
   - Runs as a background service
   - Configured via environment variables
   - Auto-restart on failure

## Configuration
The service is configured in `/opt/aitbc/apps/agent-services/aitbc-agent-daemon.service`:
- `ENABLE_HERMES_POLLING=true` - Enable Hermes polling
- `HERMES_AGENT_IDS=owl-aitbc3` - Agent ID to poll for
- `HERMES_COORDINATOR_URL=http://hub.aitbc.bubuit.net:8011` - Hub coordinator endpoint

## Implementation Files
- `/opt/aitbc/apps/agent-coordinator/scripts/hermes_polling_daemon.py` - Python polling daemon
- `/opt/aitbc/apps/agent-services/aitbc-agent-daemon-wrapper.py` - Service wrapper
- `/opt/aitbc/apps/agent-services/aitbc-agent-daemon.service` - Systemd service unit

## Usage
To start the listener service:
```bash
systemctl daemon-reload
systemctl enable aitbc-agent-daemon
systemctl start aitbc-agent-daemon
```

To view logs:
```bash
journalctl -u aitbc-agent-daemon -f
```

To send a test PING message:
```bash
curl -s -X POST "http://hub.aitbc.bubuit.net:8011/v1/hermes/messages/send" \
  -H "Content-Type: application/json" \
  -d '{
    "sender": "test-agent",
    "recipient": "owl-aitbc3",
    "content": "PING",
    "message_type": "direct",
    "timestamp": "'$(date -Iseconds)'"
  }' | jq .
```

The daemon will automatically respond with a PONG message.

## Notes
- This solution uses the Coordinator API directly rather than the simulated aitbc-cli commands
- The daemon is designed to be lightweight and resilient, with error handling and retry logic
- All message exchanges are persisted and visible via the Coordinator API endpoints
- For multi-node setups, configure `HERMES_COORDINATOR_URL` to point to the hub coordinator