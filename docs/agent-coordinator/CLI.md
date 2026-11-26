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

# Register the agent with the Agent Coordinator (port 8107 — registration
# hits /v1/agents/register there; coordinator-api on 8203 has no such route)
aitbc agent register --agent-id <agent-id> --coordinator-url http://localhost:8107
```

## Agent messaging commands

Use `aitbc agent-msg` for direct messaging through the Agent Coordinator (port 8107):

```bash
# Ping another agent and wait for a PONG reply
aitbc agent-msg ping \
  --agent hub-coordinator \
  --sender my-follower-agent \
  --coordinator-url https://hub.example.net/agent \
  --timeout 10

# Send a message
aitbc agent-msg send "hello" --to-agent hub-coordinator

# Request free coins from a hub
aitbc agent-msg request-coins \
  --sender my-agent \
  --wallet my-wallet \
  --coordinator-url https://hub.example.net/agent
```

## agent-comm commands

`aitbc agent-comm` manages the agent registry (`/v1/agents/*`) and the
message inbox. Registry reads (`list`, `discover`, `status`, `network`)
and the inbox (`receive`) are **principal-gated** — an anonymous call gets
HTTP 401 with a credential hint (#2980/#2984). Authenticate with any of:

```bash
# Signed agent read: the wallet's X-Agent-* headers authenticate as
# --signing-agent-id (must be registered + bound to that wallet)
aitbc agent-comm list --wallet <wallet> --signing-agent-id <agent-id>

# Or a session/operator credential
aitbc --api-key <JWT> agent-comm list
aitbc auth login   # stored JWT is picked up automatically
```

Wallet passwords for non-interactive signing legs resolve through the
standard chain: `--password-file`/`--password` → `AITBC_WALLET_PASSWORD_FILE`
→ `AITBC_WALLET_PASSWORD_<NAME>`/`AITBC_WALLET_PASSWORD` → keyring/TTY —
see [docs/cli/README.md](../cli/README.md) ("Wallet password input"). On
fleet nodes provision `AITBC_WALLET_PASSWORD_FILE` (or the per-wallet env)
rather than relying on a TTY prompt.

`agent-task hire` needs no manual registration: its implicit
`buyer-<host>` agent self-registers bound to the signing wallet on first
use (#2983).

## REST endpoints

The Agent Coordinator also exposes a small HTTP API on port 8107. Common paths:

```bash
# Register an agent directly (endpoints is a name→URL map; in enforce mode
# identity_address/identity_proof/identity_nonce/registered_at are required)
curl -X POST http://localhost:8107/v1/agents/register \
  -H "Content-Type: application/json" \
  -d '{"agent_id": "my-agent", "agent_type": "general", "endpoints": {"messages": "http://my-node:8107"}}'

# Send a message
curl -X POST http://localhost:8107/api/v1/agent/messages/send \
  -H "Content-Type: application/json" \
  -d '{"sender": "my-agent", "recipient": "hub-coordinator", "content": {"text": "ping"}, "message_type": "direct"}'

# Poll messages for an agent
curl http://localhost:8107/api/v1/agent/messages/my-agent
```

## See also

- [apps/agent-coordinator/README.md](../../apps/agent-coordinator/README.md) — service status and architecture
- [Service Ports Reference](../reference/SERVICE_PORTS.md) — authoritative port assignments
- [CLI README](../cli/README.md) — full CLI command catalog
