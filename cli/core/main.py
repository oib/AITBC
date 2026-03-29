#!/usr/bin/env python3
"""
AITBC CLI - Main entry point for the AITBC Command Line Interface
"""

import click
import sys
from typing import Optional

# Force version to 0.2.2
__version__ = "0.2.2"

try:
    from config import get_config
except ImportError:
    def get_config():
        return {}

try:
    from utils import output, setup_logging
except ImportError:
    def output(msg, format_type):
        print(msg)
    def setup_logging(verbose, debug):
        return "INFO"


def with_role(role: str):
    """Decorator to set role for command groups"""
    def decorator(func):
        @click.pass_context
        def wrapper(ctx, *args, **kwargs):
            ctx.parent.detected_role = role
            return func(ctx, *args, **kwargs)
        return wrapper
    return decorator


# Import command modules with error handling
commands = []

# Core commands
try:
    from commands.client import client
    commands.append(client)
except ImportError:
    pass

try:
    from commands.miner import miner
    commands.append(miner)
except ImportError:
    pass

try:
    from commands.wallet import wallet
    commands.append(wallet)
except ImportError:
    pass

try:
    from commands.blockchain import blockchain
    commands.append(blockchain)
except ImportError:
    pass

try:
    from commands.admin import admin
    commands.append(admin)
except ImportError:
    pass

try:
    from commands.marketplace import marketplace
    commands.append(marketplace)
except ImportError:
    pass

try:
    from commands.exchange import exchange
    commands.append(exchange)
except ImportError:
    pass

try:
    from commands.governance import governance
    commands.append(governance)
except ImportError:
    pass

try:
    from commands.test_cli import test
    commands.append(test)
except ImportError:
    pass

# Config command should be basic
try:
    from commands.config import config
    commands.append(config)
except ImportError:
    pass


@click.group()
@click.option(
    "--url",
    default=None,
    help="Coordinator API URL (overrides config)"
)
@click.option(
    "--api-key",
    default=None,
    help="API key for authentication"
)
@click.option(
    "--output",
    default="table",
    type=click.Choice(["table", "json", "yaml", "csv"]),
    help="Output format"
)
@click.option(
    "--verbose",
    "-v",
    count=True,
    help="Increase verbosity (can be used multiple times)"
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
      exchange        Real exchange integration
      config          Configuration management
      
    Use 'aitbc <command> --help' for detailed help on any command.
    
    Examples:
      aitbc client submit --prompt "Generate an image"
      aitbc miner status
      aitbc wallet create --type hd
      aitbc marketplace list
      aitbc config show
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


# Add command groups safely
for cmd in commands:
    try:
        cli.add_command(cmd)
    except Exception as e:
        print(f"Warning: Could not add command: {e}")


@cli.command()
@click.pass_context
def version(ctx):
    """Show version information"""
    output(f"AITBC CLI version {__version__}", ctx.obj['output_format'])


if __name__ == "__main__":
    cli()
