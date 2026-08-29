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
| Wallets (read) | `list_wallets`, `get_wallet_balance`, `list_wallet_transactions` |
| Wallets (mutate) | `send_aitbc_transaction`, `stake_aitbc`, `unstake_aitbc` |
| AI jobs (read) | `list_ai_jobs`, `get_ai_job_status`, `get_ai_job_results` |
| AI jobs (mutate) | `submit_ai_job` |
| Marketplace | `list_market_offers`, `get_market_status` |
| Nodes config | `list_aitbc_node_config`, `get_node_info` |
| Accounts | `list_accounts`, `get_account` |
| Bonds (read) | `get_bond_status` |
| Bonds (mutate) | `create_performance_bond` |
| Transactions | `list_pending_transactions`, `get_transaction_status`, `search_transactions` |
| HTTP / RPC pivot | `call_aitbc_http` |
| Blockchain core | `get_blockchain_info`, `get_blockchain_head`, `list_blocks`, `get_block_info`, `get_account_info`, `get_transaction_info`, `get_mempool`, `get_network_info`, `get_blockchain_status`, `get_genesis_allocations`, `get_sync_config`, `list_chains`, `get_pending_mempool`, `reconcile_account_balance` |
| Transactions | `query_blockchain_transactions`, `get_cross_chain_swap`, `list_cross_chain_swaps`, `get_cross_chain_bridge`, `get_cross_chain_stats` |
| Accounts / state | `get_account_balance`, `get_account_state_snapshot`, `get_account_state_delta` |
| Consensus | `get_consensus_status`, `list_validators` |
| Staking | `get_staking_info` |
| Identity / governance | `get_agent_identity`, `get_governance_proposal` |
| Bonds | `get_bond`, `list_provider_bonds` |
| Bridge | `get_bridge_transfer`, `list_pending_bridge_transfers`, `get_bridge_transfer_proof`, `get_bridge_balance`, `get_bridge_validators`, `get_bridge_security_status`, `get_bridge_oracle_status`, `get_bridge_block_header` |
| Cross-chain | `get_cross_chain_rates`, `get_cross_chain_pools` |
| GPU | `list_gpus`, `get_gpu_info`, `get_gpu_allocations`, `get_edge_info` |
| AI on-chain | `list_ai_jobs_onchain`, `get_ai_job_onchain`, `get_ai_service_stats` |
| Marketplace on-chain | `list_marketplace_listings`, `get_marketplace_listing` |
| Escrow | `get_escrow_state` |
| Islands | `list_islands`, `get_island` |
| Contracts / forum | `list_contracts`, `get_messaging_contract_state`, `get_forum_topics`, `get_topic_messages` |
| Disputes | `get_active_disputes`, `get_authorized_arbitrators`, `get_arbitrator_disputes`, `get_user_disputes`, `get_dispute`, `get_dispute_evidence`, `get_arbitration_votes` |
| Subscription | `list_subscribers`, `get_lease_status` |
| Mutating RPC | `submit_blockchain_transaction`, `submit_marketplace_transaction`, `create_marketplace_listing`, `register_gpu`, `allocate_gpu`, `stake_tokens`, `unstake_tokens`, `register_agent_identity`, `create_governance_proposal`, `cast_governance_vote`, `execute_governance_proposal`, `create_cross_chain_swap`, `create_cross_chain_bridge`, `bridge_lock`, `bridge_confirm`, `bridge_unlock`, `create_escrow`, `release_escrow`, `refund_escrow`, `register_account`, `request_faucet`, `force_sync_chain` |
| Version / auth | `get_aitbc_version`, `get_auth_status` |

All destructive tools default to `dry_run=true` and require `confirm=true` before
they actually run a command on a remote host.

Additional typed RPC tools live in `aitbc_mcp_rpc_tools.py` and are imported by
`aitbc_mcp_server.py`; they cover the remaining blockchain routers (marketplace,
bridge, cross-chain, GPU, contracts, disputes, subscription, escrow, islands,
governance/identity, and a curated set of mutating RPC endpoints).

A generic catch-all remains `call_aitbc_http` for any endpoint not yet wrapped.

## Installation

The server imports the local `aitbc` package, so it must run from a Python
environment that has the project and its dependencies installed. Use the
project venv and make sure `mcp` is present:

```bash
cd /opt/aitbc
source venv/bin/activate
pip install -r mcp-server/requirements.txt
```

If you want a dedicated MCP venv instead, install the project and
`mcp-server/requirements.txt` in it so `import aitbc` works.

The live nodes also need the `aitbc` CLI. If it is not already at
`/opt/aitbc/venv/bin/aitbc`, install it in the project venv:

```bash
cd /opt/aitbc
source venv/bin/activate
pip install -e cli/
```

To make `aitbc` callable from any directory on a node, either symlink it into
a `PATH` directory or add the venv `bin/` directory to the SSH user's `PATH`:

