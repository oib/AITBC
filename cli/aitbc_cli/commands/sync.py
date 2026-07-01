"""Sync commands for AITBC CLI"""

import subprocess
from pathlib import Path

import click

from aitbc_cli.utils.http_client import AITBCHTTPClient, NetworkError


@click.group()
def sync():
    """Blockchain synchronization utilities"""
    pass


@sync.command()
@click.option("--source", default="http://127.0.0.1:8202", help="Source RPC URL (leader node)")
@click.option("--import-url", default="http://127.0.0.1:8202", help="Local RPC URL for import")
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


def _format_status_table(
    chain_id,
    height,
    block_hash,
    timestamp,
    total_transactions,
    total_accounts,
    p2p_endpoint,
    supported_chains,
):
    """Format sync status into an aligned text table via click.echo."""
    truncated_hash = f"{block_hash[:16]}..." if block_hash else "N/A"
    chains_str = ", ".join(supported_chains) if supported_chains else "N/A"

    rows = [
        ("Chain ID", str(chain_id) if chain_id is not None else "N/A"),
        ("Local height", str(height) if height is not None else "N/A"),
        ("Last block hash", truncated_hash),
        ("Last block timestamp", str(timestamp) if timestamp is not None else "N/A"),
        ("Total transactions", str(total_transactions) if total_transactions is not None else "N/A"),
        ("Total accounts", str(total_accounts) if total_accounts is not None else "N/A"),
        ("P2P endpoint", str(p2p_endpoint) if p2p_endpoint else "N/A"),
        ("Supported chains", chains_str),
    ]

    label_width = max(len(label) for label, _ in rows)
    click.echo("Sync Status")
    click.echo("-" * 40)
    for label, value in rows:
        click.echo(f"{label.ljust(label_width)} : {value}")


@sync.command()
@click.option("--node-url", default="http://127.0.0.1:8202", help="Local node RPC URL")
@click.option("--chain-id", default=None, help="Chain ID to check (defaults to node's configured chain)")
def status(node_url, chain_id):
    """Show synchronization status (current block, peer count, sync progress)."""
    client = AITBCHTTPClient(base_url=node_url)
    try:
        # Query current chain head
        head_params = {"chain_id": chain_id} if chain_id else None
        head = client.get("/rpc/head", params=head_params)

        # Query network info
        network_info = client.get("/rpc/network-info")
    except NetworkError as e:
        click.echo(f"Error: Cannot connect to node at {node_url}")
        raise click.Abort() from e
    finally:
        client.close()

    # Handle error responses from endpoints
    if isinstance(head, dict) and head.get("error"):
        click.echo(f"Error from /rpc/head: {head['error']}")
        raise click.Abort()
    if isinstance(network_info, dict) and network_info.get("error"):
        click.echo(f"Error from /rpc/network-info: {network_info['error']}")
        raise click.Abort()

    # Extract head fields (fall back to network-info chain_id if not provided)
    resolved_chain_id = chain_id or network_info.get("chain_id") or head.get("chain_id")
    height = head.get("height")
    block_hash = head.get("hash") or head.get("last_block_hash")
    timestamp = head.get("timestamp")
    total_transactions = head.get("total_transactions")
    total_accounts = head.get("total_accounts")

    p2p_endpoint = network_info.get("p2p_endpoint")
    supported_chains = network_info.get("supported_chains") or []

    _format_status_table(
        resolved_chain_id,
        height,
        block_hash,
        timestamp,
        total_transactions,
        total_accounts,
        p2p_endpoint,
        supported_chains,
    )
