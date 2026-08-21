"""Sync commands for AITBC CLI"""

import os
import subprocess
from pathlib import Path
from typing import Any

import click

from aitbc_cli.utils.error_handling import abort
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
@click.pass_context
def bulk(ctx, source, import_url, batch_size, poll_interval):
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
        abort(ctx, f"sync_cli.py not found at {sync_cli}. Ensure bulk sync feature is deployed.")

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
            abort(ctx, "Bulk sync failed. Check logs for details.")
        click.echo("Bulk sync completed.")
    except Exception as e:
        abort(ctx, f"Error during bulk sync: {e}", from_exception=e)


def _format_status_table(
    chain_id,
    height,
    block_hash,
    timestamp,
    total_transactions,
    total_accounts,
    p2p_endpoint,
    supported_chains,
    hub_status=None,
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

    if hub_status:
        rows.append(("Hub height", str(hub_status.get("height", "N/A"))))
        rows.append(("Hub hash", f"{str(hub_status.get('hash', ''))[:16]}..." if hub_status.get("hash") else "N/A"))
        rows.append(("Height gap", str(hub_status.get("gap", "N/A"))))
        rows.append(("Divergence", hub_status.get("divergence", "unknown")))

    label_width = max(len(label) for label, _ in rows)
    click.echo("Sync Status")
    click.echo("-" * 40)
    for label, value in rows:
        click.echo(f"{label.ljust(label_width)} : {value}")


@sync.command()
@click.option("--node-url", default="http://127.0.0.1:8202", help="Local node RPC URL")
@click.option("--chain-id", default=None, help="Chain ID to check (defaults to node's configured chain)")
@click.option("--hub-url", default=None, help="Hub RPC URL to compare against (defaults to HUB_RPC_URL or node-url)")
@click.option("--gap-threshold", type=int, default=5, help="Height gap considered a divergence (default: 5)")
@click.option("--alert", is_flag=True, help="Exit non-zero on divergence or unreachable hub")
@click.pass_context
def status(ctx, node_url, chain_id, hub_url, gap_threshold, alert):
    """Show synchronization status (current block, peer count, sync progress)."""
    client = AITBCHTTPClient(base_url=node_url)
    try:
        # Query current chain head
        head_params = {"chain_id": chain_id} if chain_id else None
        head = client.get("/rpc/head", params=head_params)

        # Query network info
        network_info = client.get("/rpc/network-info")

        # Query sync configuration (v0.6.2)
        sync_config: dict[str, Any] | None = client.get("/rpc/sync/config")
    except NetworkError as e:
        abort(ctx, f"Cannot connect to node at {node_url}", from_exception=e)
    finally:
        client.close()

    # Handle error responses from endpoints
    if isinstance(head, dict) and head.get("error"):
        abort(ctx, f"Error from /rpc/head: {head['error']}")
    if isinstance(network_info, dict) and network_info.get("error"):
        abort(ctx, f"Error from /rpc/network-info: {network_info['error']}")
    # Sync config endpoint might not exist in older versions
    if isinstance(sync_config, dict) and sync_config.get("error"):
        sync_config = None

    # Extract head fields (fall back to network-info chain_id if not provided)
    resolved_chain_id = chain_id or network_info.get("chain_id") or head.get("chain_id")
    height = head.get("height")
    block_hash = head.get("hash") or head.get("last_block_hash")
    timestamp = head.get("timestamp")
    total_transactions = head.get("total_transactions")
    total_accounts = head.get("total_accounts")

    p2p_endpoint = network_info.get("p2p_endpoint")
    supported_chains = network_info.get("supported_chains") or []

    # Compare with hub if a hub URL is available
    hub_status: dict[str, Any] = {}
    if not hub_url:
        hub_url = os.environ.get("HUB_RPC_URL")
    if hub_url:
        hub_client = AITBCHTTPClient(base_url=hub_url, timeout=10)
        try:
            hub_head = hub_client.get("/rpc/head", params=head_params)
            hub_info = hub_client.get("/rpc/network-info")
        except NetworkError:
            hub_status = {
                "height": "N/A",
                "hash": "",
                "gap": "N/A",
                "divergence": "HUB_UNREACHABLE",
            }
        else:
            hub_client.close()
            hub_height = hub_head.get("height") if isinstance(hub_head, dict) else None
            hub_hash = hub_head.get("hash") or hub_head.get("last_block_hash") if isinstance(hub_head, dict) else None
            gap = (hub_height - height) if (hub_height is not None and height is not None) else None
            divergence = "none"
            if gap is not None and gap > gap_threshold:
                divergence = f"BEHIND_BY_{gap}"
            elif gap is not None and gap < 0:
                divergence = f"AHEAD_BY_{-gap}"
            elif hub_height is not None and height == hub_height and hub_hash and block_hash and hub_hash != block_hash:
                divergence = "HASH_MISMATCH"
            hub_status = {
                "height": hub_height if hub_height is not None else "N/A",
                "hash": hub_hash or "",
                "gap": gap if gap is not None else "N/A",
                "divergence": divergence,
            }

    _format_status_table(
        resolved_chain_id,
        height,
        block_hash,
        timestamp,
        total_transactions,
        total_accounts,
        p2p_endpoint,
        supported_chains,
        hub_status,
    )

    divergence = hub_status.get("divergence", "none")
    if alert and divergence not in ("none", "N/A", "HUB_UNREACHABLE"):
        ctx.exit(1)

    # Show v0.6.2 sync optimization status if available
    if sync_config:
        click.echo("\nSync Optimization (v0.6.2)")
        click.echo("-" * 40)
        parallel_enabled = sync_config.get("sync_parallel_enabled", False)
        delta_enabled = sync_config.get("sync_delta_enabled", False)
        priority_enabled = sync_config.get("gossip_priority_enabled", False)
        click.echo(f"Parallel sync      : {'enabled' if parallel_enabled else 'disabled'}")
        click.echo(f"Delta sync        : {'enabled' if delta_enabled else 'disabled'}")
        click.echo(f"Gossip priority   : {'enabled' if priority_enabled else 'disabled'}")
