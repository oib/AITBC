#!/usr/bin/env python3
"""
AITBC CLI - Main entry point for the AITBC Command Line Interface
"""

import click
import sys
from typing import Optional

from . import __version__
from .config import get_config


def with_role(role: str):
    """Decorator to set role for command groups"""
    def decorator(func):
        @click.pass_context
        def wrapper(ctx, *args, **kwargs):
            ctx.parent.detected_role = role
            return func(ctx, *args, **kwargs)
        return wrapper
    return decorator
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
from .commands.oracle import oracle
from .commands.market_maker import market_maker
from .commands.multisig import multisig
from .commands.genesis_protection import genesis_protection
from .commands.transfer_control import transfer_control
from .commands.agent import agent
from .commands.multimodal import multimodal
from .commands.optimize import optimize
# from .commands.openclaw import openclaw  # Temporarily disabled due to naming conflict
from .commands.marketplace_advanced import advanced  # Re-enabled after fixing registration issues
from .commands.swarm import swarm
from .commands.chain import chain
from .commands.genesis import genesis
from .commands.test_cli import test
from .commands.node import node
from .commands.analytics import analytics
from .commands.agent_comm import agent_comm
from .commands.deployment import deploy
from .commands.cross_chain import cross_chain
from .commands.compliance import compliance
from .commands.surveillance import surveillance
from .commands.regulatory import regulatory
from .commands.ai_trading import ai_trading
from .commands.advanced_analytics import advanced_analytics_group
from .commands.ai_surveillance import ai_surveillance_group

# AI provider commands
from .commands.ai import ai_group

# Enterprise integration (optional)
try:
    from .commands.enterprise_integration import enterprise_integration_group
except ImportError:
    enterprise_integration_group = None

from .commands.sync import sync
from .commands.explorer import explorer
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
@click.option(
    "--test-mode",
    is_flag=True,
    help="Enable test mode (uses mock data and test endpoints)"
)
@click.option(
    "--dry-run",
    is_flag=True,
    help="Dry run mode (show what would be done without executing)"
)
@click.option(
    "--timeout",
    type=int,
    default=30,
    help="Request timeout in seconds (useful for testing)"
)
@click.option(
    "--no-verify",
    is_flag=True,
    help="Skip SSL certificate verification (testing only)"
)
@click.version_option(version=__version__, prog_name="aitbc")
@click.pass_context
def cli(ctx, url: Optional[str], api_key: Optional[str], output: str, 
        verbose: int, debug: bool, config_file: Optional[str], test_mode: bool,
        dry_run: bool, timeout: int, no_verify: bool):
    """
    AITBC CLI - Command Line Interface for AITBC Network
    
    Manage jobs, mining, wallets, blockchain operations, marketplaces, and AI services.
    
    CORE COMMANDS:
      client          Submit and manage AI compute jobs
      miner           GPU mining operations and status
      wallet          Wallet management and transactions
      marketplace     GPU marketplace and trading
      blockchain      Blockchain operations and queries
      exchange        Real exchange integration (Binance, Coinbase, etc.)
      explorer        Blockchain explorer and analytics
      
    ADVANCED FEATURES:
      analytics       Chain performance monitoring and predictions
      ai-trading      AI-powered trading strategies
      surveillance    Market surveillance and compliance
      compliance      Regulatory compliance and reporting
      governance      Network governance and proposals
      
    DEVELOPMENT TOOLS:
      admin           Administrative operations
      config          Configuration management
      monitor         System monitoring and health
      test            CLI testing and validation
      deploy          Deployment and infrastructure management
      
    SPECIALIZED SERVICES:
      agent           AI agent operations
      multimodal      Multi-modal AI processing
      oracle          Price discovery and data feeds
      market-maker    Automated market making
      genesis-protection Advanced security features
      
    Use 'aitbc <command> --help' for detailed help on any command.
    
    Examples:
      aitbc client submit --prompt "Generate an image" --model llama2
      aitbc miner status
      aitbc wallet create --type hd
      aitbc marketplace list
      aitbc exchange create-pair --pair AITBC/BTC --base-asset AITBC --quote-asset BTC
      aitbc analytics summary
      aitbc explorer status
      aitbc explorer block 12345
      aitbc explorer transaction 0x123...
      aitbc explorer search --address 0xabc...
    """
    # Ensure context object exists
    ctx.ensure_object(dict)
    
    # Setup logging based on verbosity
    log_level = setup_logging(verbose, debug)
    
    # Detect role from command name (before config is loaded)
    role = None
    
    # Check invoked_subcommand first
    if ctx.invoked_subcommand:
        if ctx.invoked_subcommand == 'client':
            role = 'client'
        elif ctx.invoked_subcommand == 'miner':
            role = 'miner'
        elif ctx.invoked_subcommand == 'blockchain':
            role = 'blockchain'
        elif ctx.invoked_subcommand == 'admin':
            role = 'admin'
    
    # Also check if role was already set by command group
    if not role:
        role = getattr(ctx, 'detected_role', None)
    
    # Load configuration with role
    config = get_config(config_file, role=role)
    
    # Override config with command line options
    if url:
        config.coordinator_url = url
    if api_key:
        config.api_key = api_key
    
    # Store in context for subcommands
    ctx.obj['config'] = config
    ctx.obj['output_format'] = output
    ctx.obj['log_level'] = log_level
    ctx.obj['test_mode'] = test_mode
    ctx.obj['dry_run'] = dry_run
    ctx.obj['timeout'] = timeout
    ctx.obj['no_verify'] = no_verify
    
    # Apply test mode settings
    if test_mode:
        config.coordinator_url = config.coordinator_url or "http://localhost:8000"
        config.api_key = config.api_key or "test-api-key"


# Add command groups
cli.add_command(client)
cli.add_command(miner)
cli.add_command(wallet)
cli.add_command(plugin)
# cli.add_command(openclaw)  # Temporarily disabled due to naming conflict
cli.add_command(advanced)  # Re-enabled after fixing registration issues
cli.add_command(auth)
cli.add_command(blockchain)
cli.add_command(marketplace)
cli.add_command(simulate)
cli.add_command(admin)
cli.add_command(config)
cli.add_command(monitor)
cli.add_command(governance)
cli.add_command(exchange)
cli.add_command(oracle)
cli.add_command(market_maker)
cli.add_command(multisig)
cli.add_command(genesis_protection)
cli.add_command(transfer_control)
cli.add_command(agent)
cli.add_command(multimodal)
cli.add_command(optimize)
cli.add_command(ai_group)
# cli.add_command(openclaw)  # Temporarily disabled
cli.add_command(swarm)
cli.add_command(chain)
cli.add_command(genesis)
cli.add_command(test)
cli.add_command(node)
cli.add_command(analytics)
cli.add_command(agent_comm)
cli.add_command(deploy)
cli.add_command(cross_chain)
cli.add_command(compliance)
cli.add_command(surveillance)
cli.add_command(regulatory)
cli.add_command(ai_trading)
cli.add_command(advanced_analytics_group)
cli.add_command(ai_surveillance_group)
if enterprise_integration_group is not None:
    cli.add_command(enterprise_integration_group)
cli.add_command(sync)
cli.add_command(explorer)
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
