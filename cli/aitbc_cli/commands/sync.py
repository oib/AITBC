"""Sync commands for AITBC CLI"""

import subprocess
from pathlib import Path

import click


@click.group()
def sync():
    """Blockchain synchronization utilities"""
    pass


@sync.command()
@click.option("--source", default="http://127.0.0.1:8006", help="Source RPC URL (leader node)")
@click.option("--import-url", default="http://127.0.0.1:8006", help="Local RPC URL for import")
@click.option("--batch-size", type=int, default=100, help="Blocks per batch (default: 100)")
@click.option("--poll-interval", type=float, default=0.2, help="Seconds between batches (default: 0.2)")
def bulk(source, import_url, batch_size, poll_interval):
    """Bulk import blocks from a leader to catch up quickly"""
    # Resolve paths to the sync_cli.py script
    # Get the AITBC root directory (parent of cli directory)
    cli_dir = Path(__file__).resolve().parent.parent.parent
    aitbc_root = cli_dir.parent
    blockchain_dir = aitbc_root / "apps" / "blockchain-node"
    src_dir = blockchain_dir / "src"

    # Use the main AITBC venv at /opt/aitbc/venv
    venv_python = aitbc_root / "venv" / "bin" / "python3"

    # Fallback to blockchain-node .venv if main venv doesn't exist
    if not venv_python.exists():
        venv_python = blockchain_dir / ".venv" / "bin" / "python3"

    sync_cli = src_dir / "aitbc_chain" / "sync_cli.py"

    if not sync_cli.exists():
        click.echo(f"Error: sync_cli.py not found at {sync_cli}")
        click.echo("Ensure bulk sync feature is deployed.")
        raise click.Abort()

    cmd = [
        str(venv_python),
        str(sync_cli),
        "--source",
        source,
        "--import-url",
        import_url,
        "--batch-size",
        str(batch_size),
        "--poll-interval",
        str(poll_interval),
    ]

    # Prepare environment
    env = {
        "PYTHONPATH": str(src_dir),
    }

    click.echo(f"Running bulk sync from {source} to {import_url} (batch size: {batch_size})")

    try:
        result = subprocess.run(cmd, env=env, capture_output=False)
        if result.returncode != 0:
            click.echo("Error: Bulk sync failed. Check logs for details.")
            raise click.Abort()
        click.echo("Bulk sync completed.")
    except Exception as e:
        click.echo(f"Error during bulk sync: {e}")
        raise click.Abort() from e
