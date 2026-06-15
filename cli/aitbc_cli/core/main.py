#!/usr/bin/env python3
"""
AITBC CLI - Fixed version with modular command groups

Canonical invocation: `aitbc` (installed via /opt/aitbc/venv/bin/aitbc)
"""

import click
from aitbc_cli.commands.account import account
from aitbc_cli.commands.agent_sdk import agent
from aitbc_cli.commands.ai import ai
from aitbc_cli.commands.analytics import analytics  # Re-enabled - core.analytics exists
from aitbc_cli.commands.bridge import bridge
from aitbc_cli.commands.chain import chain
from aitbc_cli.commands.cluster import cluster
from aitbc_cli.commands.coin_requests import coin_requests
from aitbc_cli.commands.compliance import compliance
from aitbc_cli.commands.config import config as config_cmd
from aitbc_cli.commands.contract import contract
from aitbc_cli.commands.cross_chain import cross_chain  # Re-enabled - no core dependency
from aitbc_cli.commands.economics import economics
from aitbc_cli.commands.edge import edge

# from aitbc_cli.commands.node import node  # Disabled - imports from non-existent aitbc_cli.core
# from aitbc_cli.commands.agent_comm import agent_comm  # Disabled - imports from non-existent aitbc_cli.core
from aitbc_cli.commands.exchange import exchange
from aitbc_cli.commands.exchange_island import exchange_island
from aitbc_cli.commands.genesis import genesis
from aitbc_cli.commands.governance import governance

# Import island-specific commands
from aitbc_cli.commands.gpu_marketplace import gpu
from aitbc_cli.commands.gpu_resources import gpu as gpu_onchain
from aitbc_cli.commands.hermes import hermes
from aitbc_cli.commands.hermes_training import hermes_training
from aitbc_cli.commands.market import market
from aitbc_cli.commands.marketplace_cmd import marketplace
from aitbc_cli.commands.messaging import messaging
from aitbc_cli.commands.mining import mining

# from aitbc_cli.commands.deployment import deployment  # Disabled - missing core.deployment module
from aitbc_cli.commands.monitor import monitor  # Re-enabled - no core dependency
from aitbc_cli.commands.network import network
from aitbc_cli.commands.operations import operations
from aitbc_cli.commands.performance import performance
from aitbc_cli.commands.pool_hub import pool_hub
from aitbc_cli.commands.reputation import reputation
from aitbc_cli.commands.resource import resource
from aitbc_cli.commands.script import script
from aitbc_cli.commands.security import security
from aitbc_cli.commands.simulate import simulate
from aitbc_cli.commands.sync import sync

# Import modular command groups
from aitbc_cli.commands.system import system

# Import new modular commands
from aitbc_cli.commands.transactions import transactions
from aitbc_cli.commands.wallet import wallet
from aitbc_cli.commands.workflow import workflow

# Force CLI version for user-facing output
__version__ = "2.1.0"


@click.command(name="list")
def list_wallets():
    """Legacy wallet list alias"""
    return wallet.main(args=["list"], standalone_mode=False)


@click.command()
def version():
    """Show version information"""
    click.echo(f"aitbc, version {__version__}")
    click.echo("System Architecture Support: ✅")
    click.echo("FHS Compliance: ✅")
    click.echo("New Features: ✅")


@click.group()
@click.version_option(version=__version__, prog_name="aitbc")
@click.option("--url", default=None, help="Coordinator API URL (overrides config)")
@click.option("--api-key", default=None, help="API key for authentication")
@click.option("--chain-id", default=None, help="Chain ID for multichain operations (e.g., ait-mainnet, ait-devnet)")
@click.option("--output", default="table", type=click.Choice(["table", "json", "yaml", "csv"]), help="Output format")
@click.option("--verbose", "-v", count=True, help="Increase verbosity (can be used multiple times)")
@click.option("--debug", is_flag=True, help="Enable debug mode")
@click.pass_context
def cli(ctx, url, api_key, chain_id, output, verbose, debug):
    """AITBC CLI - Command Line Interface for AITBC Network

    Manage jobs, mining, wallets, blockchain operations, marketplaces, and AI
    services.

    SYSTEM ARCHITECTURE COMMANDS:
    system          System management commands
    system architect    System architecture analysis
    system audit         Audit system compliance
    system check         Check service configuration

    Examples:
    aitbc system architect
    aitbc system audit
    aitbc system check --service marketplace
    """
    ctx.ensure_object(dict)
    ctx.obj["url"] = url
    ctx.obj["api_key"] = api_key
    ctx.obj["output"] = output
    ctx.obj["verbose"] = verbose
    ctx.obj["debug"] = debug

    # Handle chain_id with auto-detection
    from aitbc_cli.utils.chain_id import get_chain_id

    default_rpc_url = url.replace("/api", "") if url else "http://localhost:8202"
    ctx.obj["chain_id"] = get_chain_id(default_rpc_url, override=chain_id)


# Add commands to CLI
cli.add_command(system)
cli.add_command(market, name="market")
cli.add_command(marketplace, name="marketplace")  # Keep old marketplace for compatibility
cli.add_command(chain, name="blockchain")
cli.add_command(agent, name="agent")  # Agent SDK and coordinator commands
cli.add_command(ai)  # AI job submission and inspection
cli.add_command(analytics)  # Re-enabled - core.analytics exists
cli.add_command(cross_chain, name="crosschain")  # Re-enabled - no core dependency
cli.add_command(reputation)  # Reputation management
cli.add_command(governance)  # Governance operations
# cli.add_command(deployment)  # Disabled - missing core.deployment module
cli.add_command(monitor)  # Re-enabled - no core dependency
# cli.add_command(node)  # Disabled - imports from non-existent aitbc_cli.core
# cli.add_command(agent_comm, name="agent")  # Disabled - imports from non-existent aitbc_cli.core
cli.add_command(exchange)
cli.add_command(config_cmd, name="config")
cli.add_command(list_wallets)
cli.add_command(version)
cli.add_command(gpu)
cli.add_command(gpu_onchain)
cli.add_command(exchange_island)
cli.add_command(wallet)
cli.add_command(genesis)

# Add new modular commands
cli.add_command(transactions)
cli.add_command(mining)
cli.add_command(hermes)
cli.add_command(workflow)
cli.add_command(resource)
cli.add_command(operations)
cli.add_command(simulate)
cli.add_command(edge)
cli.add_command(sync)
cli.add_command(account)
cli.add_command(messaging)
cli.add_command(network)
cli.add_command(performance)
cli.add_command(pool_hub)
cli.add_command(bridge)
cli.add_command(contract)
cli.add_command(script)
cli.add_command(economics)
cli.add_command(cluster)
cli.add_command(security)
cli.add_command(compliance)
cli.add_command(hermes_training)
cli.add_command(coin_requests)


def main(argv=None):
    """Entry point for console scripts and compatibility wrappers."""
    return cli.main(args=argv, prog_name="aitbc", standalone_mode=False)


if __name__ == "__main__":
    raise SystemExit(main())
