# AITBC Agent Coordinator - CLI Reference

**Last Updated:** 2026-08-13
**Version:** 2.0 (refreshed to current `aitbc` CLI)

The Agent Coordinator service runs on port **8107** and handles agent communication, presence, and message routing. Use the `aitbc` CLI (not a separate `aitbc-cli` binary) to interact with it.

For authoritative port configuration, see [Service Ports Reference](../reference/SERVICE_PORTS.md). For the full CLI, see [cli/README.md](../cli/README.md).

## Service control

The coordinator is a systemd service, not a subcommand:

```bash
sudo systemctl start aitbc-agent-coordinator.service
sudo systemctl status aitbc-agent-coordinator.service
```

## Agent SDK commands

These manage local agent configuration and registration via `aitbc agent`:

```bash
# Create a new agent configuration
aitbc agent create --name my-agent --type provider --auto-detect

# List local agent configs
aitbc agent list

# Show a specific agent's status
aitbc agent status --agent-id <agent-id>

# Show auto-detected capabilities
aitbc agent capabilities

# Register the agent with a coordinator
aitbc agent register --agent-id <agent-id> --coordinator-url http://localhost:8203
```

## Agent messaging commands

Use `aitbc agent-msg` for direct messaging through the Agent Coordinator (port 8107):

```bash
# Ping another agent and wait for a PONG reply
aitbc agent-msg ping \
  --agent hub-coordinator \
  --sender my-follower-agent \
  --coordinator-url http://hub.aitbc.bubuit.net:8107 \
  --timeout 10

# Send a message
aitbc agent-msg send "hello" --to-agent hub-coordinator

# Request free coins from a hub
aitbc agent-msg request-coins \
  --agent hub-coordinator \
  --sender my-agent \
  --wallet my-wallet \
  --coordinator-url http://hub.aitbc.bubuit.net:8107
```

## REST endpoints

The Agent Coordinator also exposes a small HTTP API on port 8107. Common paths:

```bash
# Register an agent directly
curl -X POST http://localhost:8107/api/v1/agents/register \
  -H "Content-Type: application/json" \
  -d '{"agent_id": "my-agent", "endpoint": "http://my-node:8107"}'

# Send a message
curl -X POST http://localhost:8107/api/v1/agent/messages/send \
  -H "Content-Type: application/json" \
  -d '{"from_agent": "my-agent", "to_agent": "hub-coordinator", "type": "ping"}'

# Poll messages for an agent
curl http://localhost:8107/api/v1/agent/messages/my-agent
```

## See also

- [apps/agent-coordinator/README.md](../../apps/agent-coordinator/README.md) — service status and architecture
- [Service Ports Reference](../reference/SERVICE_PORTS.md) — authoritative port assignments
- [CLI README](../cli/README.md) — full CLI command catalog
