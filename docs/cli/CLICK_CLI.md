# AITBC CLI Documentation

**Last Updated:** 2026-05-28

## Overview

The AITBC CLI has a single entry point (`aitbc-cli`) that delegates to two command architectures:

1. **Production CLI (Parser/Handler)**: Core blockchain operations using parser/handler architecture
2. **Click-Based Commands**: Agent-specific operations using Click framework

## Single Entry Point

### Location
- Entry point: `/opt/aitbc/aitbc-cli` → `/opt/aitbc/cli/aitbc_cli.py`
- Command groups: `/opt/aitbc/cli/commands/`

### Usage

```bash
# Single entry point for all commands
aitbc-cli [OPTIONS] COMMAND [ARGS]...

# Get help
aitbc-cli --help
aitbc-cli [COMMAND] --help
```

### Command Delegation

The main entry point automatically delegates commands based on type:

**Production Commands (Parser/Handler):**
- wallet, blockchain, account, messaging, network, market, ai, analytics, script, mining, system, economics, cluster, performance, security, compliance, simulate, agent, hermes, workflow, resource, genesis, pool-hub, bridge, contract

**Click Commands (Agent Operations):**
- agent, ipfs, oracle, swarm, arbitrage, validator, plugin, database, island, edge, ai, monitor, governance, staking, compliance

### Available Commands

#### IPFS Commands
```bash
aitbc-cli ipfs upload --file <path> [--pin] [--name <name>]
aitbc-cli ipfs download <cid> [--output <path>]
aitbc-cli ipfs pin <cid>
aitbc-cli ipfs list
```

#### Oracle Commands
```bash
aitbc-cli oracle store --cid <cid> --price <price> [--description <desc>]
aitbc-cli oracle announce --cid <cid> --price <price>
aitbc-cli oracle listen --wallet <wallet>
aitbc-cli oracle retrieve <cid>
aitbc-cli oracle listings --wallet <wallet>
```

#### Agent Commands
```bash
# Main agent commands
aitbc-cli agent create --name <name> --description <desc>
aitbc-cli agent list [--type <type>] [--status <status>]
aitbc-cli agent execute <agent_id> --inputs <file>
aitbc-cli agent status <execution_id>

# Agent subcommands
aitbc-cli agent zk generate-proof --input <data> --circuit <circuit>
aitbc-cli agent zk verify-proof --proof <proof> --public-inputs <inputs>
aitbc-cli agent knowledge create --name <name>
aitbc-cli agent knowledge add-node --graph-id <id> --data <json>
aitbc-cli agent bounty create --title <title> --description <desc> --reward <amount>
aitbc-cli agent dispute file --title <title> --description <desc> --evidence <evidence>
```

#### Swarm Commands
```bash
aitbc-cli swarm create --name <name> --max-agents <count>
aitbc-cli swarm discover --swarm-id <id> [--capability <cap>]
aitbc-cli swarm add --swarm-id <id> --agent-id <agent>
aitbc-cli swarm distribute --swarm-id <id> --task <task>
aitbc-cli swarm status --swarm-id <id>
```

## Architecture

### Single Entry Point with Command Delegation

The main CLI entry point (`aitbc-cli`) automatically delegates commands based on type:

```python
# In aitbc_cli.py
CLICK_COMMANDS = [
    'agent', 'ipfs', 'oracle', 'swarm', 'arbitrage', 'validator',
    'plugin', 'database', 'island', 'edge', 'ai', 'monitor',
    'governance', 'staking', 'compliance'
]

def main(argv=None):
    if argv and argv[0] in CLICK_COMMANDS:
        # Delegate to Click CLI
        from cli.click_cli import aitbc_click
        aitbc_click()
    else:
        # Delegate to unified CLI (parser/handler)
        from unified_cli import run_cli
        return run_cli(argv, globals())
```

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

1. Create file in `/opt/aitbc/cli/commands/<command>.py`
2. Add command to `CLICK_COMMANDS` list in `/opt/aitbc/cli/aitbc_cli.py`
3. Import and register in `/opt/aitbc/cli/click_cli.py`

For production parser/handler commands, use the standard parser/handler pattern in `/opt/aitbc/cli/parsers/` and `/opt/aitbc/cli/handlers/`.

## Integration with Agent SDK

Agent SDK methods call Click CLI commands via subprocess:

```python
from aitbc_agent.command_executor import CommandExecutor

executor = CommandExecutor("/opt/aitbc/aitbc-cli")
result = executor.execute_command("ipfs", ["upload", "--file", "path"])
```

## Implementation Status

### Implemented CLI Commands
- ✅ IPFS (upload, download, pin, list)
- ✅ Oracle (store, announce, listen, retrieve, listings)
- ✅ Agent (create, list, execute, status)
- ✅ Agent zk (generate-proof, verify-proof, create-receipt)
- ✅ Agent knowledge (create, add-node)
- ✅ Agent bounty (create, list)
- ✅ Agent dispute (file, vote)
- ✅ Swarm (create, discover, add, distribute, status)
- ✅ Arbitrage (analyze, find, execute, status, performance)
- ✅ Validator (init, status, deregister, slashing)
- ✅ Plugin (publish, list, install, uninstall)
- ✅ Database (init, query, backup, restore)
- ✅ Island (create, join, leave, bridge)
- ✅ Edge (init, status, list, configure)
- ✅ AI (submit, list-ai-power, trade-ai-power, reputation)
- ✅ Monitor (start, stop, status, alerts)
- ✅ Governance (vote)
- ✅ Staking (manage)
- ✅ Compliance (check, report)
- ✅ Cross-chain (transfer, list, swaps)

## Testing

```bash
# Test CLI entry point
aitbc-cli --help
aitbc-cli ipfs --help
aitbc-cli agent --help
aitbc-cli agent zk --help

# Test specific command
aitbc-cli agent zk generate-proof --input test --circuit circuit1
```

## Notes

- The CLI uses a single entry point (`aitbc-cli`) for all commands
- Production commands (wallet, blockchain, etc.) use parser/handler architecture
- Agent-specific commands (agent, ipfs, oracle, etc.) use Click framework
- Agent SDK methods internally call `aitbc-cli` commands via subprocess
- Commands are automatically delegated based on the command group
