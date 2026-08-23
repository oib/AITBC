# AITBC MCP server

A [Model Context Protocol][mcp] (MCP) server that lets Devin operate the AITBC
live nodes (`aitbc3` and `hub.aitbc`) through natural-language tool calls.

[mcp]: https://modelcontextprotocol.io

## What it can do

| Capability | Tools |
|------------|-------|
| Run an AITBC node | `start_node`, `stop_node`, `restart_node` |
| Get status | `list_nodes`, `node_status`, `get_service_health`, `get_chain_height`, `get_block` |
| Triggers | `get_trigger_status`, `list_rebalance_triggers` |
| Actions | `run_aitbc_command` |
| Cron jobs | `list_cron_jobs`, `run_cron_job` |

All destructive tools default to `dry_run=true` and require `confirm=true` before
they actually run a command on a remote host.

## Installation

On the machine that will host the MCP server:

```bash
cd /opt/aitbc/mcp-server
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Devin configuration

Add the server to your Devin project or user config:

```json
{
  "mcpServers": {
    "aitbc": {
      "command": "/opt/aitbc/mcp-server/.venv/bin/python",
      "args": ["/opt/aitbc/mcp-server/aitbc_mcp_server.py"],
      "env": {
        "AITBC_MCP_SSH_USER": "oib",
        "AITBC_MCP_LOG_LEVEL": "INFO"
      }
    }
  }
}
```

Save project config as `.devin/mcp_config.json` and user secrets in
`.devin/mcp_config.local.json`.

### Local IDE (while developing)

```json
{
  "mcpServers": {
    "aitbc": {
      "command": "/home/oib/windsurf/aitbc/.venv-mcp/bin/python",
      "args": ["/home/oib/windsurf/aitbc/mcp-server/aitbc_mcp_server.py"],
      "env": {
        "AITBC_MCP_LOG_LEVEL": "INFO"
      }
    }
  }
}
```

## Permissions

Recommended `.devin/config.json`:

```json
{
  "permissions": {
    "allow": [
      "mcp__aitbc__list_*",
      "mcp__aitbc__get_*",
      "mcp__aitbc__node_status",
      "mcp__aitbc__get_service_health"
    ],
    "ask": [
      "mcp__aitbc__start_node",
      "mcp__aitbc__stop_node",
      "mcp__aitbc__restart_node",
      "mcp__aitbc__run_cron_job",
      "mcp__aitbc__run_aitbc_command"
    ],
    "deny": []
  }
}
```

## Requirements

* The MCP host (Devin) must be able to reach `aitbc3` and `hub.aitbc` via
  passwordless SSH.
* The SSH user must be able to run `sudo -n /opt/aitbc/venv/bin/aitbc ...` and
  `sudo -n systemctl ...` on the live nodes.

## Example `run_aitbc_command` calls

The installed `aitbc` CLI on the live nodes only exposes a subset of commands
(`--show-deprecated` lists hidden ones). Valid examples include:

- `node list`
- `node info <node-id>`
- `ai --help`
- `wallet list`
- `market list-offers`
- `system check --service blockchain-node`

Deprecated command groups such as `chain` and `blockchain` are hidden from the
live CLI and should not be used through the MCP.

## Running outside Devin

```bash
source .venv/bin/activate
python aitbc_mcp_server.py
```

The server speaks `stdio` MCP transport, so it does nothing until a host
connects to it.

## Safety

* Destructive tools are dry-run by default.
* Even when `dry_run=false`, the tool requires `confirm=true`.
* Arbitrary commands are parsed with `shlex` and disallowed shell
  metacharacters are rejected.
* `run_cron_job` only accepts scripts under `/opt/aitbc/scripts/`,
  `/opt/aitbc/monitoring/`, and `/opt/aitbc/cluster/`.
