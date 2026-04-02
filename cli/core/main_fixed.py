#!/usr/bin/env python3
"""
AITBC CLI - Fixed version with proper imports
"""

import click
import sys
import os
from pathlib import Path

# Add current directory to Python path
current_dir = Path(__file__).parent
sys.path.insert(0, str(current_dir))

# Force version to 0.2.2
__version__ = "0.2.2"

# Import commands with error handling
commands = []

# Basic commands that work
try:
    from aitbc_cli.commands.system import system
    commands.append(system)
    print("✅ System command imported")
except ImportError as e:
    print(f"❌ System command import failed: {e}")

try:
    from aitbc_cli.commands.system_architect import system_architect
    commands.append(system_architect)
    print("✅ System architect command imported")
except ImportError as e:
    print(f"❌ System architect command import failed: {e}")

# Add basic version command
@click.command()
def version():
    """Show version information"""
    click.echo(f"aitbc, version {__version__}")

commands.append(version)

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
@click.pass_context
def cli(ctx, url, api_key, output, verbose, debug):
    """AITBC CLI - Command Line Interface for AITBC Network"""
    ctx.ensure_object(dict)
    ctx.obj['url'] = url
    ctx.obj['api_key'] = api_key
    ctx.obj['output'] = output
    ctx.obj['verbose'] = verbose
    ctx.obj['debug'] = debug

# Add all commands to CLI
for cmd in commands:
    cli.add_command(cmd)

if __name__ == '__main__':
    cli()
