"""
CLI entry point for training environment setup.
"""

import sys
from pathlib import Path

# Add parent directory to sys.path for importability
if str(Path(__file__).parent.parent.parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import click

from .environment import TrainingEnvironment
from .exceptions import TrainingSetupError


@click.group()
def cli():
    """AITBC Training Environment Setup CLI"""
    pass


@cli.command()
@click.option(
    "--aitbc-dir",
    default="/opt/aitbc",
    help="AITBC installation directory",
)
@click.option(
    "--log-dir",
    default="/var/log/aitbc/training-setup",
    help="Log directory",
)
@click.option(
    "--faucet-amount",
    default=1000,
    help="Amount to fund per request",
)
@click.option(
    "--genesis-allocation",
    default=10000,
    help="Genesis allocation amount",
)
def setup(aitbc_dir, log_dir, faucet_amount, genesis_allocation):
    """Setup complete training environment"""
    click.echo("Starting AITBC training environment setup...")
    
    try:
        env = TrainingEnvironment(
            aitbc_dir=aitbc_dir,
            log_dir=log_dir,
            faucet_amount=faucet_amount,
            genesis_allocation=genesis_allocation,
        )
        
        results = env.setup_full_environment()
        
        click.echo("\n=== Setup Summary ===")
        for key, value in results.items():
            click.echo(f"{key}: {value}")
        
        click.echo(f"\nLog file: {env.log_dir}/training_setup.log")
        
        if results.get("prerequisites") == "failed":
            sys.exit(1)
            
    except TrainingSetupError as e:
        click.echo(f"Setup failed: {e}", err=True)
        sys.exit(1)
    except Exception as e:
        click.echo(f"Unexpected error: {e}", err=True)
        sys.exit(1)


@cli.command()
@click.option(
    "--aitbc-dir",
    default="/opt/aitbc",
    help="AITBC installation directory",
)
def check(aitbc_dir):
    """Check training environment prerequisites"""
    click.echo("Checking training environment prerequisites...")
    
    try:
        env = TrainingEnvironment(aitbc_dir=aitbc_dir)
        env.check_prerequisites()
        click.echo("✓ All prerequisites met")
        sys.exit(0)
    except TrainingSetupError as e:
        click.echo(f"✗ Prerequisites not met: {e}", err=True)
        sys.exit(1)


@cli.command()
@click.option(
    "--aitbc-dir",
    default="/opt/aitbc",
    help="AITBC installation directory",
)
def verify(aitbc_dir):
    """Verify training environment is properly configured"""
    click.echo("Verifying training environment...")
    
    try:
        env = TrainingEnvironment(aitbc_dir=aitbc_dir)
        results = env.verify_environment()
        
        click.echo("\n=== Verification Results ===")
        for key, value in results.items():
            click.echo(f"{key}: {value}")
        
        sys.exit(0)
    except Exception as e:
        click.echo(f"Verification failed: {e}", err=True)
        sys.exit(1)


@cli.command()
@click.argument("wallet_name")
@click.option(
    "--password",
    default="training123",
    help="Wallet password",
)
@click.option(
    "--aitbc-dir",
    default="/opt/aitbc",
    help="AITBC installation directory",
)
def fund_wallet(wallet_name, password, aitbc_dir):
    """Fund a specific training wallet"""
    click.echo(f"Funding wallet: {wallet_name}")
    
    try:
        env = TrainingEnvironment(aitbc_dir=aitbc_dir)
        result = env.fund_training_wallet(wallet_name, password)
        click.echo(f"✓ Wallet {wallet_name} funded")
        sys.exit(0)
    except TrainingSetupError as e:
        click.echo(f"✗ Funding failed: {e}", err=True)
        sys.exit(1)


@cli.command()
@click.argument("json_path")
@click.option(
    "--aitbc-dir",
    default="/opt/aitbc",
    help="AITBC installation directory",
)
def run_stage(json_path, aitbc_dir):
    """Run a training stage from JSON schema definition"""
    click.echo(f"Running stage from JSON: {json_path}")
    
    try:
        env = TrainingEnvironment(aitbc_dir=aitbc_dir)
        result = env.run_stage_from_json(json_path)
        
        click.echo("\n=== Stage Execution Results ===")
        click.echo(f"Stage: {result['stage']}")
        click.echo(f"Title: {result['title']}")
        click.echo(f"Success: {result['success']}")
        
        if result['success']:
            click.echo(f"\nCommands executed: {len(result['commands'])}")
            for i, cmd_result in enumerate(result['commands'], 1):
                status = "✓" if cmd_result['success'] else "✗"
                click.echo(f"  {status} Command {i}: {'Success' if cmd_result['success'] else 'Failed'}")
                if cmd_result.get('tx_hash'):
                    click.echo(f"      TX Hash: {cmd_result['tx_hash']}")
        
        sys.exit(0 if result['success'] else 1)
    except TrainingSetupError as e:
        click.echo(f"✗ Stage execution failed: {e}", err=True)
        sys.exit(1)
    except FileNotFoundError:
        click.echo(f"✗ JSON file not found: {json_path}", err=True)
        sys.exit(1)


if __name__ == "__main__":
    cli()
