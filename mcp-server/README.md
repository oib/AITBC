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
| Cron jobs | `list_cron_jobs`, `run_cron_job` |
| Logs | `get_service_logs` |
| AITBC CLI pivot | `run_aitbc_cli`, `run_aitbc_command`, `list_aitbc_cli_group` |
| Wallets | `list_wallets`, `get_wallet_balance`, `list_wallet_transactions` |
| AI jobs | `list_ai_jobs`, `get_ai_job_status`, `get_ai_job_results` |
| Marketplace | `list_market_offers`, `get_market_status` |
| Nodes config | `list_aitbc_node_config`, `get_node_info` |
| Accounts | `list_accounts`, `get_account` |
| Bonds | `get_bond_status` |
| Transactions | `list_pending_transactions`, `get_transaction_status`, `search_transactions` |
| Version / auth | `get_aitbc_version`, `get_auth_status` |

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
      "mcp__aitbc__search_*",
      "mcp__aitbc__node_status",
      "mcp__aitbc__get_service_health"
    ],
    "ask": [
      "mcp__aitbc__start_node",
      "mcp__aitbc__stop_node",
      "mcp__aitbc__restart_node",
      "mcp__aitbc__run_cron_job",
      "mcp__aitbc__run_aitbc_command",
      "mcp__aitbc__run_aitbc_cli"
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

## The aitbc CLI pivot

The server exposes two ways to use the aitbc CLI:

1. **Typed wrappers** such as `list_wallets`, `get_wallet_balance`,
   `list_market_offers`, `list_ai_jobs`, etc. These are safer and easier for
   the model to call.
2. **Generic `run_aitbc_cli`** for anything not covered. Pass `group`,
   `subcommand`, `args` (positional) and `options` (`--key=value`).

Examples of `run_aitbc_cli`:

- group="wallet", subcommand="list"
- group="wallet", subcommand="balance", args=["genesis"]
- group="wallet", subcommand="transactions", args=["genesis"], options={"limit": "5"}
- group="ai", subcommand="jobs", options={"limit": "10"}
- group="ai", subcommand="status", options={"job-id": "<job-id>"}
- group="market", subcommand="list", options={"status": "active"}
- group="market", subcommand="status", args=["<order-id>"]
- group="node", subcommand="info", args=["<node-id>"]

The installed CLI only exposes a validated subset of commands. Deprecated groups
such as `chain` and `blockchain` are hidden and will be rejected.

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