```bash
ln -s /opt/aitbc/venv/bin/aitbc /usr/local/bin/aitbc
# or, in the SSH user's shell profile:
export PATH="/opt/aitbc/venv/bin:$PATH"
```

## Devin configuration

Add the server to your Devin project or user config:

```json
{
  "mcpServers": {
    "aitbc": {
      "command": "/opt/aitbc/venv/bin/python",
      "args": ["/opt/aitbc/mcp-server/aitbc_mcp_server.py"],
      "env": {
        "AITBC_MCP_SSH_USER": "oib",
        "AITBC_MCP_AITBC_CLI": "/opt/aitbc/venv/bin/aitbc",
        "AITBC_MCP_LOG_LEVEL": "INFO"
      }
    }
  }
}
```

Save project config as `.devin/mcp_config.json` and user secrets in
`.devin/mcp_config.local.json`.

### Local IDE (while developing)

For a local staging checkout, use that checkout's venv (it must have `aitbc`
and `mcp` importable):

```json
{
  "mcpServers": {
    "aitbc": {
      "command": "/home/oib/windsurf/aitbc/venv/bin/python",
      "args": ["/home/oib/windsurf/aitbc/mcp-server/aitbc_mcp_server.py"],
      "env": {
        "AITBC_MCP_AITBC_CLI": "/home/oib/windsurf/aitbc/venv/bin/aitbc",
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
      "mcp__aitbc__query_*",
      "mcp__aitbc__node_status",
      "mcp__aitbc__get_service_health"
    ],
    "ask": [
      "mcp__aitbc__start_node",
      "mcp__aitbc__stop_node",
      "mcp__aitbc__restart_node",
      "mcp__aitbc__run_cron_job",
      "mcp__aitbc__run_aitbc_command",
      "mcp__aitbc__run_aitbc_cli",
      "mcp__aitbc__call_aitbc_http",
      "mcp__aitbc__submit_ai_job",
      "mcp__aitbc__send_aitbc_transaction",
      "mcp__aitbc__create_performance_bond",
      "mcp__aitbc__stake_aitbc",
      "mcp__aitbc__unstake_aitbc",
      "mcp__aitbc__submit_blockchain_transaction",
      "mcp__aitbc__submit_marketplace_transaction",
      "mcp__aitbc__create_marketplace_listing",
      "mcp__aitbc__register_gpu",
      "mcp__aitbc__allocate_gpu",
      "mcp__aitbc__stake_tokens",
      "mcp__aitbc__unstake_tokens",
      "mcp__aitbc__register_agent_identity",
      "mcp__aitbc__create_governance_proposal",
      "mcp__aitbc__cast_governance_vote",
      "mcp__aitbc__execute_governance_proposal",
      "mcp__aitbc__create_cross_chain_swap",
      "mcp__aitbc__create_cross_chain_bridge",
      "mcp__aitbc__bridge_lock",
      "mcp__aitbc__bridge_confirm",
      "mcp__aitbc__bridge_unlock",
      "mcp__aitbc__create_escrow",
      "mcp__aitbc__release_escrow",
      "mcp__aitbc__refund_escrow",
      "mcp__aitbc__register_account",
      "mcp__aitbc__request_faucet",
      "mcp__aitbc__force_sync_chain"
    ],
    "deny": []
  }
}
```

## Requirements

* The MCP host (Devin) must be able to reach `aitbc3` and `hub.aitbc` via
  passwordless SSH.
* The `aitbc` CLI must be installed on each live node and available at the
  default path `/opt/aitbc/venv/bin/aitbc`, or wherever `AITBC_MCP_AITBC_CLI`
  is configured to point (see [Installation](#installation) above).
* The SSH user must be able to run `sudo -n <AITBC_MCP_AITBC_CLI> ...` and
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

Examples of destructive CLI wrappers:

- `submit_ai_job(prompt="...", wallet="genesis", model="llama3:8b")`
- `send_aitbc_transaction(from_wallet="genesis", to_address="ait...", amount="0.1")`
- `stake_aitbc(amount="1000", duration_days=30)`
- `create_performance_bond(provider_id="aitbc3-provider", amount="500")`

## HTTP / RPC pivot

A second generic tool, `call_aitbc_http`, hits the local HTTP APIs on each node.
It maps a service name to a base URL and builds a `curl` command.

Examples:

- service="blockchain-rpc", path="info"
- service="blockchain-rpc", path="account/0x..."
- service="blockchain-rpc", path="transaction/0x..."
- service="blockchain-rpc", path="blocks-range", params={"limit": "3"}
- service="coordinator-api", path="v1/jobs", params={"limit": "10"}
- service="blockchain-event-bridge", path="metrics/"

Typed RPC tools are also provided for the most common blockchain paths:
`get_blockchain_info`, `get_blockchain_head`, `list_blocks`, `get_block_info`,
`get_account_info`, `get_transaction_info`, `get_mempool`, `get_network_info`,
`get_blockchain_status`.

Some endpoints (e.g. coordinator, marketplace, event bridge) may require
authentication or be bound to a specific node.

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
