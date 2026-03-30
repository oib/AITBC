#!/usr/bin/env python3
"""
AITBC CLI - Main entry point for the AITBC Command Line Interface
"""

import click
import sys
from typing import Optional

from . import __version__
from .config import get_config
from .utils import output, setup_logging
from .commands.client import client
from .commands.miner import miner
from .commands.wallet import wallet
from .commands.auth import auth
from .commands.blockchain import blockchain
from .commands.marketplace import marketplace
from .commands.simulate import simulate
from .commands.admin import admin
from .commands.config import config
from .commands.monitor import monitor
from .commands.governance import governance
from .commands.exchange import exchange
from .commands.agent import agent
from .commands.multimodal import multimodal
from .commands.optimize import optimize
# from .commands.openclaw import openclaw  # Temporarily disabled due to command registration issues
# from .commands.marketplace_advanced import advanced  # Temporarily disabled due to command registration issues
from .commands.swarm import swarm
from .commands.chain import chain
from .commands.genesis import genesis
from .plugins import plugin, load_plugins


@click.group()
@click.option(
    "--url",
    default=None,
    help="Coordinator API URL (overrides config)"
)
@click.option(
    "--api-key",
    default=None,
    help="API key (overrides config)"
)
@click.option(
    "--output",
    type=click.Choice(["table", "json", "yaml"]),
    default="table",
    help="Output format"
)
@click.option(
    "--verbose", "-v",
    count=True,
    help="Increase verbosity (use -v, -vv, -vvv)"
)
@click.option(
    "--debug",
    is_flag=True,
    help="Enable debug mode"
)
@click.option(
    "--config-file",
    default=None,
    help="Path to config file"
)
@click.version_option(version=__version__, prog_name="aitbc")
@click.pass_context
def cli(ctx, url: Optional[str], api_key: Optional[str], output: str, 
        verbose: int, debug: bool, config_file: Optional[str]):
    """
    AITBC CLI - Command Line Interface for AITBC Network
    
    Manage jobs, mining, wallets, and blockchain operations from the command line.
    """
    # Ensure context object exists
    ctx.ensure_object(dict)
    
    # Setup logging based on verbosity
    log_level = setup_logging(verbose, debug)
    
    # Load configuration
    config = get_config(config_file)
    
    # Override config with command line options
    if url:
        config.coordinator_url = url
    if api_key:
        config.api_key = api_key
    
    # Store in context for subcommands
    ctx.obj['config'] = config
    ctx.obj['output_format'] = output
    ctx.obj['log_level'] = log_level


# Add command groups
cli.add_command(client)
cli.add_command(miner)
cli.add_command(wallet)
cli.add_command(auth)
cli.add_command(blockchain)
cli.add_command(marketplace)
cli.add_command(simulate)
cli.add_command(admin)
cli.add_command(config)
cli.add_command(monitor)
cli.add_command(governance)
cli.add_command(exchange)
cli.add_command(agent)
cli.add_command(multimodal)
cli.add_command(optimize)
# cli.add_command(openclaw)  # Temporarily disabled due to command registration issues
# cli.add_command(advanced)  # Temporarily disabled due to command registration issues
cli.add_command(swarm)
from .commands.chain import chain      # NEW: Multi-chain management
from .commands.genesis import genesis  # NEW: Genesis block commands
from .commands.node import node        # NEW: Node management commands
from .commands.analytics import analytics  # NEW: Analytics and monitoring
from .commands.agent_comm import agent_comm  # NEW: Cross-chain agent communication
# from .commands.marketplace_cmd import marketplace  # NEW: Global chain marketplace - disabled due to conflict
from .commands.deployment import deploy  # NEW: Production deployment and scaling
cli.add_command(chain)      # NEW: Multi-chain management
cli.add_command(genesis)    # NEW: Genesis block commands
cli.add_command(node)        # NEW: Node management commands
cli.add_command(analytics)  # NEW: Analytics and monitoring
cli.add_command(agent_comm)  # NEW: Cross-chain agent communication
# cli.add_command(marketplace)  # NEW: Global chain marketplace - disabled due to conflict
cli.add_command(deploy)      # NEW: Production deployment and scaling
cli.add_command(plugin)
load_plugins(cli)


@cli.command()
@click.pass_context
def version(ctx):
    """Show version information"""
    output(f"AITBC CLI version {__version__}", ctx.obj['output_format'])


@cli.command()
@click.pass_context
def config_show(ctx):
    """Show current configuration"""
    config = ctx.obj['config']
    output({
        "coordinator_url": config.coordinator_url,
        "api_key": "***REDACTED***" if config.api_key else None,
        "output_format": ctx.obj['output_format'],
        "config_file": config.config_file
    }, ctx.obj['output_format'])


def main():
    """Main entry point"""
    try:
        cli()
    except KeyboardInterrupt:
        click.echo("\nAborted by user", err=True)
        sys.exit(1)
    except Exception as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
