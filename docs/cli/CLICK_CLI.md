# AITBC CLI Documentation

**Last Updated:** 2026-05-28

## Overview

The AITBC CLI has a single entry point (`aitbc`) built on the Click framework. All command groups live under `/opt/aitbc/cli/aitbc_cli/commands/` and are loaded lazily by `/opt/aitbc/cli/aitbc_cli/core/main.py`, so `aitbc --help` stays usable even when optional dependencies are missing.

## Single Entry Point

### Location

- Entry point: `/usr/local/bin/aitbc` — shell wrapper exec'ing `python -m aitbc_cli.core.main` inside `/opt/aitbc/venv`
- Command groups: `/opt/aitbc/cli/aitbc_cli/commands/`
- CLI entry point module: `/opt/aitbc/cli/aitbc_cli/core/main.py`

### Usage

```bash
# Single entry point for all commands
aitbc [OPTIONS] COMMAND [ARGS]...

# Get help
aitbc --help
aitbc [COMMAND] --help

# Show version
aitbc version
```

### Command Groups

All commands are Click groups registered in `core/main.py`. Major groups include:

- wallet, blockchain, account, messaging, network, market, ai, analytics, script, mining, system, economics, cluster, performance, security, compliance, simulate, agent, agent-msg, agent-comm, agent-task, agent-wallet, workflow, resource, genesis, pool-hub, bridge, contract
- ipfs, oracle, plugin, edge, monitor, governance, zk, dispute, exchange, node, sync, tee, trade, explorer, deploy, service, bond, bootstrap, reinvest, confidential, coin-requests, gpu, gpu-onchain, exchange-island, crosschain, developer, grant, reputation, prometheus, dashboard, transactions, http, update, auth, health, operations, config

Top-level convenience commands also exist: `aitbc list`, `aitbc version`, `aitbc start`, `aitbc stop`, `aitbc restart`, `aitbc stake`, `aitbc unstake`, `aitbc liquidity-stake`, `aitbc update`, `aitbc health`.

### Available Commands

#### IPFS Commands

```bash
aitbc ipfs upload --file <path> [--pin] [--name <name>]
aitbc ipfs download <cid> [--output <path>]
aitbc ipfs pin <cid>
aitbc ipfs list
```

#### Oracle Commands

```bash
aitbc oracle store --cid <cid> --price <price> [--description <desc>]
aitbc oracle listings
```

#### Agent Commands

```bash
# Main agent commands
aitbc agent create --name <name> --type <type>
aitbc agent list [--agent-dir <dir>] [--format json]
aitbc agent status --agent-id <agent_id>
aitbc agent register --agent-id <agent_id>

# Agent subcommands
aitbc agent capabilities
aitbc agent discover agents [--capability <cap>]
aitbc agent workflow create-workflow --name <name> --steps-file <file>
aitbc agent workflow execute --workflow-id <id>

# Related top-level groups
aitbc zk circuits
aitbc zk verify --proof <proof> --public-signals <inputs>
aitbc agent-msg send --message <msg> --to-agent <agent>
aitbc dispute file --agreement-id <id> --respondent <addr> --dispute-type <type> --reason <text> --evidence-hash <hash>
```

## Architecture

### Single Entry Point with Lazy Command Loading

The main CLI entry point (`aitbc`, implemented in `/opt/aitbc/cli/aitbc_cli/core/main.py`) registers every command group through `LazyCommand`/`LazyGroup` proxies. Each proxy imports its module under `aitbc_cli/commands/` only when the command is invoked or its help is rendered:

```python
# In core/main.py
wallet = _lazy("aitbc_cli.commands.wallet", "wallet", name="wallet", group=True)
chain = _lazy("aitbc_cli.commands.chain", "chain", name="blockchain", group=True)
...
cli.add_command(wallet)
cli.add_command(chain, name="blockchain")
```

Because loading is lazy, `aitbc --help` works even when optional dependencies for a specific group are not installed.

### Click Command Pattern

Click commands follow this pattern:

```python
import click
from utils import output, error, success, warning

@click.group()
def command_group():
    """Command group description"""
    pass

@command_group.command()
@click.option("--option", required=True, help="Option description")
@click.argument("argument")
def subcommand(option: str, argument: str):
    """Subcommand description"""
    try:
        # Implementation logic
        result = {"status": "success", "data": {...}}
        output(result)
    except Exception as e:
        error(f"Failed: {e}")
```

### Registering New Commands

To add a new Click command group:

1. Create a module in `/opt/aitbc/cli/aitbc_cli/commands/<command>.py` exporting a `click.Group`/`click.Command`
2. Register it in `/opt/aitbc/cli/aitbc_cli/core/main.py` via a `_lazy(...)` proxy and `cli.add_command(...)`

## Integration with Agent SDK

Agent SDK methods call Click CLI commands via subprocess:

```python
from aitbc_agent.command_executor import CommandExecutor

executor = CommandExecutor("/usr/local/bin/aitbc")
result = executor.execute_command("ipfs", ["upload", "--file", "path"])
```

## Implementation Status

### Implemented CLI Commands

- ✅ IPFS (upload, download, pin, unpin, list, island)
- ✅ Oracle (store, listings)
- ✅ Agent (create, register, register-identity, get-identity, verify-identity, list, status, capabilities, config, discover, inbox, subscribe, workflow)
- ✅ ZK (circuits, verify, health)
- ✅ Agent messaging (`agent-msg`: send, receive, peers, ping, request-coins)
- ✅ Dispute (file, active, get, user, votes, vote, evidence, arbitrator)
- ✅ Plugin (create, list, load)
- ✅ Edge (status, balance, transfer, island, gpu)
- ✅ AI (submit, pay, jobs, status, accept, refund, results, cancel, stats, service)
- ✅ Monitor (dashboard, metrics, alerts, history, webhooks, campaigns, sweepers)
- ✅ Governance (propose, vote, list, execute, close, status, get, propagate, aggregate-votes)
- ✅ Staking (stake, unstake, liquidity-stake; also `wallet stake`/`unstake`/`staking-info`)
- ✅ Compliance (check, classify, export-audit)
- ✅ Cross-chain (`crosschain`: rates, swap, status, swaps, bridge, bridge-status, confirm, pools, stats)

## Testing

```bash
# Test CLI entry point
aitbc --help
aitbc ipfs --help
aitbc agent --help
aitbc zk --help

# Test specific command
aitbc zk verify --proof '{"a":"b"}' --public-signals '{"x":1}'
```

## Notes

- The CLI uses a single entry point (`aitbc`) for all commands
- All command groups use the Click framework and are lazily loaded from `aitbc_cli/commands/`
- Agent SDK methods internally call `aitbc` commands via subprocess
- Command groups are registered in `aitbc_cli/core/main.py`
