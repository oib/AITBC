#!/usr/bin/env python3
"""
AITBC CLI - Minimal Version with Working Commands Only
"""

import click
import sys
import os
from pathlib import Path

# Add CLI directory to Python path
CLI_DIR = Path(__file__).parent
sys.path.insert(0, str(CLI_DIR))

# Import only working commands
from .commands.wallet import wallet
from .commands.config import config
from .commands.blockchain import blockchain
from .commands.compliance import compliance

@click.group()
@click.option('--url', help='Coordinator API URL (overrides config)')
@click.option('--api-key', help='API key (overrides config)')
@click.option('--output', type=click.Choice(['table', 'json', 'yaml']), default='table', help='Output format')
@click.option('-v', '--verbose', count=True, help='Increase verbosity (use -v, -vv, -vvv)')
@click.option('--debug', is_flag=True, help='Enable debug mode')
@click.option('--config-file', help='Path to config file')
@click.option('--test-mode', is_flag=True, help='Enable test mode (uses mock data and test endpoints)')
@click.option('--dry-run', is_flag=True, help='Dry run mode (show what would be done without executing)')
@click.option('--timeout', type=int, help='Request timeout in seconds (useful for testing)')
@click.option('--no-verify', is_flag=True, help='Skip SSL certificate verification (testing only)')
@click.version_option(version='0.1.0', prog_name='AITBC CLI')
@click.pass_context
def cli(ctx, url, api_key, output, verbose, debug, config_file, test_mode, dry_run, timeout, no_verify):
    """AITBC CLI - Command Line Interface for AITBC Network
    
    Manage jobs, mining, wallets, blockchain operations, and AI services.
    """
    # Ensure that ctx.obj exists and is a dict
    ctx.ensure_object(dict)
    
    # Initialize config
    try:
        config = get_config(config_file)
        if url:
            config.coordinator_url = url
        if api_key:
            config.api_key = api_key
        if timeout:
            config.timeout = timeout
    except Exception as e:
        # Create a minimal config if loading fails
        config = type('Config', (), {
            'coordinator_url': url or 'http://127.0.0.1:8000',
            'api_key': api_key,
            'timeout': timeout or 30,
            'config_file': config_file
        })()
    
    # Store global options and config in context
    ctx.obj.update({
        'url': url,
        'api_key': api_key,
        'output': output,
        'verbose': verbose,
        'debug': debug,
        'config_file': config_file,
        'test_mode': test_mode,
        'dry_run': dry_run,
        'timeout': timeout,
        'no_verify': no_verify,
        'config': config,
        'output_format': output
    })

# Add working commands
cli.add_command(wallet)
cli.add_command(config)
cli.add_command(blockchain)
cli.add_command(compliance)

@cli.command()
def version():
    """Show version information"""
    click.echo("AITBC CLI version 0.1.0")

@cli.command()
def config_show():
    """Show current configuration"""
    click.echo("Configuration display (minimal version)")
    click.echo("Use 'aitbc config --help' for configuration options")

def main():
    """Main entry point"""
    try:
        cli()
    except KeyboardInterrupt:
        click.echo("\nOperation cancelled by user", err=True)
        sys.exit(1)
    except Exception as e:
        if 'debug' in sys.argv or '--debug' in sys.argv:
            import traceback
            traceback.print_exc()
        else:
            click.echo(f"Error: {e}", err=True)
        sys.exit(1)

if __name__ == '__main__':
    main()